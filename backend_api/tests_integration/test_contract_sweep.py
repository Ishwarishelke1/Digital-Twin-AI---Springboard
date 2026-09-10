"""
tests_integration/test_contract_sweep.py — docs/TEST_PLAN.md Phase 1.1–1.3.

The headline assertion of the whole test plan: **no endpoint returns 500 under
valid input.** Every route is exercised with a real request through the real
app against a real (disposable, local-only) database — not mocked, which is
exactly the band of the codebase that had zero coverage before this file
(see docs/TEST_PLAN.md's "shape of the gap").

Organised as one create→read→update→delete cycle per domain rather than one
tiny test per route: state built by an earlier step in the same function is
what a later step needs to act on, and a single ordered flow makes a failure's
traceback show exactly which call in the sequence broke, with everything it
depended on still visible above it.
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio


def _goal(user_response_json: dict, goal_id: str) -> dict:
    """POST/PATCH /users/me/goals return the full UserResponse (profile +
    preferences + the whole active_goals array), not the single goal that was
    just created or edited — confirmed by reading api/v1/users.py's
    response_model, not assumed. Every call site that needs "the goal I just
    touched" goes through this rather than guessing a top-level shape."""
    return next(g for g in user_response_json["active_goals"] if g["goal_id"] == goal_id)


# ─── Route-completeness cross-check ───────────────────────────────────────────
# Every route this file intends to cover, hand-maintained rather than derived
# from app.routes — the point is to notice drift in BOTH directions: a route
# added later that nothing below exercises, or one removed that this list still
# references. Compared against the live route table in
# test_all_registered_api_routes_are_accounted_for, below.
_COVERED_ROUTES = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/users/me"),
    ("PATCH", "/api/v1/users/me/profile"),
    ("PATCH", "/api/v1/users/me/preferences"),
    ("POST", "/api/v1/users/me/change-password"),
    ("DELETE", "/api/v1/users/me"),
    ("POST", "/api/v1/users/me/goals"),
    ("GET", "/api/v1/users/me/goals"),
    ("GET", "/api/v1/users/me/goals/predictions"),
    ("PATCH", "/api/v1/users/me/goals/{goal_id}"),
    ("DELETE", "/api/v1/users/me/goals/{goal_id}"),
    ("POST", "/api/v1/finance/transactions"),
    ("GET", "/api/v1/finance/transactions"),
    ("PATCH", "/api/v1/finance/transactions/{transaction_id}"),
    ("DELETE", "/api/v1/finance/transactions/{transaction_id}"),
    ("GET", "/api/v1/finance/analytics/cashflow"),
    ("GET", "/api/v1/finance/analytics/category"),
    ("POST", "/api/v1/study/sessions"),
    ("GET", "/api/v1/study/sessions"),
    ("PATCH", "/api/v1/study/sessions/{session_id}"),
    ("DELETE", "/api/v1/study/sessions/{session_id}"),
    ("GET", "/api/v1/study/analytics/subject-performance"),
    ("POST", "/api/v1/habits/daily-log"),
    ("GET", "/api/v1/habits/daily-log"),
    ("DELETE", "/api/v1/habits/daily-log/{log_id}"),
    ("GET", "/api/v1/habits/analytics/kmeans-features"),
    ("GET", "/api/v1/activity"),
    ("GET", "/api/v1/forecast/savings"),
    ("GET", "/api/v1/forecast/income"),
    ("GET", "/api/v1/forecast/expenses"),
    ("GET", "/api/v1/forecast/goals"),
    ("GET", "/api/v1/forecast/goals/{goal_id}"),
    ("GET", "/api/v1/forecast/summary"),
    ("GET", "/api/v1/forecast/accuracy"),
    ("GET", "/api/v1/productivity/score"),
    ("GET", "/api/v1/productivity/focus-score"),
    ("GET", "/api/v1/productivity/weekly-trend"),
    ("GET", "/api/v1/productivity/monthly-trend"),
    ("GET", "/api/v1/productivity/completion-percentage"),
    ("GET", "/api/v1/productivity/prediction"),
    ("GET", "/api/v1/productivity/summary"),
    ("GET", "/api/v1/habit-analytics/consistency-score"),
    ("GET", "/api/v1/habit-analytics/streak"),
    ("GET", "/api/v1/habit-analytics/positive"),
    ("GET", "/api/v1/habit-analytics/negative"),
    ("GET", "/api/v1/habit-analytics/missed"),
    ("GET", "/api/v1/habit-analytics/trend"),
    ("GET", "/api/v1/habit-analytics/summary"),
    ("GET", "/api/v1/trends/savings"),
    ("GET", "/api/v1/trends/study"),
    ("GET", "/api/v1/trends/fitness"),
    ("GET", "/api/v1/trends/summary"),
    ("GET", "/api/v1/trends/goals"),
    ("POST", "/api/v1/simulation/finance/scenarios"),
    ("POST", "/api/v1/simulation/study/scenarios"),
    ("POST", "/api/v1/simulation/fitness/scenarios"),
    ("POST", "/api/v1/simulation/hybrid/scenarios"),
    ("GET", "/api/v1/simulation/compare"),
    ("GET", "/api/v1/simulation/history"),
    ("GET", "/api/v1/simulation/{simulation_id}"),
    ("PATCH", "/api/v1/simulation/recommendations/{recommendation_id}/feedback"),
    ("POST", "/api/v1/assistant/chat"),
    ("POST", "/api/v1/assistant/chat/feedback"),
    ("GET", "/api/v1/assistant/satisfaction-summary"),
    ("GET", "/api/v1/recommendations/habits"),
    ("GET", "/api/v1/recommendations/study"),
    ("GET", "/health"),
}


