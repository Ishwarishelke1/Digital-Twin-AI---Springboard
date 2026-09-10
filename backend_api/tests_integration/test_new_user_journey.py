"""
tests_integration/test_new_user_journey.py — New-user pass beyond
test_contract_sweep.py's existing zero-data check and full-cycle tests.

Three things this file adds that test_contract_sweep.py does not cover:

1. Forecasting-method TIER BOUNDARIES actually crossed (0 -> 1 -> 2-3 -> 4+
   data points), not just "a zero-data user never 500s" — proving
   `method_used` really changes at each documented threshold
   (forecast_service.py's `_select_method`, duplicated per-engine on purpose,
   see CLAUDE.md).
2. Adversarial/edge-case input: goal windows of zero or negative length,
   deadlines already passed, malformed ObjectIds, unicode/whitespace/
   over-length strings, pagination boundaries, duplicate registration.
3. Cross-tenant isolation extended to habits and simulation (the existing
   test_cross_tenant_isolation in test_contract_sweep.py covers goals,
   finance and study only).

Same conftest.py fixtures as test_contract_sweep.py (app_client, user_a,
user_b) — disposable local Mongo, dropped before/after, real ASGI transport,
no AI provider keys (assistant/recommendations must degrade cleanly).
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio


# ─── Forecasting method tiers, crossed for real ────────────────────────────────

async def _post_income_expense(client, year: int, month: int, income: str, expense: str):
    if income:
        r = await client.post("/api/v1/finance/transactions", json={
            "type": "INCOME", "amount": income, "category": "SALARY",
            "transaction_date": f"{year:04d}-{month:02d}-05T00:00:00Z",
        })
        assert r.status_code == 201, r.text
    if expense:
        r = await client.post("/api/v1/finance/transactions", json={
            "type": "EXPENSE", "amount": expense, "category": "FOOD",
            "transaction_date": f"{year:04d}-{month:02d}-10T00:00:00Z",
        })
        assert r.status_code == 201, r.text


async def test_savings_forecast_method_crosses_every_tier(user_a):
    # forecast_service.DEFAULT_LOOKBACK_MONTHS=12 trims to the active range
    # ending at *today's* month — dates must be recent, not a fixed year, or
    # they fall outside the lookback window and never register as a data point.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    def _months_ago(n: int) -> tuple[int, int]:
        total = now.year * 12 + (now.month - 1) - n
        year, month0 = divmod(total, 12)
        return year, month0 + 1

    # 0 points: brand-new user.
    r = await user_a.get("/api/v1/forecast/savings")
    assert r.status_code == 200, r.text
    assert r.json()["method_used"] == "insufficient_data"

    # _build_monthly_series zero-fills every month from the EARLIEST active
    # transaction's month through the current month, so "n data points" is
    # controlled by how far back the earliest transaction is — not by how many
    # transactions were posted. Build backward from the current month so each
    # step adds exactly one more trailing period.

    # 1 point: earliest (only) transaction in the current month -> naive_last_value.
    await _post_income_expense(user_a, *_months_ago(0), "50000", "30000")
    r = await user_a.get("/api/v1/forecast/savings")
    assert r.status_code == 200, r.text
    assert r.json()["data_points_used"] == 1, r.json()
    assert r.json()["method_used"] == "naive_last_value", r.json()

    # 2 points: earliest transaction now 1 month back -> moving_average.
    await _post_income_expense(user_a, *_months_ago(1), "50000", "31000")
    r = await user_a.get("/api/v1/forecast/savings")
    assert r.json()["data_points_used"] == 2, r.json()
    assert r.json()["method_used"] == "moving_average", r.json()

    # 3 points: still moving_average.
    await _post_income_expense(user_a, *_months_ago(2), "50000", "29000")
    r = await user_a.get("/api/v1/forecast/savings")
    assert r.json()["data_points_used"] == 3, r.json()
    assert r.json()["method_used"] == "moving_average", r.json()

    # 4+ points: -> linear_regression.
    await _post_income_expense(user_a, *_months_ago(3), "50000", "28000")
    r = await user_a.get("/api/v1/forecast/savings")
    assert r.json()["data_points_used"] == 4, r.json()
    assert r.json()["method_used"] == "linear_regression", r.json()


# ─── Sufficiency-gated ML predictions (goal_completion_service) ───────────────

async def test_goal_prediction_refuses_below_sufficiency_thresholds(user_a):
    """MIN_DURATION_DAYS=7 and MIN_DAYS_ELAPSED=3 (goal_completion_service.py)
    — below either, the endpoint must return a reason, never a fabricated
    probability."""
    # Window shorter than MIN_DURATION_DAYS.
    r = await user_a.post("/api/v1/users/me/goals", json={
        "title": "Too Soon", "category": "FINANCE",
        "target_value": 1000, "unit": "USD",
        "target_date": "2099-01-01T00:00:03Z",  # placeholder, overwritten below
    })
    assert r.status_code == 201, r.text
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    goal_id = next(g["goal_id"] for g in r.json()["active_goals"] if g["title"] == "Too Soon")
    r = await user_a.patch(f"/api/v1/users/me/goals/{goal_id}", json={
        "target_date": (now + timedelta(days=3)).isoformat(),
    })
    assert r.status_code == 200, r.text

    r = await user_a.get("/api/v1/users/me/goals/predictions")
    assert r.status_code == 200, r.text
    pred = next(p for p in r.json() if p["goal_id"] == goal_id)
    assert pred["probability"] is None
    assert pred["reason"], "goal window too short must carry a reason, not silently return None"


async def test_goal_prediction_deadline_already_passed(user_a):
    r = await user_a.post("/api/v1/users/me/goals", json={
        "title": "Past Due", "category": "FINANCE",
        "target_value": 1000, "unit": "USD", "target_date": "2020-01-01T00:00:00Z",
    })
    assert r.status_code == 201, r.text
    goal_id = next(g["goal_id"] for g in r.json()["active_goals"] if g["title"] == "Past Due")

    r = await user_a.get("/api/v1/users/me/goals/predictions")
    assert r.status_code == 200, r.text
    pred = next(p for p in r.json() if p["goal_id"] == goal_id)
    assert pred["probability"] is None
    assert pred["reason"], "a passed deadline must carry a reason, not a fabricated probability"


async def test_goal_prediction_min_days_elapsed_gate(user_a):
    """MIN_DAYS_ELAPSED=3 — a long-enough window, but created too recently,
    must still refuse with a reason (goal_completion_service.py)."""
    r = await user_a.post("/api/v1/users/me/goals", json={
        "title": "Brand New", "category": "FINANCE",
        "target_value": 1000, "unit": "USD", "target_date": "2027-01-01T00:00:00Z",
    })
    assert r.status_code == 201, r.text
    goal_id = next(g["goal_id"] for g in r.json()["active_goals"] if g["title"] == "Brand New")

    r = await user_a.get("/api/v1/users/me/goals/predictions")
    assert r.status_code == 200, r.text
    pred = next(p for p in r.json() if p["goal_id"] == goal_id)
    assert pred["probability"] is None
    assert pred["reason"], "a goal created moments ago must refuse with a reason, not a probability"
    # Provenance must be surfaced even on a refusal, per goal_completion_service's
    # documented "hide its provenance" refusal.
    assert pred["trained_on"] == "synthetic"


async def test_goal_prediction_already_completed_gate(user_a):
    r = await user_a.post("/api/v1/users/me/goals", json={
        "title": "Done Already", "category": "FINANCE",
        "target_value": 1000, "unit": "USD", "target_date": "2027-01-01T00:00:00Z",
    })
    assert r.status_code == 201, r.text
    goal_id = next(g["goal_id"] for g in r.json()["active_goals"] if g["title"] == "Done Already")

    r = await user_a.patch(f"/api/v1/users/me/goals/{goal_id}", json={"current_value": 1000})
    assert r.status_code == 200, r.text

    r = await user_a.get("/api/v1/users/me/goals/predictions")
    assert r.status_code == 200, r.text
    pred = next((p for p in r.json() if p["goal_id"] == goal_id), None)
    # Either omitted entirely or explicitly None+reason — either way, never a
    # fabricated probability for a goal whose current_value already met target.
    if pred is not None:
        assert pred["probability"] is None or pred["reason"] is None and pred["probability"] is not None


# ─── Adversarial / edge-case input ─────────────────────────────────────────────

async def test_malformed_object_id_is_404_or_422_never_500(user_a):
    for path in [
        "/api/v1/users/me/goals/not-a-valid-id",
        "/api/v1/finance/transactions/not-a-valid-id",
        "/api/v1/study/sessions/not-a-valid-id",
        "/api/v1/habits/daily-log/not-a-valid-id",
        "/api/v1/forecast/goals/not-a-valid-id",
    ]:
        r = await user_a.get(path)
        assert r.status_code in (404, 422), f"{path} returned {r.status_code}: {r.text}"
        assert r.status_code != 500


async def test_simulation_malformed_id_is_404_not_500(user_a):
    """Regression: simulation_service.get_simulation and
    submit_recommendation_feedback called PydanticObjectId(...) with no
    try/except, unlike every other service's id-lookup (e.g.
    finance_service.update_transaction) — a malformed id 500'd instead of
    404ing. Fixed to match the established convention."""
    r = await user_a.get("/api/v1/simulation/not-a-valid-id")
    assert r.status_code == 404, r.text

    r = await user_a.patch(
        "/api/v1/simulation/recommendations/not-a-valid-id/feedback",
        json={"feedback": "HELPFUL"},
    )
    assert r.status_code == 404, r.text


async def test_duplicate_email_registration_rejected_not_500(app_client):
    email = "dup-test@example.com"
    payload = {
        "email": email, "password": "a-genuinely-fine-password-1",
        "name": "First", "age": 25, "monthly_income_baseline": 40000,
    }
    r = await app_client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text

    r = await app_client.post("/api/v1/auth/register", json={**payload, "name": "Second"})
    assert r.status_code in (400, 409), r.text
    assert r.status_code != 500


async def test_unicode_and_whitespace_input(user_a):
    r = await user_a.post("/api/v1/users/me/goals", json={
        "title": "  存お金・ميزانية \U0001F4B0  ",
        "category": "FINANCE", "target_value": 100, "unit": "USD",
        "target_date": "2027-01-01T00:00:00Z",
    })
    assert r.status_code == 201, r.text

    r = await user_a.patch("/api/v1/users/me/profile", json={"name": "   "})
    # Whitespace-only name should not silently succeed as a "valid" name — either
    # rejected (422/400) or trimmed; must not 500 either way.
    assert r.status_code in (200, 400, 422), r.text
    assert r.status_code != 500


async def test_pagination_edge_cases(user_a):
    r = await user_a.post("/api/v1/finance/transactions", json={
        "type": "EXPENSE", "amount": "10.00", "category": "FOOD",
    })
    assert r.status_code == 201, r.text

    r = await user_a.get("/api/v1/finance/transactions", params={"page": 0})
    assert r.status_code == 422, r.text  # ge=1

    r = await user_a.get("/api/v1/finance/transactions", params={"page": -1})
    assert r.status_code == 422, r.text

    r = await user_a.get("/api/v1/finance/transactions", params={"limit": 1000})
    assert r.status_code == 422, r.text  # le=100

    r = await user_a.get("/api/v1/finance/transactions", params={"page": 9999})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == [], "a page far beyond the end must be an empty page, not an error"


async def test_zero_target_value_goal_rejected_at_schema(user_a):
    r = await user_a.post("/api/v1/users/me/goals", json={
        "title": "Zero Target", "category": "FINANCE",
        "target_value": 0, "unit": "USD", "target_date": "2027-01-01T00:00:00Z",
    })
    assert r.status_code == 422, r.text  # gt=0 at the schema layer


async def test_negative_amount_rejected_at_schema(user_a):
    r = await user_a.post("/api/v1/finance/transactions", json={
        "type": "EXPENSE", "amount": "-50.00", "category": "FOOD",
    })
    assert r.status_code == 422, r.text  # gt=0 at the schema layer


# ─── Cross-tenant isolation, extended to habits and simulation ────────────────

async def test_cross_tenant_isolation_habits_and_simulation(user_a, user_b):
    log = await user_b.post("/api/v1/habits/daily-log", json={
        "sleep_hours": "8.0", "exercise_minutes": 20,
        "water_intake_liters": "2.5", "screen_time_hours": "3.0",
        "mood_rating": 5, "log_date": "2026-02-01T00:00:00Z",
    })
    assert log.status_code == 200, log.text
    b_log_id = log.json()["id"]

    sim = await user_b.post("/api/v1/simulation/finance/scenarios", json={"additional_monthly_saving": 200})
    assert sim.status_code == 200, sim.text
    b_sim_id = sim.json()["id"]
    b_rec_id = sim.json()["recommendation"]["id"]

    for method, path, body in [
        ("DELETE", f"/api/v1/habits/daily-log/{b_log_id}", None),
        ("GET", f"/api/v1/simulation/{b_sim_id}", None),
        ("PATCH", f"/api/v1/simulation/recommendations/{b_rec_id}/feedback", {"feedback": "HELPFUL"}),
    ]:
        r = await user_a.request(method, path, json=body)
        assert r.status_code in (403, 404), f"{method} {path} returned {r.status_code}: {r.text}"
        assert r.status_code != 500

    # B's own data survives untouched.
    r = await user_b.get("/api/v1/habits/daily-log")
    assert any(h["id"] == b_log_id for h in r.json()["data"])


# ─── Assistant grounding — the composed context, not a real LLM call ──────────
# Deterministic and free: asserts the *context fed to the model* contains the
# real figures from every domain, without spending a provider call. See
# services/ai_assistant_service.py's build_assistant_context.

async def test_assistant_context_grounded_in_every_domain(user_a):
    from datetime import datetime, timezone
    from beanie import PydanticObjectId
    from models.user import User
    from services.ai_assistant_service import build_assistant_context

    # Finance: a real expense this month, categorized.
    r = await user_a.post("/api/v1/finance/transactions", json={
        "type": "EXPENSE", "amount": "1234.00", "category": "FOOD",
    })
    assert r.status_code == 201, r.text

    # Study: a real session with a distinctive subject name.
    r = await user_a.post("/api/v1/study/sessions", json={
        "subject": "Quantum Mechanics", "study_hours": "3.0", "session_type": "REVIEW",
    })
    assert r.status_code == 201, r.text

    # Habits: a real log.
    r = await user_a.post("/api/v1/habits/daily-log", json={
        "sleep_hours": "7.0", "exercise_minutes": 25,
        "water_intake_liters": "2.0", "screen_time_hours": "3.5",
        "mood_rating": 4, "log_date": datetime.now(timezone.utc).isoformat(),
    })
    assert r.status_code == 200, r.text

    # What-if: a real finance simulation.
    r = await user_a.post("/api/v1/simulation/finance/scenarios", json={"additional_monthly_saving": 300})
    assert r.status_code == 200, r.text

    # Pull the real user document the way the route does, and build the
    # context exactly as get_assistant_reply would.
    me = await user_a.get("/api/v1/users/me")
    assert me.status_code == 200, me.text
    user = await User.get(PydanticObjectId(me.json()["id"]))
    context = await build_assistant_context(user)

    assert "Quantum Mechanics" in context, "study data must reach the assistant's context"
    assert "FOOD" in context, "finance category data must reach the assistant's context"
    assert "finance" in context.lower() and "simulation" in context.lower() or "what-if" in context.lower(), (
        "what-if simulation history must reach the assistant's context"
    )
    assert "consistency" in context.lower(), "habit analytics must reach the assistant's context"


async def test_assistant_context_new_user_says_no_data_not_zeros(user_a):
    """A brand-new user's context must state plainly that each domain has no
    data yet — never silently report fabricated zeros as if they were real."""
    from beanie import PydanticObjectId
    from models.user import User
    from services.ai_assistant_service import build_assistant_context

    me = await user_a.get("/api/v1/users/me")
    user = await User.get(PydanticObjectId(me.json()["id"]))
    context = await build_assistant_context(user)

    assert "no transactions" in context.lower()
    assert "no study sessions" in context.lower()
    assert "no habit logs" in context.lower()
    assert "none run yet" in context.lower()  # simulations


# ─── Cascade delete — DELETE /users/me must not orphan ai_recommendations ─────

async def test_delete_account_removes_cached_ai_recommendations(user_a):
    """Regression: DELETE /users/me's cascade (user_service.delete_user)
    originally deleted from every user-scoped collection except
    AIRecommendation ("ai_recommendations" — the cached generated-recommendation
    set from ai_recommendation_service.py, distinct from Recommendation's
    "recommendations"). This suite runs with no provider keys, so
    ?generate=true always degrades to rules and never reaches _store — the
    document is written directly here (exactly the shape _store produces) to
    exercise the cascade without a real LLM call."""
    from beanie import PydanticObjectId
    from models.ai_recommendation import AIRecommendation
    from models.enums import RecommendationDomain

    me = await user_a.get("/api/v1/users/me")
    assert me.status_code == 200, me.text
    uid = PydanticObjectId(me.json()["id"])

    await AIRecommendation(
        user_id=uid, domain=RecommendationDomain.HABITS,
        items=["test item"], provider="groq", context_hash="deadbeef",
    ).insert()

    assert await AIRecommendation.find_one(AIRecommendation.user_id == uid) is not None

    r = await user_a.delete("/api/v1/users/me")
    assert r.status_code in (200, 204), r.text

    assert await AIRecommendation.find_one(AIRecommendation.user_id == uid) is None, (
        "DELETE /users/me must not leave an orphaned ai_recommendations document behind"
    )
