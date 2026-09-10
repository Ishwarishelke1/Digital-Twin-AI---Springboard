"""
tests/test_user_service.py — Unit tests for services/user_service.py.

Two layers, mirroring tests/test_forecast_service.py's style:
1. Pure-function tests for the digital-twin-state helpers (savings_rate_pct /
   emergency_fund_months) — no mocking, no DB.
2. A service-level test for change_password's wrong-current-password rejection,
   patching out the only I/O call (the raw motor find_one for password_hash) with
   AsyncMock, and constructing a real in-memory User instance (Beanie Documents are
   plain Pydantic models — no DB connection needed unless .insert()/.get() is called).
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from core.exceptions import AuthenticationError, ConflictError
from core.security import hash_password
from models.activity import UserActivity
from models.ai_recommendation import AIRecommendation
from models.enums import Gender, RiskTolerance
from models.feedback import AssistantFeedback
from models.finance import FinancialRecord
from models.habit import HabitTracking
from models.simulation import Recommendation, Simulation
from models.study import StudyActivity
from models.user import ActiveGoal, Profile, User
from schemas.auth_schema import ChangePasswordRequest, RegisterRequest
from schemas.user_schema import ActiveGoalUpdateRequest
from services.user_service import (
    _emergency_fund_months,
    _savings_rate_pct,
    authenticate_user,
    change_password,
    create_user,
    delete_active_goal,
    delete_user,
    update_active_goal,
)


def test_savings_rate_pct_normal_case():
    assert _savings_rate_pct(monthly_savings=2000, monthly_income=10000) == 20.0


def test_savings_rate_pct_zero_income_is_zero():
    assert _savings_rate_pct(monthly_savings=500, monthly_income=0) == 0.0


def test_savings_rate_pct_negative_savings_clamped_to_zero():
    assert _savings_rate_pct(monthly_savings=-500, monthly_income=10000) == 0.0


def test_savings_rate_pct_capped_at_100():
    assert _savings_rate_pct(monthly_savings=15000, monthly_income=10000) == 100.0


def test_emergency_fund_months_normal_case():
    # 24000 saved, spending 6000/month on average -> 4 months of runway
    assert _emergency_fund_months(net_savings_total=24000, average_monthly_expense=6000) == 4.0


def test_emergency_fund_months_zero_expense_is_zero():
    assert _emergency_fund_months(net_savings_total=5000, average_monthly_expense=0) == 0.0


def test_emergency_fund_months_negative_net_savings_clamped_to_zero():
    # Spent more than earned over the window -> no runway, not a negative number of months.
    assert _emergency_fund_months(net_savings_total=-1000, average_monthly_expense=2000) == 0.0


# ─── change_password ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current_password():
    correct_hash = hash_password("CorrectPass123")
    user = User.model_construct(
        email="pwtest@example.com",
        password_hash=correct_hash,
        profile=Profile(name="PW Test", age=30),
    )
    user.id = PydanticObjectId("507f1f77bcf86cd799439011")

    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value={"password_hash": correct_hash})

    with patch("services.user_service.User.get_motor_collection", return_value=mock_collection):
        with pytest.raises(AuthenticationError):
            await change_password(
                user,
                ChangePasswordRequest(current_password="WrongPassword", new_password="NewPass123"),
            )


@pytest.mark.asyncio
async def test_change_password_happy_path_updates_hash_and_bumps_token_version():
    old_hash = hash_password("OldPass123")
    user = User.model_construct(
        email="pwtest2@example.com", password_hash=old_hash,
        profile=Profile(name="PW Test 2", age=30), token_version=0,
    )
    user.id = PydanticObjectId("507f1f77bcf86cd799439012")

    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value={"password_hash": old_hash})

    with patch("services.user_service.User.get_motor_collection", return_value=mock_collection), \
         patch.object(User, "update", new=AsyncMock()) as mock_update, \
         patch.object(User, "sync", new=AsyncMock()) as mock_sync:
        await change_password(
            user, ChangePasswordRequest(current_password="OldPass123", new_password="BrandNewPass456")
        )

    mock_update.assert_awaited_once()
    mock_sync.assert_awaited_once()


# ─── create_user ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user_normal_registration():
    payload = RegisterRequest(email="new@example.com", password="SecurePass123", name="New User", age=28)

    with patch.object(User, "find_one", new=AsyncMock(return_value=None)), \
         patch.object(User, "get_motor_collection", return_value=MagicMock()), \
         patch.object(User, "insert", new=AsyncMock()):
        user = await create_user(payload)

    assert user.email == "new@example.com"
    assert user.profile.name == "New User"
    assert user.password_hash != "SecurePass123"  # actually hashed, not stored raw


@pytest.mark.asyncio
async def test_create_user_defaults_gender_none_and_risk_tolerance_moderate():
    """When signup doesn't send gender/risk_tolerance, the profile still gets
    RiskTolerance's schema default (MODERATE) — not silently unset."""
    payload = RegisterRequest(email="defaults@example.com", password="SecurePass123", name="Defaults User", age=28)

    with patch.object(User, "find_one", new=AsyncMock(return_value=None)), \
         patch.object(User, "get_motor_collection", return_value=MagicMock()), \
         patch.object(User, "insert", new=AsyncMock()):
        user = await create_user(payload)

    assert user.profile.gender is None
    assert user.profile.risk_tolerance == RiskTolerance.MODERATE


