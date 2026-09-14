"""
api/v1/forecast.py — Financial forecasting endpoints.
GET /api/v1/forecast/savings                  → monthly savings forecast
GET /api/v1/forecast/income                    → income projection
GET /api/v1/forecast/expenses                  → expense projection
GET /api/v1/forecast/goals/{goal_id}           → single goal completion estimate
GET /api/v1/forecast/goals                     → all finance-category goal estimates
GET /api/v1/forecast/summary                   → bundled forecast + overall confidence
GET /api/v1/forecast/accuracy                  → backtested accuracy (retrospective, not confidence)
"""
import logging

from fastapi import APIRouter, Query

from api.dependencies import CurrentUser
from schemas.forecast_schema import (
    ExpenseProjectionResponse,
    ForecastAccuracyResponse,
    ForecastSummaryResponse,
    GoalCompletionResponse,
    IncomeProjectionResponse,
    SavingsForecastResponse,
)
from services.forecast_service import forecast_service

logger = logging.getLogger("digital_twin_ai.forecast_router")
router = APIRouter(prefix="/forecast", tags=["Financial Forecasting"])


@router.get(
    "/savings",
    response_model=SavingsForecastResponse,
    summary="Forecast monthly savings",
)
async def forecast_savings(
    current_user: CurrentUser,
    months_ahead: int = Query(default=1, ge=1, le=12),
) -> SavingsForecastResponse:
    """Projects future monthly savings (income - expense) using the best method
    available given the user's transaction history."""
    return await forecast_service.forecast_monthly_savings(str(current_user.id), months_ahead)


@router.get(
    "/income",
    response_model=IncomeProjectionResponse,
    summary="Project future income",
)
async def project_income(
    current_user: CurrentUser,
    months_ahead: int = Query(default=1, ge=1, le=12),
) -> IncomeProjectionResponse:
    """Projects future monthly income. Falls back to the user's
    profile.monthly_income_baseline when there is no transaction history at all."""
    return await forecast_service.project_income(str(current_user.id), months_ahead)


@router.get(
    "/expenses",
    response_model=ExpenseProjectionResponse,
    summary="Project future expenses",
)
async def project_expenses(
    current_user: CurrentUser,
    months_ahead: int = Query(default=1, ge=1, le=12),
) -> ExpenseProjectionResponse:
    """Projects future monthly expenses. There is no sane fallback when there's no
    history, so this simply reports insufficient_data in that case."""
    return await forecast_service.project_expenses(str(current_user.id), months_ahead)


@router.get(
    "/goals/{goal_id}",
    response_model=GoalCompletionResponse,
    summary="Estimate a single goal's completion",
)
async def goal_completion(goal_id: str, current_user: CurrentUser) -> GoalCompletionResponse:
    """Estimates months remaining and projected completion date for one active goal,
    based on the user's projected monthly savings trend. Returns 404 if the goal
    doesn't exist."""
    return await forecast_service.estimate_goal_completion(str(current_user.id), goal_id)


@router.get(
    "/goals",
    response_model=list[GoalCompletionResponse],
    summary="Estimate completion for all finance-category goals",
)
async def all_goal_completions(current_user: CurrentUser) -> list[GoalCompletionResponse]:
    """Returns a completion estimate for every active goal with category=FINANCE."""
    return await forecast_service.estimate_all_goal_completions(str(current_user.id))


@router.get(
    "/summary",
    response_model=ForecastSummaryResponse,
    summary="Full financial forecast summary",
)
async def forecast_summary(current_user: CurrentUser) -> ForecastSummaryResponse:
    """Bundles the savings forecast, income/expense projections, and finance-goal
    completion estimates into one response with an averaged overall confidence score."""
    return await forecast_service.get_forecast_summary(str(current_user.id))


@router.get(
    "/accuracy",
    response_model=ForecastAccuracyResponse,
    summary="Backtested financial forecasting accuracy",
)
async def forecast_accuracy(current_user: CurrentUser) -> ForecastAccuracyResponse:
    """Retrospective accuracy via walk-forward backtesting over this user's real
    transaction history — distinct from confidence_score (a live, forward-looking
    heuristic on the other endpoints). At each past month, forecasts one step ahead
    using only data available up to that point, then scores it against what actually
    happened."""
    return await forecast_service.backtest_accuracy(str(current_user.id))