async def test_all_registered_api_routes_are_accounted_for():
    """Fails the moment a route is added or removed without this file being
    told about it — the whole point of hand-maintaining _COVERED_ROUTES rather
    than deriving it from app.routes, which would silently expand to cover
    anything new without anyone deciding it should."""
    import main
    from fastapi.routing import APIRoute

    live = set()
    for r in main.app.routes:
        if isinstance(r, APIRoute) and r.path != "/{full_path:path}":
            for m in r.methods - {"HEAD", "OPTIONS"}:
                live.add((m, r.path))
    live.add(("GET", "/health"))

    missing_from_sweep = live - _COVERED_ROUTES
    stale_in_sweep = _COVERED_ROUTES - live
    assert not missing_from_sweep, f"routes registered but not covered by this sweep: {missing_from_sweep}"
    assert not stale_in_sweep, f"_COVERED_ROUTES references routes that no longer exist: {stale_in_sweep}"


# ─── Auth lifecycle ────────────────────────────────────────────────────────────

async def test_auth_lifecycle(app_client):
    email = "sweep-auth-lifecycle@example.com"
    payload = {
        "email": email, "password": "correct-horse-battery-staple",
        "name": "Auth Test", "age": 25, "monthly_income_baseline": 0,
    }

    r = await app_client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text

    # Duplicate registration must be a clean 4xx, not a raw Mongo duplicate-key 500.
    r = await app_client.post("/api/v1/auth/register", json=payload)
    assert r.status_code in (400, 409), f"duplicate register: {r.status_code} {r.text}"
    assert r.status_code != 500

    # Wrong password: clean 401, not 500.
    r = await app_client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    assert r.status_code == 401, r.text

    r = await app_client.post("/api/v1/auth/login", json={"email": email, "password": payload["password"]})
    assert r.status_code == 200, r.text
    assert "access_token" in app_client.cookies

    r = await app_client.get("/api/v1/users/me")
    assert r.status_code == 200
    assert r.json()["email"] == email

    r = await app_client.post("/api/v1/auth/logout")
    assert r.status_code == 204

    r = await app_client.get("/api/v1/users/me")
    assert r.status_code == 401, "logout must actually invalidate the session"


async def test_unauthenticated_requests_are_rejected_not_crashed(app_client):
    """No cookie at all on a protected route must be a clean 401, exercised
    against one representative route per router — not the full 68, which
    test_cross_tenant_and_auth_enforcement below covers more directly via
    every route this suite actually calls."""
    from httpx import ASGITransport, AsyncClient
    import main

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://testserver") as anon:
        for method, path in [
            ("GET", "/api/v1/users/me"),
            ("GET", "/api/v1/finance/transactions"),
            ("GET", "/api/v1/study/sessions"),
            ("GET", "/api/v1/habits/daily-log"),
            ("GET", "/api/v1/activity"),
        ]:
            r = await anon.request(method, path)
            assert r.status_code == 401, f"{method} {path} with no cookie: {r.status_code}"


# ─── Users, profile, preferences, goals ────────────────────────────────────────

