"""
api/v1/trend_prediction.py — Trend Prediction endpoints.
Consumes Financial Forecasting, Productivity Analytics, and Habit Analytics outputs
to produce forward-looking predictions with a probability/confidence score each.

GET /api/v1/trends/savings   → future savings trend (wraps Financial Forecasting)
GET /api/v1/trends/study     → future study/productivity trend (wraps Productivity Analytics)
GET /api/v1/trends/fitness   → future fitness/habit-score trend (built on Habit Analytics)
GET /api/v1/trends/goals     → goal completion predictions (wraps Financial Forecasting)
GET /api/v1/trends/summary   → all of the above, bundled with an overall confidence score
"""
import logging

from fastapi import APIRouter, Query

from api.dependencies import CurrentUser
from schemas.trend_prediction_schema import (
    FitnessTrendPrediction,
    GoalTrendPrediction,
    SavingsTrendPrediction,
    StudyTrendPrediction,
    TrendPredictionSummary,
)
from services.trend_prediction_service import trend_prediction_service

logger = logging.getLogger("digital_twin_ai.trend_prediction_router")
router = APIRouter(prefix="/trends", tags=["Trend Prediction"])


@router.get(
    "/savings",
    response_model=SavingsTrendPrediction,
    summary="Predict future savings trend",
)
async def predict_savings_trend(
    current_user: CurrentUser,
    months_ahead: int = Query(default=1, ge=1, le=12),
) -> SavingsTrendPrediction:
    """Wraps the Financial Forecasting Service's monthly savings forecast."""
    return await trend_prediction_service.predict_savings_trend(str(current_user.id), months_ahead)


@router.get(
    "/study",
    response_model=StudyTrendPrediction,
    summary="Predict future study/productivity trend",
)
async def predict_study_trend(
    current_user: CurrentUser,
    weeks_ahead: int = Query(default=1, ge=1, le=12),
) -> StudyTrendPrediction:
    """Wraps the Productivity Analytics Engine's performance prediction
    (productivity trend + exam-score trend, when exam data exists)."""
    return await trend_prediction_service.predict_study_trend(str(current_user.id), weeks_ahead)


@router.get(
    "/fitness",
    response_model=FitnessTrendPrediction,
    summary="Predict future fitness/habit-score trend",
)
async def predict_fitness_trend(
    current_user: CurrentUser,
    weeks_ahead: int = Query(default=1, ge=1, le=12),
) -> FitnessTrendPrediction:
    """Projects the Habit Analytics Engine's weekly habit-score trend forward
    (Habit Analytics itself only reports historical/current trend)."""
    return await trend_prediction_service.predict_fitness_trend(str(current_user.id), weeks_ahead)


@router.get(
    "/goals",
    response_model=list[GoalTrendPrediction],
    summary="Predict goal completion trends",
)
async def predict_goal_completions(current_user: CurrentUser) -> list[GoalTrendPrediction]:
    """Wraps the Financial Forecasting Service's goal completion estimates.
    Currently scoped to FINANCE-category goals."""
    return await trend_prediction_service.predict_goal_completions(str(current_user.id))


@router.get(
    "/summary",
    response_model=TrendPredictionSummary,
    summary="Full trend prediction summary",
)
async def get_trend_prediction_summary(
    current_user: CurrentUser,
    months_ahead: int = Query(default=1, ge=1, le=12),
    weeks_ahead: int = Query(default=1, ge=1, le=12),
) -> TrendPredictionSummary:
    """Bundles savings, study, fitness, and goal predictions into a single response
    with an overall confidence score averaged across all of them."""
    return await trend_prediction_service.predict_all_trends(
        str(current_user.id), months_ahead, weeks_ahead
    )
