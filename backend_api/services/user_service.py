"""
services/user_service.py — Business logic layer for user profile management.
Python equivalent of UserRepository from backend/database/repositories/user_repository.ts.
All CRUD operations reuse Beanie's O(1) document access patterns.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from beanie import PydanticObjectId
from beanie.operators import Set, Push, Pull, Inc

from core.exceptions import NotFoundError, BusinessRuleError, ConflictError, AuthenticationError
from core.security import hash_password, verify_password
from models.user import User, Profile, ActiveGoal, DigitalTwinState, UserPreferences
from models.enums import TransactionType, GoalStatus
from models.finance import FinancialRecord
from models.study import StudyActivity
from models.habit import HabitTracking
from models.activity import UserActivity
from models.simulation import Recommendation, Simulation
from models.feedback import AssistantFeedback

from schemas.auth_schema import RegisterRequest, ChangePasswordRequest
from schemas.user_schema import ProfileUpdateRequest, ActiveGoalCreateRequest, ActiveGoalUpdateRequest, PreferencesUpdateRequest
import services.activity_service as activity_service
import services.finance_service as finance_service
import services.goal_progress_service as goal_progress_service
from services.forecast_service import forecast_service
from services.productivity_service import productivity_service
from services.habit_analytics_service import habit_analytics_service

logger = logging.getLogger("digital_twin_ai.user_service")

DIGITAL_TWIN_LOOKBACK_MONTHS = 12


# ─── Pure helpers for the two derived digital-twin fields (no I/O — unit-tested directly) ──

def _savings_rate_pct(monthly_savings: float, monthly_income: float) -> float:
    """% of income being saved. 0 if there's no income to measure against."""
    if monthly_income <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (monthly_savings / monthly_income) * 100)), 2)


def _emergency_fund_months(net_savings_total: float, average_monthly_expense: float) -> float:
    """How many months of expenses the user's net savings over the lookback window
    would cover. 0 if there's no expense history to measure against (avoids a
    meaningless division, and matches this field's pre-existing 0.0 default)."""
    if average_monthly_expense <= 0:
        return 0.0
    return round(max(0.0, net_savings_total / average_monthly_expense), 2)


async def create_user(payload: RegisterRequest) -> User:
    """Registers a new user. Raises ConflictError if email already exists."""
    existing = await User.find_one(User.email == payload.email.lower())
    if existing:
        raise ConflictError(f"An account with email '{payload.email}' already exists.")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        profile=Profile(
            name=payload.name,
            age=payload.age,
            gender=payload.gender,
            occupation=payload.occupation,
            monthly_income_baseline=Decimal(str(payload.monthly_income_baseline)),
            risk_tolerance=payload.risk_tolerance,
        ),
    )
    await user.insert()
    logger.info("User registered: %s (id=%s)", user.email, user.id)
    return user


async def authenticate_user(email: str, password: str) -> User:
    """
    Validates credentials and returns the User document.
    Equivalent to the TS pattern: findOne({email}) + bcrypt.compare().

    NOTE: password_hash is marked `exclude=True` on the Pydantic model so normal
    Beanie find_one() won't return it. We use get_motor_collection() to fetch the
    raw MongoDB document (which includes password_hash), verify the hash, then
    fetch the full Beanie User document for the authenticated session.
    This is the correct pattern for Beanie 1.26.x.
    """
    # Fetch raw document to access password_hash (excluded from Beanie model)
    collection = User.get_motor_collection()
    raw = await collection.find_one(
        {"email": email.lower()},
        {"password_hash": 1, "email": 1}
    )

    if not raw or not verify_password(password, raw.get("password_hash", "")):
        raise AuthenticationError("Incorrect email or password.")

    # Fetch full Beanie document for the authenticated session
    user = await User.find_one(User.email == email.lower())
    return user


async def change_password(user: User, payload: ChangePasswordRequest) -> User:
    """
    Verifies the current password, sets the new one, and bumps token_version in the
    same atomic update — invalidating every other outstanding session/token for this
    user (a leaked old token can no longer be used once the password it was issued
    under has been changed). The caller (api/v1/users.py) is responsible for issuing
    a fresh token for the session that just made this change, since this function's
    own update makes the token used to call it stale too.
    """
    collection = User.get_motor_collection()
    raw = await collection.find_one({"_id": user.id}, {"password_hash": 1})
    if not raw or not verify_password(payload.current_password, raw.get("password_hash", "")):
        raise AuthenticationError("Current password is incorrect.")

    new_hash = hash_password(payload.new_password)
    await user.update(
        Set({User.password_hash: new_hash, User.updated_at: datetime.now(timezone.utc)}),
        Inc({User.token_version: 1}),
    )
    await user.sync()

    logger.info("Password changed for user %s (token_version bumped).", user.id)
    await activity_service.log_activity(
        user_id=str(user.id),
        action_type="CHANGED_PASSWORD",
        entity_type="PROFILE",
        description="Changed account password"
    )
    return user