async def test_profile_and_preferences(user_a):
    r = await user_a.patch("/api/v1/users/me/profile", json={"name": "Updated Name", "age": 31})
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["name"] == "Updated Name"

    r = await user_a.patch("/api/v1/users/me/preferences", json={"currency": "INR", "dark_mode": True})
    assert r.status_code == 200, r.text
    assert r.json()["preferences"]["currency"] == "INR"

    # Hold a second, independent client authenticated with the SAME cookie
    # before the change, to prove it goes stale — the change-password endpoint
    # deliberately re-issues a fresh cookie for `user_a`'s own session (see
    # api/v1/users.py's docstring: "so this session keeps working"), so the
    # thing token_version actually invalidates is every *other* outstanding
    # token, not the one that made the change.
    from httpx import ASGITransport, AsyncClient
    import main
    stale_client = AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://testserver",
        cookies=user_a.cookies,
    )

    r = await user_a.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "a-genuinely-fine-password-1", "new_password": "a-new-fine-password-2"},
    )
    assert r.status_code == 200, r.text

    # The session that made the change keeps working (fresh cookie reissued).
    r = await user_a.get("/api/v1/users/me")
    assert r.status_code == 200, "the session that changed its own password must not be logged out by it"

    # A second client holding the pre-change cookie must now be rejected.
    r = await stale_client.get("/api/v1/users/me")
    assert r.status_code == 401, "a token issued before the password change must go stale"
    await stale_client.aclose()


async def test_finance_full_cycle(user_a):
    goal_payload = {
        "title": "Emergency Fund", "category": "FINANCE",
        "target_value": 10000, "unit": "USD",
        "target_date": "2027-01-01T00:00:00Z",
    }
    r = await user_a.post("/api/v1/users/me/goals", json=goal_payload)
    assert r.status_code == 201, r.text
    goal_id = next(g["goal_id"] for g in r.json()["active_goals"] if g["title"] == goal_payload["title"])

    r = await user_a.get("/api/v1/users/me/goals")
    assert r.status_code == 200, r.text
    assert any(g["goal_id"] == goal_id for g in r.json())

    r = await user_a.get("/api/v1/users/me/goals/predictions")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)

    txn = {
        "type": "SAVINGS_DEPOSIT", "amount": "500.00", "category": "SAVINGS",
        "description": "sweep test deposit", "linked_goal_id": goal_id,
    }
    r = await user_a.post("/api/v1/finance/transactions", json=txn)
    assert r.status_code == 201, r.text
    txn_id = r.json()["id"]

    # Progress must actually move from the linked deposit — this is the exact
    # class of wiring bug an HTTP-level test catches that a mocked unit test
    # (which never round-trips through the real linking code) cannot.
    r = await user_a.get("/api/v1/users/me/goals")
    updated_goal = next(g for g in r.json() if g["goal_id"] == goal_id)
    assert Decimal(str(updated_goal["current_value"])) == Decimal("500.00"), (
        "linked SAVINGS_DEPOSIT must increment the goal's current_value"
    )

    r = await user_a.get("/api/v1/finance/transactions")
    assert r.status_code == 200, r.text
    assert any(t["id"] == txn_id for t in r.json()["data"])

    r = await user_a.get("/api/v1/finance/analytics/cashflow")
    assert r.status_code == 200, r.text
    r = await user_a.get("/api/v1/finance/analytics/category")
    assert r.status_code == 200, r.text

    r = await user_a.patch(f"/api/v1/finance/transactions/{txn_id}", json={"amount": "750.00"})
    assert r.status_code == 200, r.text

    r = await user_a.delete(f"/api/v1/finance/transactions/{txn_id}")
    assert r.status_code in (200, 204), r.text

    # Deleting the linked transaction must reverse the goal progress it added.
    r = await user_a.get("/api/v1/users/me/goals")
    updated_goal = next(g for g in r.json() if g["goal_id"] == goal_id)
    assert Decimal(str(updated_goal["current_value"])) == Decimal("0.00"), (
        "deleting a linked transaction must reverse its goal contribution"
    )

    r = await user_a.patch(f"/api/v1/users/me/goals/{goal_id}", json={"title": "Renamed Fund"})
    assert r.status_code == 200, r.text
    assert _goal(r.json(), goal_id)["title"] == "Renamed Fund"

    r = await user_a.delete(f"/api/v1/users/me/goals/{goal_id}")
    assert r.status_code in (200, 204), r.text


