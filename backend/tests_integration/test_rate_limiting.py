"""
tests_integration/test_rate_limiting.py — docs/TEST_PLAN.md Phase 1.2's "rate
limits actually trigger" checkbox. Every configured limit, hit for real.

Each test makes N+1 calls within its own body — `_reset_rate_limits`
(conftest.py, autouse) only zeroes the counter once per test *function*, so a
test making all its own calls in sequence still sees the limiter engage on the
call past its configured threshold, same as it would for a real client.
"""
import pytest

pytestmark = pytest.mark.asyncio


async def test_register_is_limited_to_5_per_minute(app_client):
    payload = {
        "password": "a-genuinely-fine-password-1", "name": "Rate Limit Test", "age": 25,
    }
    statuses = []
    for i in range(6):
        r = await app_client.post(
            "/api/v1/auth/register", json={**payload, "email": f"ratelimit-reg-{i}@example.com"}
        )
        statuses.append(r.status_code)
    assert statuses[:5] == [201] * 5, f"first 5 registrations should all succeed: {statuses}"
    assert statuses[5] == 429, f"the 6th within a minute must be rate-limited: {statuses}"


async def test_login_is_limited_to_10_per_minute(app_client):
    email = "ratelimit-login@example.com"
    await app_client.post("/api/v1/auth/register", json={
        "email": email, "password": "correct-password-123", "name": "Login Limit", "age": 25,
    })
    statuses = []
    for _ in range(11):
        r = await app_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-on-purpose"}
        )
        statuses.append(r.status_code)
    assert statuses[:10] == [401] * 10, f"first 10 wrong-password attempts should all be clean 401s: {statuses}"
    assert statuses[10] == 429, f"the 11th within a minute must be rate-limited: {statuses}"


async def test_change_password_is_limited_to_5_per_minute(user_a):
    statuses = []
    for _ in range(6):
        r = await user_a.post(
            "/api/v1/users/me/change-password",
            json={"current_password": "wrong-on-purpose", "new_password": "irrelevant-new-pw-1"},
        )
        statuses.append(r.status_code)
    assert statuses[:5] == [401] * 5, f"first 5 wrong-current-password attempts should all be clean 401s: {statuses}"
    assert statuses[5] == 429, f"the 6th within a minute must be rate-limited: {statuses}"


async def test_assistant_chat_is_limited_to_15_per_minute(user_a):
    """No provider is configured (conftest.py deliberately unsets both API
    keys), so every one of these individually resolves to 503 — the rate
    limiter runs before that, as `@limiter.limit` decorates the route itself,
    so the 16th call is 429 regardless of what the route body would have done."""
    statuses = []
    for _ in range(16):
        r = await user_a.post("/api/v1/assistant/chat", json={"message": "hi"})
        statuses.append(r.status_code)
    assert statuses[:15] == [503] * 15, f"first 15 calls should all reach the route (503, no provider): {statuses}"
    assert statuses[15] == 429, f"the 16th within a minute must be rate-limited: {statuses}"
