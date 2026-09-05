"""
api/v1/users.py — User profile management endpoints.
GET    /api/v1/users/me                  → full twin context (O(1) read)
PATCH  /api/v1/users/me/profile          → partial profile update
PATCH  /api/v1/users/me/preferences      → partial preferences update
POST   /api/v1/users/me/change-password  → change password, invalidates other sessions
POST   /api/v1/users/me/goals            → add active goal
GET    /api/v1/users/me/goals            → list active goals
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Request, Response, status, Depends
from beanie import PydanticObjectId

from api.dependencies import CurrentUser
from core.rate_limit import limiter
from core.security import create_access_token, set_auth_cookie
from models.user import User
from schemas.auth_schema import ChangePasswordRequest, TokenResponse
from schemas.user_schema import (
    UserResponse,
    ProfileUpdateRequest,
    ProfileResponse,
    PreferencesResponse,
    PreferencesUpdateRequest,
    ActiveGoalResponse,
    ActiveGoalCreateRequest,
    ActiveGoalUpdateRequest,
    DigitalTwinStateResponse,
)
import services.user_service as user_service

logger = logging.getLogger("digital_twin_ai.users_router")
router = APIRouter(prefix="/users", tags=["User Profile"])


def _serialize_user(user: User) -> UserResponse:
    """Serialises a User Beanie Document into the API response shape."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        profile=ProfileResponse(
            name=user.profile.name,
            age=user.profile.age,
            gender=user.profile.gender,
            occupation=user.profile.occupation,
            monthly_income_baseline=user.profile.monthly_income_baseline,
            risk_tolerance=user.profile.risk_tolerance,
        ),
        preferences=PreferencesResponse(
            currency=user.preferences.currency,
            language=user.preferences.language,
            dark_mode=user.preferences.dark_mode,
            email_notifications=user.preferences.email_notifications,
            weekly_report_enabled=user.preferences.weekly_report_enabled,
        ),
        active_goals=[
            ActiveGoalResponse(
                goal_id=g.goal_id,
                title=g.title,
                category=g.category,
                target_value=g.target_value,
                current_value=g.current_value,
                unit=g.unit,
                target_date=g.target_date,
                created_at=g.created_at,
                status=g.status,
                completed_at=g.completed_at,
            )
            for g in user.active_goals
        ],
        digital_twin_state=DigitalTwinStateResponse(
            savings_rate_pct=user.digital_twin_state.savings_rate_pct,
            emergency_fund_months=user.digital_twin_state.emergency_fund_months,
            study_consistency_score=user.digital_twin_state.study_consistency_score,
            predicted_exam_score=user.digital_twin_state.predicted_exam_score,
            habit_completion_rate=user.digital_twin_state.habit_completion_rate,
            lifestyle_score=user.digital_twin_state.lifestyle_score,
            productivity_score=user.digital_twin_state.productivity_score,
            burnout_risk_cluster=user.digital_twin_state.burnout_risk_cluster,
            last_updated_at=user.digital_twin_state.last_updated_at,
        ),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get complete twin context (O(1) read)",
)
async def get_me(current_user: CurrentUser) -> UserResponse:
    """
    Returns the full user aggregate: profile + preferences + active_goals +
    digital_twin_state (recomputed live from real activity on every call —
    see user_service.get_twin_context for the data sources).
    """
    user = await user_service.get_twin_context(str(current_user.id))
    return _serialize_user(user)

@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete current user and all data",
)
async def delete_me(
    current_user: CurrentUser,
) -> None:
    """Permanently deletes the user and all associated records."""
    await user_service.delete_user(current_user)


@router.post(
    "/me/change-password",
    response_model=TokenResponse,
    summary="Change the current user's password",
)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
) -> TokenResponse:
    """
    Verifies the current password, sets the new one, and invalidates every other
    outstanding session for this account. Re-sets the auth cookie with a fresh token
    so this session keeps working — every other previously issued token/cookie is
    now stale. Rate limited (takes a password guess as input, same as /auth/login).
    """
    user = await user_service.change_password(current_user, payload)
    token = create_access_token(subject=str(user.id), token_version=user.token_version)
    set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        email=user.email,
    )


@router.patch(
    "/me/profile",
    response_model=UserResponse,
    summary="Partially update user profile",
)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: CurrentUser,
) -> UserResponse:
    """Applies partial $set updates to the embedded profile subdocument."""
    updated = await user_service.update_profile(current_user, payload)
    return _serialize_user(updated)


@router.patch(
    "/me/preferences",
    response_model=UserResponse,
    summary="Update user notification and display preferences",
)
async def update_preferences(
    payload: PreferencesUpdateRequest,
    current_user: CurrentUser,
) -> UserResponse:
    """Applies partial $set updates to the embedded preferences subdocument."""
    updated = await user_service.update_preferences(current_user, payload)
    return _serialize_user(updated)


@router.post(
    "/me/goals",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new active goal (hard cap: 30)",
)
async def add_goal(
    payload: ActiveGoalCreateRequest,
    current_user: CurrentUser,
) -> UserResponse:
    """
    Atomically appends a new goal to the user's active_goals array.
    Enforces the hard cap of 30 items (mirrors addActiveGoal() from user_repository.ts).
    Returns 422 if the cap is reached.
    """
    updated = await user_service.add_active_goal(current_user, payload)
    return _serialize_user(updated)


@router.get(
    "/me/goals",
    response_model=list[ActiveGoalResponse],
    summary="List all active goals for the current user",
)
async def list_goals(current_user: CurrentUser) -> list[ActiveGoalResponse]:
    """Returns the bounded active goals array directly from the user document."""
    return [
        ActiveGoalResponse(
            goal_id=g.goal_id,
            title=g.title,
            category=g.category,
            target_value=g.target_value,
            current_value=g.current_value,
            unit=g.unit,
            target_date=g.target_date,
            created_at=g.created_at,
            # `status` is required on ActiveGoalResponse and was not passed here,
            # so every call to this endpoint raised a Pydantic ValidationError and
            # returned 500. It went unnoticed because the frontend reads goals from
            # GET /users/me's active_goals rather than calling this route.
            status=g.status,
            completed_at=g.completed_at,
        )
        for g in current_user.active_goals
    ]

@router.patch(
    "/me/goals/{goal_id}",
    response_model=UserResponse,
    summary="Update an active goal",
)
async def update_goal(
    goal_id: str,
    payload: ActiveGoalUpdateRequest,
    current_user: CurrentUser,
) -> UserResponse:
    """Updates an existing goal in the user's active_goals array."""
    updated = await user_service.update_active_goal(current_user, goal_id, payload)
    return _serialize_user(updated)

@router.delete(
    "/me/goals/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an active goal",
)
async def delete_goal(
    goal_id: str,
    current_user: CurrentUser,
) -> None:
    """Removes a goal from the user's active_goals array."""
    await user_service.delete_active_goal(current_user, goal_id)