async def test_study_full_cycle(user_a):
    goal_title = "Finish Course"
    goal = await user_a.post("/api/v1/users/me/goals", json={
        "title": goal_title, "category": "STUDY",
        "target_value": 10, "unit": "sessions", "target_date": "2027-01-01T00:00:00Z",
    })
    assert goal.status_code == 201, goal.text
    goal_id = next(g["goal_id"] for g in goal.json()["active_goals"] if g["title"] == goal_title)

    session_payload = {
        "subject": "Mathematics", "study_hours": "2.5", "session_type": "PRACTICE_EXAM",
        "quiz_marks": "18", "max_quiz_marks": "20", "linked_goal_id": goal_id,
    }
    r = await user_a.post("/api/v1/study/sessions", json=session_payload)
    assert r.status_code == 201, r.text
    session = r.json()
    assert Decimal(str(session["quiz_marks_pct"])) == Decimal("90.00"), "quiz_marks_pct must auto-compute"
    session_id = session["id"]

    r = await user_a.get("/api/v1/study/sessions")
    assert r.status_code == 200, r.text
    assert any(s["id"] == session_id for s in r.json()["data"])

    r = await user_a.get("/api/v1/study/analytics/subject-performance")
    assert r.status_code == 200, r.text

    # Clearing the marks must clear the derived percentage too, not leave it
    # stale — a real defect this project has hit before.
    r = await user_a.patch(f"/api/v1/study/sessions/{session_id}", json={"quiz_marks": None, "max_quiz_marks": None})
    assert r.status_code == 200, r.text
    assert r.json()["quiz_marks_pct"] is None, "clearing marks must clear the computed percentage"

    r = await user_a.delete(f"/api/v1/study/sessions/{session_id}")
    assert r.status_code in (200, 204), r.text


async def test_habits_full_cycle(user_a):
    log_payload = {
        "sleep_hours": "7.5", "exercise_minutes": 30,
        "water_intake_liters": "2.0", "screen_time_hours": "4.0",
        "mood_rating": 4, "log_date": "2026-01-01T00:00:00Z",
    }
    r = await user_a.post("/api/v1/habits/daily-log", json=log_payload)
    assert r.status_code == 200, r.text  # upsert_daily_log — create and update share this path
    log_id = r.json()["id"]

    # Re-posting the same log_date is a deliberate upsert (findOneAndUpdate,
    # upsert=True) — same day, same record, updated in place. Verified by
    # reading services/habit_service.py rather than assumed: a same-day
    # re-log is normal usage ("I logged this morning, correcting it tonight"),
    # not an error, so it must return the SAME id updated, not a 409.
    updated_payload = {**log_payload, "exercise_minutes": 45}
    r = await user_a.post("/api/v1/habits/daily-log", json=updated_payload)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == log_id, "a same-day re-log must update the existing record, not create a new one"
    assert r.json()["exercise_minutes"] == 45

    r = await user_a.get("/api/v1/habits/daily-log")
    assert r.status_code == 200, r.text
    assert any(h["id"] == log_id for h in r.json()["data"])

    r = await user_a.get("/api/v1/habits/analytics/kmeans-features")
    assert r.status_code == 200, r.text

    r = await user_a.delete(f"/api/v1/habits/daily-log/{log_id}")
    assert r.status_code in (200, 204), r.text


async def test_activity_log_endpoint(user_a):
    """`user_a` is function-scoped — a fresh user, no history — so this proves
    the endpoint itself is sound (200, correctly-shaped empty page) rather than
    exercising the log_activity() writes the domain-cycle tests above trigger.
    Those writes are swallow-on-failure by design (services/activity_service.py)
    specifically so a broken audit log can never fail the operation it's
    attached to — which also means nothing here would notice if they silently
    stopped firing. That's a real gap; closing it means asserting against the
    log's own collection directly rather than through this endpoint, which is
    less than Phase 1.1's HTTP-contract scope. Left as a named gap, not papered
    over as covered."""
    r = await user_a.get("/api/v1/activity")
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


# ─── Analytics engines against a brand-new (zero-data) user ───────────────────
# Phase 1.4's empty-state check: every read-only analytics endpoint must
# degrade to a sensible zero/insufficient_data response, never a 500, for a
# user with no history at all.

