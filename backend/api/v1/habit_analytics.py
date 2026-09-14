"""
api/v1/habit_analytics.py — Habit Analytics endpoints.
Mounted at /habit-analytics (distinct from /habits, which is habit-log CRUD).

GET /api/v1/habit-analytics/consistency-score   → % of days with a logged check-in
GET /api/v1/habit-analytics/streak              → current + longest logging streak
GET /api/v1/habit-analytics/positive            → habits consistently meeting healthy thresholds
GET /api/v1/habit-analytics/negative            → habits consistently missing healthy thresholds
GET /api/v1/habit-analytics/missed              → days in the window with no log at all
GET /api/v1/habit-analytics/trend               → daily / weekly / monthly habit trend
GET /api/v1/habit-analytics/summary             → all of the above, bundled
"""
import logging

from fastapi import APIRouter, Query

from api.dependencies import CurrentUser
from schemas.habit_analytics_schema import (
    ConsistencyScoreResponse,
    HabitAnalyticsSummaryResponse,
    HabitStreakResponse,
    HabitTrendResponse,
    MissedHabitsResponse,
    NegativeHabitsResponse,
    PositiveHabitsResponse,
)
from services.habit_analytics_service import habit_analytics_service

logger = logging.getLogger("digital_twin_ai.habit_analytics_router")
router = APIRouter(prefix="/habit-analytics", tags=["Habit Analytics"])


@router.get(
    "/consistency-score",
    response_model=ConsistencyScoreResponse,
    summary="Percentage of days with a logged habit check-in",
)
async def get_consistency_score(
    current_user: CurrentUser,
    window_days: int = Query(default=30, ge=1, le=365),
) -> ConsistencyScoreResponse:
    """Returns the % of days in the window that have a habit log entry."""
    return await habit_analytics_service.get_consistency_score(str(current_user.id), window_days)


@router.get(
    "/streak",
    response_model=HabitStreakResponse,
    summary="Current and longest habit-logging streak",
)
async def get_habit_streak(
    current_user: CurrentUser,
    lookback_days: int = Query(default=90, ge=1, le=365),
) -> HabitStreakResponse:
    """Returns the current consecutive-day logging streak (still counted "active" if
    today or yesterday is logged) plus the longest streak found in the lookback window."""
    return await habit_analytics_service.get_habit_streak(str(current_user.id), lookback_days)


@router.get(
    "/positive",
    response_model=PositiveHabitsResponse,
    summary="Habits consistently meeting healthy thresholds",
)
async def get_positive_habits(
    current_user: CurrentUser,
    window_days: int = Query(default=30, ge=1, le=365),
) -> PositiveHabitsResponse:
    """Returns tracked metrics (sleep, exercise, water, screen time) whose windowed
    average scores at or above the positive-habit threshold."""
    return await habit_analytics_service.get_positive_habits(str(current_user.id), window_days)


@router.get(
    "/negative",
    response_model=NegativeHabitsResponse,
    summary="Habits consistently missing healthy thresholds",
)
async def get_negative_habits(
    current_user: CurrentUser,
    window_days: int = Query(default=30, ge=1, le=365),
) -> NegativeHabitsResponse:
    """Returns tracked metrics whose windowed average falls below the positive-habit threshold."""
    return await habit_analytics_service.get_negative_habits(str(current_user.id), window_days)


@router.get(
    "/missed",
    response_model=MissedHabitsResponse,
    summary="Days in the window with no habit log at all",
)
async def get_missed_habits(
    current_user: CurrentUser,
    window_days: int = Query(default=30, ge=1, le=365),
) -> MissedHabitsResponse:
    """Returns the count and dates of days in the window with no logged check-in."""
    return await habit_analytics_service.get_missed_habits(str(current_user.id), window_days)


@router.get(
    "/trend",
    response_model=HabitTrendResponse,
    summary="Habit trend analyzed daily, weekly, and monthly",
)
async def get_habit_trend(
    current_user: CurrentUser,
    daily_days: int = Query(default=14, ge=1, le=90),
    weeks_back: int = Query(default=8, ge=1, le=52),
    months_back: int = Query(default=6, ge=1, le=24),
) -> HabitTrendResponse:
    """Returns habit history grouped at all three granularities in one response."""
    return await habit_analytics_service.get_habit_trend(
        str(current_user.id), daily_days, weeks_back, months_back
    )


@router.get(
    "/summary",
    response_model=HabitAnalyticsSummaryResponse,
    summary="Full habit analytics summary",
)
async def get_habit_analytics_summary(current_user: CurrentUser) -> HabitAnalyticsSummaryResponse:
    """Bundles consistency score, streak, positive/negative habits, missed habits,
    and the daily/weekly/monthly trend into a single structured response."""
    return await habit_analytics_service.get_summary(str(current_user.id))
