"""
tests_integration/conftest.py — Harness for the Phase 1 contract sweep
(docs/TEST_PLAN.md). Unlike tests/, which mocks every database call, this
drives the *real* FastAPI app — real routing, real dependency injection, real
Beanie/Motor queries — over a real (but disposable, local-only) MongoDB
database. This is the only way to catch what a mocked-DB unit suite
structurally cannot: `list_goals` returned 500 on every call for weeks because
every one of the 321 tests that existed at the time mocked the query that was
actually broken.

SAFETY: this suite only ever talks to `mongodb://localhost:27017` — never the
Atlas cluster in the real .env. Settings overrides are applied via os.environ
*before* `main` (and therefore `core.config.get_settings()`, which is
`@lru_cache`d) is ever imported, so the real .env's MONGODB_URI can never leak
in here even if this file is imported after something else already touched
`core.config`. The target database is dropped both before and after the run,
so a crashed previous run never contaminates the next one.
"""
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

# ── Point every Settings() at a disposable local database, before any app
# module is imported. Real environment variables win over the .env file in
# pydantic-settings' precedence order, so this is not overridable by whatever
# the real .env happens to contain.
_TEST_DB_NAME = "digital_twin_ai_contract_sweep_test"
os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
os.environ["MONGODB_DB_NAME"] = _TEST_DB_NAME
os.environ.setdefault("JWT_SECRET_KEY", "integration-test-secret-do-not-use-in-prod")
os.environ.setdefault("NODE_ENV", "development")  # keep /api/docs visible for debugging
# No AI provider keys — the two AI-backed endpoints (assistant/chat,
# recommendations/*) are expected to degrade to their documented fallback
# ("rules" / AIProviderUnavailableError) rather than reach a real provider.
#
# Set to "" rather than popped from os.environ: Settings reads _ROOT_ENV_FILE
# (the real root .env, which DOES have a real GROQ_API_KEY) directly via
# pydantic-settings' own env_file parser — a source entirely separate from
# os.environ, so removing the *process* env var does nothing to stop the real
# key being read straight out of the file. Explicitly setting an empty string
# is a real environment variable, which DOES take priority over the file, and
# an empty string is falsy in every `if settings.GROQ_API_KEY:` check the
# service layer uses — the first run of this suite skipped this and made 15
# real, billed calls to api.groq.com before the mistake was caught.
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""

import main  # noqa: E402  (must import after the env vars above are set)
from core.database import close_mongo_connection, connect_to_mongo  # noqa: E402


async def _require_local_mongo() -> None:
    """Fails fast with an actionable message rather than letting every test in
    the suite fail individually with a raw connection-timeout traceback. Not a
    module-level pytestmark — conftest.py pytestmark propagation to sibling
    test files is easy to get subtly wrong, so this is called explicitly from
    the one fixture every test in this suite actually depends on."""
    probe = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=1500)
    try:
        await probe.admin.command("ping")
    except Exception as exc:
        pytest.skip(
            "No MongoDB reachable at localhost:27017 — the contract sweep needs a "
            "real, local, disposable database (never the Atlas cluster in .env). "
            "`brew services start mongodb-community` or "
            f"`docker run -p 27017:27017 mongo:7`. ({exc})"
        )
    finally:
        probe.close()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Real rate limiting stays real — this only stops it accumulating ACROSS
    unrelated test functions in the same run. `/auth/register` and
    `/auth/login` are limited to 5/minute; this suite registers a fresh user
    per test, so without a reset the 6th test function in a run would 429 no
    matter how correct its own logic is. slowapi's key_func is the client IP,
    which every request in this suite shares (loopback, via ASGITransport —
    there's no real network layer), so tests genuinely would contend for the
    same bucket. This only resets the counter ONCE, before each test function
    starts — it does nothing to stop a test's own repeated calls within its own
    body from tripping the limit, which is exactly what test_rate_limiting.py
    below relies on to verify the limiter's real, configured behaviour."""
    from core.rate_limit import limiter
    limiter._storage.reset()
    yield


@pytest_asyncio.fixture
async def app_client():
    """A real app instance and a real Mongo connection, fresh per test
    function.

    Deliberately function-scoped, not session-scoped: pytest-asyncio hands
    each test function its own event loop by default, and Motor's client
    (like any asyncio object holding onto a loop) can't cross from the loop
    it was created on to a different one — a session-scoped connection here
    reliably produced "Future attached to a different loop" on the second
    test to run. Reconnecting per test costs a few milliseconds against a
    local Mongo and buys correctness, plus a bonus: every test starts against
    a genuinely empty database rather than whatever earlier tests left behind,
    so cross-test data leakage can't hide a bug the way it could with shared
    state.
    """
    await _require_local_mongo()

    client = AsyncIOMotorClient("mongodb://localhost:27017")
    await client.drop_database(_TEST_DB_NAME)
    client.close()

    await connect_to_mongo()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main.app), base_url="http://testserver"
        ) as ac:
            yield ac
    finally:
        await close_mongo_connection()


async def _register_and_login(client: AsyncClient, email: str) -> AsyncClient:
    """Registers a real user through the real endpoint and logs in through the
    real endpoint, so the auth cookie this returns is exactly what a browser
    would have — not a hand-minted JWT that happens to satisfy the decoder."""
    payload = {
        "email": email,
        "password": "a-genuinely-fine-password-1",
        "name": "Contract Sweep User",
        "age": 30,
        "monthly_income_baseline": 50000,
    }
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, f"register failed: {r.status_code} {r.text}"

    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": payload["password"]}
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return client


@pytest_asyncio.fixture
async def user_a(app_client):
    """A fresh, real, authenticated user — new email per test function (uuid4)
    so tests never collide on the unique email index even when run out of
    order or repeated."""
    email = f"sweep-a-{uuid.uuid4().hex[:12]}@example.com"
    await _register_and_login(app_client, email)
    yield app_client
    # Logout so a later fixture use in the same test module starts clean —
    # cheap insurance against cookie-jar bleed between tests sharing app_client.
    await app_client.post("/api/v1/auth/logout")


@pytest_asyncio.fixture
async def user_b(app_client):
    """A second, independent authenticated user — for cross-tenant isolation
    checks (Phase 1.2). Uses its own AsyncClient (its own cookie jar) against
    the SAME app/database, so user_a's and user_b's sessions can be held
    concurrently within one test rather than one login clobbering the other."""
    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://testserver"
    ) as client:
        email = f"sweep-b-{uuid.uuid4().hex[:12]}@example.com"
        await _register_and_login(client, email)
        yield client