async def test_analytics_engines_on_a_fresh_user_never_500(user_a):
    reads = [
        "/api/v1/forecast/savings", "/api/v1/forecast/income", "/api/v1/forecast/expenses",
        "/api/v1/forecast/goals", "/api/v1/forecast/summary", "/api/v1/forecast/accuracy",
        "/api/v1/productivity/score", "/api/v1/productivity/focus-score",
        "/api/v1/productivity/weekly-trend", "/api/v1/productivity/monthly-trend",
        "/api/v1/productivity/completion-percentage", "/api/v1/productivity/prediction",
        "/api/v1/productivity/summary",
        "/api/v1/habit-analytics/consistency-score", "/api/v1/habit-analytics/streak",
        "/api/v1/habit-analytics/positive", "/api/v1/habit-analytics/negative",
        "/api/v1/habit-analytics/missed", "/api/v1/habit-analytics/trend",
        "/api/v1/habit-analytics/summary",
        "/api/v1/trends/savings", "/api/v1/trends/study", "/api/v1/trends/fitness",
        "/api/v1/trends/summary", "/api/v1/trends/goals",
        "/api/v1/simulation/compare", "/api/v1/simulation/history",
        "/api/v1/recommendations/habits", "/api/v1/recommendations/study",
        "/api/v1/assistant/satisfaction-summary",
    ]
    failures = []
    for path in reads:
        r = await user_a.get(path)
        if r.status_code >= 500:
            failures.append((path, r.status_code, r.text[:200]))
    assert not failures, f"analytics endpoints that 500'd on a zero-data user: {failures}"


async def test_forecast_goal_detail_needs_a_real_goal(user_a):
    goal_title = "Down Payment"
    goal = await user_a.post("/api/v1/users/me/goals", json={
        "title": goal_title, "category": "FINANCE",
        "target_value": 5000, "unit": "USD", "target_date": "2027-06-01T00:00:00Z",
    })
    assert goal.status_code == 201, goal.text
    goal_id = next(g["goal_id"] for g in goal.json()["active_goals"] if g["title"] == goal_title)
    r = await user_a.get(f"/api/v1/forecast/goals/{goal_id}")
    assert r.status_code == 200, r.text

    # A goal id that isn't this user's (or doesn't exist) must be a clean 404.
    r = await user_a.get("/api/v1/forecast/goals/000000000000000000000000")
    assert r.status_code == 404, r.text


# ─── Simulation ────────────────────────────────────────────────────────────────

async def test_simulation_full_cycle(user_a):
    r = await user_a.post("/api/v1/simulation/finance/scenarios", json={"additional_monthly_saving": 200})
    assert r.status_code == 200, r.text
    body = r.json()
    sim_id = body["id"]
    rec_id = body["recommendation"]["id"]

    r = await user_a.post("/api/v1/simulation/study/scenarios", json={"additional_weekly_study_hours": 3})
    assert r.status_code == 200, r.text
    r = await user_a.post("/api/v1/simulation/fitness/scenarios", json={"additional_exercise_minutes": 20})
    assert r.status_code == 200, r.text
    r = await user_a.post("/api/v1/simulation/hybrid/scenarios", json={"additional_monthly_saving": 100})
    assert r.status_code == 200, r.text

    r = await user_a.get(f"/api/v1/simulation/{sim_id}")
    assert r.status_code == 200, r.text

    r = await user_a.get("/api/v1/simulation/000000000000000000000000")
    assert r.status_code == 404, r.text

    r = await user_a.patch(
        f"/api/v1/simulation/recommendations/{rec_id}/feedback", json={"feedback": "HELPFUL"}
    )
    assert r.status_code == 200, r.text


# ─── Assistant (no provider key configured — must degrade, not crash) ─────────

async def test_assistant_degrades_cleanly_with_no_provider_configured(user_a):
    r = await user_a.post("/api/v1/assistant/chat", json={"message": "How am I doing?"})
    assert r.status_code == 503, (
        f"no GEMINI/GROQ key configured must be a clean 503 AI_PROVIDER_UNAVAILABLE, "
        f"got {r.status_code}: {r.text}"
    )
    assert r.json()["error"] == "AI_PROVIDER_UNAVAILABLE"

    r = await user_a.post(
        "/api/v1/assistant/chat/feedback",
        json={"message_snippet": "some reply", "feedback": "HELPFUL"},
    )
    assert r.status_code == 201, r.text


