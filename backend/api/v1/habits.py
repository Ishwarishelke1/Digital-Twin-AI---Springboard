"""
api/v1/habits.py — Habit data collection endpoints.
POST  /api/v1/habits/daily-log                  → upsert today's biometric check-in
PATCH /api/v1/habits/daily-log/{id}             → edit an existing log (any day)
GET   /api/v1/habits/daily-log                  → paginated habit log history
GET   /api/v1/habits/analytics/kmeans-features  → 4D feature matrix for K-Means ML
"""
import logging

from fastapi import APIRouter, Query, status

from api.dependencies import CurrentUser
from typing import Optional

from models.enums import SleepBand
from schemas.habit_schema import (
    HabitCreateRequest,
    HabitUpdateRequest,
    HabitRecordResponse,
    PaginatedHabitResponse,
    KMeansFeatureRow,
)
import services.habit_service as habit_service

logger = logging.getLogger("digital_twin_ai.habits_router")
router = APIRouter(prefix="/habits", tags=["Habit Tracking"])


@router.post(
    "/daily-log",
    response_model=HabitRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Upsert today's daily biometric check-in",
)
async def upsert_daily_log(
    payload: HabitCreateRequest,
    current_user: CurrentUser,
) -> HabitRecordResponse:
    """
    Creates or updates the habit log for today (UTC).
    The unique compound index (user_id, log_date) in MongoDB enforces strictly 1 entry per day.
    log_date is auto-normalized to midnight UTC (mirrors HabitTrackingSchema.pre('validate')).
    Returns 200 (not 201) because this is an upsert — the record may already exist.
    """
    return await habit_service.upsert_daily_log(str(current_user.id), payload)


@router.patch(
    "/daily-log/{log_id}",
    response_model=HabitRecordResponse,
    summary="Update an existing habit log",
)
async def update_daily_log(
    log_id: str,
    payload: HabitUpdateRequest,
    current_user: CurrentUser,
) -> HabitRecordResponse:
    """Edits a habit log (typically a past day's entry) without changing its log_date."""
    return await habit_service.update_log(str(current_user.id), log_id, payload)


@router.delete(
    "/daily-log/{log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a daily habit log",
)
async def delete_daily_log(
    log_id: str,
    current_user: CurrentUser,
) -> None:
    """Deletes a habit log."""
    await habit_service.delete_daily_log(str(current_user.id), log_id)


@router.get(
    "/daily-log",
    response_model=PaginatedHabitResponse,
    summary="Get paginated habit log history",
)
async def list_logs(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    mood_rating: Optional[int] = Query(default=None, ge=1, le=5, description="Filter by mood (1-5)"),
    sleep_band: Optional[SleepBand] = Query(default=None, description="Filter by sleep against the healthy range"),
) -> PaginatedHabitResponse:
    """
    Returns paginated habit records sorted by log_date descending.
    Leverages idx_habit_user_date_desc ESR index.
    """
    return await habit_service.list_logs(
        user_id=str(current_user.id),
        page=page,
        limit=limit,
        mood_rating=mood_rating,
        sleep_band=sleep_band,
    )


@router.get(
    "/analytics/kmeans-features",
    response_model=list[KMeansFeatureRow],
    summary="Extract 4D biometric feature matrix (raw, unclustered)",
)
async def kmeans_feature_space(
    current_user: CurrentUser,
    days: int = Query(default=30, ge=7, le=365, description="Lookback window in days"),
) -> list[KMeansFeatureRow]:
    """
    Returns the raw 4D biometric feature vectors (sleep, exercise, water, screen_time)
    over the specified time window. Python port of extractKMeansFeatureSpace() from
    habit_repository.ts.

    NOTE: this is feature *extraction* only — no K-Means clustering algorithm is
    implemented anywhere in this codebase yet, and no frontend page currently calls
    this endpoint. `HabitTracking.burnout_risk_cluster` is written by nothing and
    stays at its default (UNKNOWN) for every user. Kept as a documented building
    block for a future clustering feature rather than removed.
    """
    return await habit_service.extract_kmeans_feature_space(str(current_user.id), days)