async def get_twin_context(user_id: str) -> User:
    """
    Mirrors getTwinContext() from user_repository.ts. Returns the full user aggregate:
    profile + preferences + active_goals + digital_twin_state — recomputing
    digital_twin_state live from the real forecasting/productivity/habit-analytics
    engines on every call (same "compute live, no background job" pattern already used
    by forecast_service/productivity_service/habit_analytics_service/trend_prediction_service/
    simulation_service elsewhere in this codebase) and persisting the fresh snapshot back
    onto the document, so it's accurate both in this response and for anything reading
    the User document directly. burnout_risk_cluster is intentionally left untouched —
    populating it for real requires K-Means clustering, which doesn't exist anywhere in
    this codebase yet (a separate, distinct feature, not a "wire up existing data" fix).
    """
    user = await User.get(PydanticObjectId(user_id))
    if not user:
        raise NotFoundError("User", user_id)

    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=DIGITAL_TWIN_LOOKBACK_MONTHS * 30)

    (
        savings_forecast,
        income_forecast,
        productivity_score_resp,
        performance_prediction,
        completion_pct_resp,
        habit_consistency_resp,
        habit_trend_resp,
        cashflow_items,
    ) = await asyncio.gather(
        forecast_service.forecast_monthly_savings(user_id, months_ahead=1),
        forecast_service.project_income(user_id, months_ahead=1),
        productivity_service.get_productivity_score(user_id),
        productivity_service.predict_performance(user_id, weeks_ahead=1),
        productivity_service.get_completion_percentage(user_id),
        habit_analytics_service.get_consistency_score(user_id),
        habit_analytics_service.get_habit_trend(user_id),
        finance_service.get_monthly_cashflow(user_id, lookback_start, now),
    )

    monthly_savings = float(savings_forecast.projections[0].projected_amount) if savings_forecast.projections else 0.0
    monthly_income = float(income_forecast.projections[0].projected_amount) if income_forecast.projections else 0.0
    savings_rate = _savings_rate_pct(monthly_savings, monthly_income)

    income_total = sum(float(i.total_amount) for i in cashflow_items if i.type == TransactionType.INCOME)
    expense_total = sum(float(i.total_amount) for i in cashflow_items if i.type == TransactionType.EXPENSE)
    expense_months = len({(i.year, i.month) for i in cashflow_items if i.type == TransactionType.EXPENSE})
    average_monthly_expense = expense_total / expense_months if expense_months else 0.0
    emergency_fund_months = _emergency_fund_months(income_total - expense_total, average_monthly_expense)

    active_weeks = [w for w in habit_trend_resp.weekly if w.days_logged > 0]
    lifestyle_score = active_weeks[-1].average_habit_score if active_weeks else 0.0

    update_data = {
        "digital_twin_state.savings_rate_pct": Decimal(str(savings_rate)),
        "digital_twin_state.emergency_fund_months": Decimal(str(emergency_fund_months)),
        "digital_twin_state.study_consistency_score": Decimal(str(completion_pct_resp.completion_percentage)),
        "digital_twin_state.predicted_exam_score": performance_prediction.predicted_exam_score,
        "digital_twin_state.habit_completion_rate": Decimal(str(habit_consistency_resp.consistency_score)),
        "digital_twin_state.lifestyle_score": Decimal(str(lifestyle_score)),
        "digital_twin_state.productivity_score": Decimal(str(productivity_score_resp.productivity_score)),
        "digital_twin_state.last_updated_at": now,
    }
    await user.update(Set(update_data))
    await user.sync()
    return user


async def update_profile(user: User, payload: ProfileUpdateRequest) -> User:
    """Applies a partial profile update using atomic $set operations."""
    update_data: dict = {}
    for field, value in payload.model_dump(exclude_none=True).items():
        update_data[f"profile.{field}"] = value

    if not update_data:
        return user

    update_data["updated_at"] = datetime.now(timezone.utc)
    await user.update(Set(update_data))
    await user.sync()
    logger.info("Profile updated for user: %s", user.id)
    await activity_service.log_activity(
        user_id=str(user.id),
        action_type="UPDATED_PROFILE",
        entity_type="PROFILE",
        description="Updated user profile"
    )
    return user


async def update_preferences(user: User, payload: PreferencesUpdateRequest) -> User:
    """Applies a partial preferences update."""
    update_data: dict = {}
    for field, value in payload.model_dump(exclude_none=True).items():
        update_data[f"preferences.{field}"] = value

    if not update_data:
        return user

    update_data["updated_at"] = datetime.now(timezone.utc)
    await user.update(Set(update_data))
    await user.sync()
    await activity_service.log_activity(
        user_id=str(user.id),
        action_type="UPDATED_PREFERENCES",
        entity_type="PROFILE",
        description="Updated user preferences"
    )
    return user