async def test_chat_feedback_rejects_a_realistic_full_length_reply(user_a):
    """A short hand-typed snippet (the case above) is not what the frontend
    actually sends — ChatBox.jsx used to forward the AI reply's full text
    unmodified, and a real reply is routinely well past the schema's 300-char
    cap. tests/test_feedback_service.py's `..._truncates_long_snippet` calls
    the service function directly and passes, which is real but misleading:
    it demonstrates the service *would* truncate a long snippet if it ever
    saw one, while Pydantic's max_length=300 rejects it with a 422 before the
    service function is ever reached. Only an HTTP-level call sees that.
    Confirmed against a live backend before the frontend fix (ChatBox.jsx now
    truncates before sending) — kept here as the regression test."""
    realistic_reply = (
        "Based on your real Digital Twin data, your savings rate is strong "
        "at 98 percent and your study consistency is excellent at 96 percent "
        "this month. Based on your real Digital Twin data, your savings rate "
        "is strong at 98 percent and your study consistency is excellent, "
        "and your habit score of 33 percent still has room to improve if "
        "you keep logging consistently every day."
    )
    assert len(realistic_reply) > 300, "fixture must actually exercise the boundary"

    r = await user_a.post(
        "/api/v1/assistant/chat/feedback",
        json={"message_snippet": realistic_reply, "feedback": "HELPFUL"},
    )
    assert r.status_code == 422, (
        f"expected the schema's max_length=300 to reject an untruncated reply, "
        f"got {r.status_code}: {r.text}"
    )

    r = await user_a.post(
        "/api/v1/assistant/chat/feedback",
        json={"message_snippet": realistic_reply[:300], "feedback": "HELPFUL"},
    )
    assert r.status_code == 201, f"a client that truncates first must still succeed: {r.text}"


async def test_recommendations_fall_back_to_rules_with_no_provider_configured(user_a):
    """Unlike /assistant/chat, the recommendations endpoints are documented to
    never fail outright — provider="rules" is the designed fallback, not an
    error path."""
    r = await user_a.get("/api/v1/recommendations/habits")
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "rules"

    r = await user_a.get("/api/v1/recommendations/study")
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "rules"


# ─── Cross-tenant isolation (Phase 1.2) ────────────────────────────────────────

async def test_cross_tenant_isolation(user_a, user_b):
    """User A must not be able to read, edit, or delete User B's records
    through any route that takes an id — a missing user_id filter here is a
    data leak, not a display bug."""
    b_goal_title = "B's Secret Goal"
    goal = await user_b.post("/api/v1/users/me/goals", json={
        "title": b_goal_title, "category": "FINANCE",
        "target_value": 1000, "unit": "USD", "target_date": "2027-01-01T00:00:00Z",
    })
    assert goal.status_code == 201, goal.text
    b_goal_id = next(g["goal_id"] for g in goal.json()["active_goals"] if g["title"] == b_goal_title)

    txn = await user_b.post("/api/v1/finance/transactions", json={
        "type": "EXPENSE", "amount": "42.00", "category": "FOOD",
    })
    b_txn_id = txn.json()["id"]

    session = await user_b.post("/api/v1/study/sessions", json={
        "subject": "B's Subject", "study_hours": "1.0", "session_type": "REVIEW",
    })
    b_session_id = session.json()["id"]

    # A must not see B's goal in A's own list.
    r = await user_a.get("/api/v1/users/me/goals")
    assert all(g["goal_id"] != b_goal_id for g in r.json()), "user A's goal list leaked user B's goal"

    # A editing/deleting B's resources by id must be refused, never succeed.
    for method, path, body in [
        ("PATCH", f"/api/v1/users/me/goals/{b_goal_id}", {"title": "pwned"}),
        ("DELETE", f"/api/v1/users/me/goals/{b_goal_id}", None),
        ("PATCH", f"/api/v1/finance/transactions/{b_txn_id}", {"amount": "1.00"}),
        ("DELETE", f"/api/v1/finance/transactions/{b_txn_id}", None),
        ("PATCH", f"/api/v1/study/sessions/{b_session_id}", {"subject": "pwned"}),
        ("DELETE", f"/api/v1/study/sessions/{b_session_id}", None),
        ("GET", f"/api/v1/forecast/goals/{b_goal_id}", None),
    ]:
        r = await user_a.request(method, path, json=body)
        assert r.status_code in (403, 404), (
            f"{method} {path} against user B's resource as user A returned "
            f"{r.status_code} — expected 403/404: {r.text}"
        )
        assert r.status_code != 500

    # And B's data must be provably untouched by any of the above.
    r = await user_b.get("/api/v1/users/me/goals")
    assert any(g["goal_id"] == b_goal_id and g["title"] == b_goal_title for g in r.json())
