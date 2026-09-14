"""
api/v1/productivity.py — Productivity Analytics endpoints.
GET /api/v1/productivity/score                  → composite productivity score
GET /api/v1/productivity/focus-score             → average focus score
GET /api/v1/productivity/weekly-trend            → weekly study/productivity trend
GET /api/v1/productivity/monthly-trend           → monthly study/productivity trend
GET /api/v1/productivity/completion-percentage   → % of days studied in a window
GET /api/v1/productivity/prediction              → forward-looking performance prediction
GET /api/v1/productivity/summary                 → all of the above, bundled
"""
import logging

from fastapi import APIRouter, Query

from api.dependencies import CurrentUser
from schemas.productivity_schema import (
    CompletionPercentageResponse,
    FocusScoreResponse,
    MonthlyTrendResponse,
    PerformancePredictionResponse,
    ProductivityScoreResponse,
    ProductivitySummaryResponse,
    WeeklyTrendResponse,
)
from services.productivity_service import productivity_service

logger = logging.getLogger("digital_twin_ai.productivity_router")
router = APIRouter(prefix="/productivity", tags=["Productivity Analytics"])


@router.get(
    "/score",
    response_model=ProductivityScoreResponse,
    summary="Composite productivity score over a lookback window",
)
async def get_productivity_score(
    current_user: CurrentUser,
    lookback_days: int = Query(default=30, ge=1, le=365),
) -> ProductivityScoreResponse:
    """Returns a 0-100 composite score derived from focus, quiz/exam performance,
    and study-hours consistency across the requested window."""
    return await productivity_service.get_productivity_score(str(current_user.id), lookback_days)


@router.get(
    "/focus-score",
    response_model=FocusScoreResponse,
    summary="Average focus score over a lookback window",
)
async def get_focus_score(
    current_user: CurrentUser,
    lookback_days: int = Query(default=30, ge=1, le=365),
) -> FocusScoreResponse:
    """Averages recorded session focus_score values; reports insufficient_data when
    no session in the window has focus_score recorded."""
    return await productivity_service.get_focus_score(str(current_user.id), lookback_days)


@router.get(
    "/weekly-trend",
    response_model=WeeklyTrendResponse,
    summary="Weekly study hours / focus / productivity trend",
)
async def get_weekly_trend(
    current_user: CurrentUser,
    weeks_back: int = Query(default=8, ge=1, le=52),
) -> WeeklyTrendResponse:
    """Returns one point per week (oldest first), zero-filled for weeks with no sessions."""
    return await productivity_service.get_weekly_trend(str(current_user.id), weeks_back)


@router.get(
    "/monthly-trend",
    response_model=MonthlyTrendResponse,
    summary="Monthly study hours / focus / productivity trend",
)
async def get_monthly_trend(
    current_user: CurrentUser,
    months_back: int = Query(default=6, ge=1, le=24),
) -> MonthlyTrendResponse:
    """Returns one point per calendar month (oldest first), zero-filled for months with no sessions."""
    return await productivity_service.get_monthly_trend(str(current_user.id), months_back)


@router.get(
    "/completion-percentage",
    response_model=CompletionPercentageResponse,
    summary="Percentage of days with a logged study session",
)
async def get_completion_percentage(
    current_user: CurrentUser,
    window_days: int = Query(default=30, ge=1, le=365),
) -> CompletionPercentageResponse:
    """Returns the % of days in the window that had at least one study session logged."""
    return await productivity_service.get_completion_percentage(str(current_user.id), window_days)


@router.get(
    "/prediction",
    response_model=PerformancePredictionResponse,
    summary="Forward-looking productivity and exam-score prediction",
)
async def predict_performance(
    current_user: CurrentUser,
    weeks_ahead: int = Query(default=1, ge=1, le=12),
) -> PerformancePredictionResponse:
    """Projects the weekly productivity trend forward, and — when exam data exists —
    the exam-score trend, each with its own forecasting method and confidence score."""
    return await productivity_service.predict_performance(str(current_user.id), weeks_ahead)


@router.get(
    "/summary",
    response_model=ProductivitySummaryResponse,
    summary="Full productivity analytics summary",
)
async def get_productivity_summary(current_user: CurrentUser) -> ProductivitySummaryResponse:
    """Bundles productivity score, focus score, weekly/monthly trend, completion
    percentage, and performance prediction into a single response."""
    return await productivity_service.get_summary(str(current_user.id))