@pytest.mark.asyncio
async def test_create_user_full_profile_fields_pass_through():
    """Regression test: signup now covers every Profile field (gender,
    risk_tolerance) up front, not just name/age/occupation/income."""
    payload = RegisterRequest(
        email="full@example.com", password="SecurePass123", name="Full Profile User", age=30,
        gender=Gender.FEMALE, occupation="Engineer", monthly_income_baseline=5000.0,
        risk_tolerance=RiskTolerance.AGGRESSIVE,
    )

    with patch.object(User, "find_one", new=AsyncMock(return_value=None)), \
         patch.object(User, "get_motor_collection", return_value=MagicMock()), \
         patch.object(User, "insert", new=AsyncMock()):
        user = await create_user(payload)

    assert user.profile.gender == Gender.FEMALE
    assert user.profile.occupation == "Engineer"
    assert user.profile.monthly_income_baseline == Decimal("5000.0")
    assert user.profile.risk_tolerance == RiskTolerance.AGGRESSIVE


@pytest.mark.asyncio
async def test_create_user_duplicate_email_rejected():
    payload = RegisterRequest(email="taken@example.com", password="SecurePass123", name="Dupe", age=28)
    existing = User.model_construct(email="taken@example.com", password_hash="x", profile=Profile(name="Existing User", age=25))

    with patch.object(User, "find_one", new=AsyncMock(return_value=existing)):
        with pytest.raises(ConflictError):
            await create_user(payload)


# ─── authenticate_user ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authenticate_user_correct_password():
    correct_hash = hash_password("MyPassword123")
    stored_user = User.model_construct(email="auth@example.com", password_hash=correct_hash, profile=Profile(name="Auth", age=25))
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value={"password_hash": correct_hash, "email": "auth@example.com"})

    with patch.object(User, "get_motor_collection", return_value=mock_collection), \
         patch.object(User, "find_one", new=AsyncMock(return_value=stored_user)):
        user = await authenticate_user("auth@example.com", "MyPassword123")
    assert user.email == "auth@example.com"


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password_rejected():
    correct_hash = hash_password("MyPassword123")
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value={"password_hash": correct_hash, "email": "auth@example.com"})

    with patch.object(User, "get_motor_collection", return_value=mock_collection):
        with pytest.raises(AuthenticationError):
            await authenticate_user("auth@example.com", "WrongPassword")


@pytest.mark.asyncio
async def test_authenticate_user_nonexistent_email_rejected():
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value=None)

    with patch.object(User, "get_motor_collection", return_value=mock_collection):
        with pytest.raises(AuthenticationError):
            await authenticate_user("nobody@example.com", "Whatever123")


# ─── delete_user ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_user_removes_all_eight_associated_collections():
    """Regression test for cascading-delete fixes: Simulation, Recommendation,
    AssistantFeedback, and AIRecommendation (the cached generated-recommendation
    set from ai_recommendation_service.py — a distinct collection,
    "ai_recommendations", from Recommendation's "recommendations") must all be
    cleaned up alongside finance/study/habit/activity records. AIRecommendation
    was missed originally — confirmed live via a real account that had called
    GET /recommendations/habits?generate=true, then deleted: the document
    survived deletion until this fix (see docs/NEW_USER_TEST_REPORT.md)."""
    user = User.model_construct(email="todelete@example.com", password_hash="x", profile=Profile(name="Del", age=30))
    user.id = PydanticObjectId("507f1f77bcf86cd799439013")

    def _mock_find(model):
        query = MagicMock()
        query.delete = AsyncMock()
        return patch.object(model, "find", return_value=query), query

    patches_and_queries = [_mock_find(m) for m in (
        FinancialRecord, StudyActivity, HabitTracking, UserActivity, Simulation, Recommendation,
        AssistantFeedback, AIRecommendation,
    )]

    ctx_managers = [p for p, _ in patches_and_queries]
    queries = [q for _, q in patches_and_queries]

    for cm in ctx_managers:
        cm.start()
    mock_delete = patch.object(User, "delete", new=AsyncMock())
    mock_delete_obj = mock_delete.start()
    try:
        await delete_user(user)
    finally:
        for cm in ctx_managers:
            cm.stop()
        mock_delete.stop()

    for query in queries:
        query.delete.assert_awaited_once()
    mock_delete_obj.assert_awaited_once()


# ─── update_active_goal / delete_active_goal (atomicity regression) ───────────────

