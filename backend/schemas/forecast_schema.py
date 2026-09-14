"""
schemas/forecast_schema.py — Pydantic response schemas for the Financial Forecasting Service.
Follows the same style as schemas/finance_schema.py.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from models.enums import GoalCategory


class ForecastMethod(str, Enum):
    """Which forecasting method produced a given projection, chosen by data volume."""
    INSUFFICIENT_DATA = "insufficient_data"
    BASELINE_FALLBACK = "baseline_fallback"
    NAIVE_LAST_VALUE = "naive_last_value"
    MOVING_AVERAGE = "moving_average"
    LINEAR_REGRESSION = "linear_regression"


class MonthlyProjectionPoint(BaseModel):
    year: int
    month: int
    projected_amount: Decimal


class SavingsForecastResponse(BaseModel):
    """GET /forecast/savings"""
    user_id: str
    projections: list[MonthlyProjectionPoint]
    method_used: ForecastMethod
    data_points_used: int
    confidence_score: float


class IncomeProjectionResponse(BaseModel):
    """GET /forecast/income"""
    user_id: str
    projections: list[MonthlyProjectionPoint]
    method_used: ForecastMethod
    data_points_used: int
    confidence_score: float


class ExpenseProjectionResponse(BaseModel):
    """GET /forecast/expenses"""
    user_id: str
    projections: list[MonthlyProjectionPoint]
    method_used: ForecastMethod
    data_points_used: int
    confidence_score: float


class GoalCompletionResponse(BaseModel):
    """GET /forecast/goals/{goal_id}, GET /forecast/goals"""
    goal_id: str
    title: str
    category: GoalCategory
    current_value: Decimal
    target_value: Decimal
    target_date: datetime
    monthly_projected_delta: Decimal
    estimated_months_remaining: Optional[int] = None
    estimated_completion_date: Optional[datetime] = None
    on_track: Optional[bool] = None
    method_used: ForecastMethod
    confidence_score: float


class ForecastSummaryResponse(BaseModel):
    """GET /forecast/summary"""
    user_id: str
    savings_forecast: SavingsForecastResponse
    income_projection: IncomeProjectionResponse
    expense_projection: ExpenseProjectionResponse
    goal_completions: list[GoalCompletionResponse]
    overall_confidence_score: float
    generated_at: datetime


class SeriesAccuracy(BaseModel):
    """Walk-forward backtest result for one series (income/expense/savings)."""
    accuracy_pct: float
    points_evaluated: int


class ForecastAccuracyResponse(BaseModel):
    """GET /forecast/accuracy — retrospective accuracy, not to be confused with
    confidence_score (a live, forward-looking heuristic on the other endpoints).
    Measured by walk-forward backtesting: at each past month, forecast one step
    ahead using only data available up to that point, then compare against what
    actually happened."""
    user_id: str
    income_accuracy: SeriesAccuracy
    expense_accuracy: SeriesAccuracy
    savings_accuracy: SeriesAccuracy
    overall_accuracy_pct: float
    by_method: dict[ForecastMethod, float]
    generated_at: datetime