async def add_active_goal(user: User, payload: ActiveGoalCreateRequest) -> User:
    """
    Atomically adds a new goal, enforcing the hard cap of 30 items.
    Mirrors addActiveGoal() from user_repository.ts.
    """
    if len(user.active_goals) >= 30:
        raise BusinessRuleError(
            "Active goals array hard cap reached (30 items). "
            "Please complete or archive existing targets first."
        )

    new_goal = ActiveGoal(
        title=payload.title,
        category=payload.category,
        target_value=payload.target_value,
        unit=payload.unit,
        target_date=payload.target_date,
    )

    await user.update(Push({User.active_goals: new_goal}))
    await user.sync()
    logger.info("Goal '%s' added for user %s", new_goal.title, user.id)
    await activity_service.log_activity(
        user_id=str(user.id),
        action_type="CREATED_GOAL",
        entity_type="PROFILE",
        entity_id=new_goal.goal_id,
        description=f"Added new goal '{new_goal.title}'"
    )
    return user

async def update_active_goal(user: User, goal_id: str, payload: ActiveGoalUpdateRequest) -> User:
    """
    Atomically updates one goal within the active_goals array using the positional
    `$` operator, instead of reading the whole User document into memory and calling
    `.save()` — a full-document overwrite would silently lose a concurrent edit to a
    *different* goal made by another in-flight request between this read and write.
    """
    goal = next((g for g in user.active_goals if g.goal_id == goal_id), None)
    if not goal:
        raise NotFoundError("Goal", goal_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return user

    from bson.decimal128 import Decimal128

    # Raw Motor calls bypass Beanie's Decimal <-> Decimal128 BSON encoding (Beanie only
    # applies it via the ODM-level save()/update() path), so convert explicitly here —
    # same pattern already used in habit_service.upsert_daily_log for the same reason.
    set_fields = {
        f"active_goals.$.{key}": Decimal128(str(value)) if isinstance(value, Decimal) else value
        for key, value in update_data.items()
    }

    # Auto-derive status from current_value vs target_value on every update, using
    # whichever of the two this payload touches merged with the goal's existing values —
    # covers editing current_value alone (progress update), target_value alone (re-target
    # after completion reopens it), or both at once.
    #
    # Shared with goal_progress_service so the manual-edit path and the linked-record
    # ($inc) path derive status identically — they diverged before, and only this one
    # recomputed it, so goals completed via a linked transaction never left ACTIVE.
    merged_current = update_data.get("current_value", goal.current_value)
    merged_target = update_data.get("target_value", goal.target_value)
    new_status = goal_progress_service.derive_status(merged_current, merged_target)
    for key, value in goal_progress_service.completion_fields(
        new_status, goal.status, goal.completed_at
    ).items():
        set_fields[f"active_goals.$.{key}"] = value

    collection = User.get_motor_collection()
    result = await collection.update_one(
        {"_id": user.id, "active_goals.goal_id": goal_id},
        {"$set": set_fields},
    )
    if result.matched_count == 0:
        raise NotFoundError("Goal", goal_id)

    await user.sync()

    await activity_service.log_activity(
        user_id=str(user.id),
        action_type="UPDATED_GOAL",
        entity_type="PROFILE",
        entity_id=goal_id,
        description=f"Updated goal '{goal.title}'"
    )
    return user

async def delete_active_goal(user: User, goal_id: str) -> User:
    """Atomically removes one goal via $pull, for the same reason as update_active_goal above."""
    goal = next((g for g in user.active_goals if g.goal_id == goal_id), None)
    if not goal:
        raise NotFoundError("Goal", goal_id)

    collection = User.get_motor_collection()
    await collection.update_one(
        {"_id": user.id},
        {"$pull": {"active_goals": {"goal_id": goal_id}}},
    )
    await user.sync()

    await activity_service.log_activity(
        user_id=str(user.id),
        action_type="DELETED_GOAL",
        entity_type="PROFILE",
        entity_id=goal_id,
        description=f"Deleted goal '{goal.title}'"
    )
    return user

async def delete_user(user: User) -> None:
    uid = user.id
    
    await FinancialRecord.find(FinancialRecord.user_id == uid).delete()
    await StudyActivity.find(StudyActivity.user_id == uid).delete()
    await HabitTracking.find(HabitTracking.user_id == uid).delete()
    await UserActivity.find(UserActivity.user_id == uid).delete()
    await Simulation.find(Simulation.user_id == uid).delete()
    await Recommendation.find(Recommendation.user_id == uid).delete()
    await AssistantFeedback.find(AssistantFeedback.user_id == uid).delete()

    await user.delete()
    logger.info("User %s and all associated records deleted.", uid)