@pytest.mark.asyncio
async def test_update_active_goal_uses_positional_set_scoped_to_one_goal():
    goal = ActiveGoal(goal_id="goal-a", title="Goal A", category="FINANCE", target_value=1000, unit="INR", target_date="2027-01-01T00:00:00Z")
    user = User.model_construct(email="goals@example.com", password_hash="x", profile=Profile(name="Goal Owner", age=30), active_goals=[goal])
    user.id = PydanticObjectId("507f1f77bcf86cd799439014")

    mock_result = MagicMock(matched_count=1)
    mock_collection = MagicMock()
    mock_collection.update_one = AsyncMock(return_value=mock_result)

    with patch.object(User, "get_motor_collection", return_value=mock_collection), \
         patch.object(User, "sync", new=AsyncMock()):
        await update_active_goal(user, "goal-a", ActiveGoalUpdateRequest(title="Renamed Goal A"))

    call_args = mock_collection.update_one.call_args
    query_filter, update_doc = call_args[0]
    assert query_filter == {"_id": user.id, "active_goals.goal_id": "goal-a"}
    assert "active_goals.$.title" in update_doc["$set"]
    assert update_doc["$set"]["active_goals.$.status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_update_active_goal_marks_completed_when_current_reaches_target():
    goal = ActiveGoal(goal_id="goal-a", title="Goal A", category="FINANCE", target_value=1000, current_value=200, unit="INR", target_date="2027-01-01T00:00:00Z")
    user = User.model_construct(email="goals@example.com", password_hash="x", profile=Profile(name="Goal Owner", age=30), active_goals=[goal])
    user.id = PydanticObjectId("507f1f77bcf86cd799439014")

    mock_result = MagicMock(matched_count=1)
    mock_collection = MagicMock()
    mock_collection.update_one = AsyncMock(return_value=mock_result)

    with patch.object(User, "get_motor_collection", return_value=mock_collection), \
         patch.object(User, "sync", new=AsyncMock()):
        await update_active_goal(user, "goal-a", ActiveGoalUpdateRequest(current_value=Decimal("1000")))

    update_doc = mock_collection.update_one.call_args[0][1]
    assert update_doc["$set"]["active_goals.$.status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_update_active_goal_reopens_when_target_raised_above_current():
    goal = ActiveGoal(goal_id="goal-a", title="Goal A", category="FINANCE", target_value=1000, current_value=1000, unit="INR", target_date="2027-01-01T00:00:00Z")
    user = User.model_construct(email="goals@example.com", password_hash="x", profile=Profile(name="Goal Owner", age=30), active_goals=[goal])
    user.id = PydanticObjectId("507f1f77bcf86cd799439014")

    mock_result = MagicMock(matched_count=1)
    mock_collection = MagicMock()
    mock_collection.update_one = AsyncMock(return_value=mock_result)

    with patch.object(User, "get_motor_collection", return_value=mock_collection), \
         patch.object(User, "sync", new=AsyncMock()):
        await update_active_goal(user, "goal-a", ActiveGoalUpdateRequest(target_value=Decimal("2000")))

    update_doc = mock_collection.update_one.call_args[0][1]
    assert update_doc["$set"]["active_goals.$.status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_delete_active_goal_uses_pull_scoped_to_one_goal():
    goal = ActiveGoal(goal_id="goal-b", title="Goal B", category="STUDY", target_value=100, unit="hours", target_date="2027-01-01T00:00:00Z")
    user = User.model_construct(email="goals2@example.com", password_hash="x", profile=Profile(name="Goal Owner 2", age=30), active_goals=[goal])
    user.id = PydanticObjectId("507f1f77bcf86cd799439015")

    mock_collection = MagicMock()
    mock_collection.update_one = AsyncMock()

    with patch.object(User, "get_motor_collection", return_value=mock_collection), \
         patch.object(User, "sync", new=AsyncMock()):
        await delete_active_goal(user, "goal-b")

    call_args = mock_collection.update_one.call_args
    query_filter, update_doc = call_args[0]
    assert query_filter == {"_id": user.id}
    assert update_doc["$pull"] == {"active_goals": {"goal_id": "goal-b"}}


# ─── ActiveGoalResponse construction ─────────────────────────────────────────────

def test_active_goal_response_requires_status_and_accepts_completed_at():
    """Guards a real bug: api/v1/users.py's list_goals built ActiveGoalResponse
    without `status`, which is required — so GET /users/me/goals raised a
    ValidationError and returned 500 on every call. It went unnoticed because the
    frontend reads goals from GET /users/me instead of that route."""
    from datetime import datetime, timezone
    from decimal import Decimal

    import pytest as _pytest
    from pydantic import ValidationError

    from models.enums import GoalCategory, GoalStatus
    from schemas.user_schema import ActiveGoalResponse

    base = dict(
        goal_id="g1",
        title="Laptop fund",
        category=GoalCategory.FINANCE,
        target_value=Decimal("1000"),
        current_value=Decimal("1000"),
        unit="INR",
        target_date=datetime.now(timezone.utc),
        created_at=None,
    )

    with _pytest.raises(ValidationError):
        ActiveGoalResponse(**base)  # no status — must not silently succeed

    completed = datetime.now(timezone.utc)
    resp = ActiveGoalResponse(**base, status=GoalStatus.COMPLETED, completed_at=completed)
    assert resp.status is GoalStatus.COMPLETED
    assert resp.completed_at == completed

    # completed_at is optional — goals predating the field, and incomplete goals
    assert ActiveGoalResponse(**base, status=GoalStatus.ACTIVE).completed_at is None
