"""
schemas/productivity_schema.py — Pydantic response schemas for the Productivity Analytics Engine.
Follows the same style as schemas/forecast_schema.py, but is fully self-contained
(no shared types with the financial forecasting code).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class AnalyticsMethod(str, Enum):
    """Which method produced a given score/prediction, chosen by data volume."""
    INSUFFICIENT_DATA = "insufficient_data"
    NAIVE_LAST_VALUE = "naive_last_value"
    MOVING_AVERAGE = "moving_average"
    LINEAR_REGRESSION = "linear_regression"
    RECORDED_AVERAGE = "recorded_average"


class WeeklyTrendPoint(BaseModel):
    week_start: date
    total_study_hours: float
    average_focus_score: float
    average_productivity_score: float
    session_count: int


class MonthlyTrendPoint(BaseModel):
    year: int
    month: int
    total_study_hours: float
    average_focus_score: float
    average_productivity_score: float
    session_count: int


class WeeklyProjectionPoint(BaseModel):
    week_start: date
    projected_score: float


class ProductivityScoreResponse(BaseModel):
    user_id: str
    productivity_score: float
    data_points_used: int
    lookback_days: int


class FocusScoreResponse(BaseModel):
    user_id: str
    focus_score: float
    method_used: AnalyticsMethod
    data_points_used: int


class WeeklyTrendResponse(BaseModel):
    user_id: str
    trend: list[WeeklyTrendPoint]


class MonthlyTrendResponse(BaseModel):
    user_id: str
    trend: list[MonthlyTrendPoint]


class CompletionPercentageResponse(BaseModel):
    user_id: str
    completion_percentage: float
    active_days: int
    window_days: int


class PerformancePredictionResponse(BaseModel):
    """Projects the overall productivity trend forward, and — when exam data exists —
    the exam-score trend, each with its own method and confidence score."""
    user_id: str
    predicted_productivity: list[WeeklyProjectionPoint]
    productivity_method_used: AnalyticsMethod
    productivity_confidence_score: float
    predicted_exam_score: Optional[Decimal] = None
    exam_method_used: Optional[AnalyticsMethod] = None
    exam_confidence_score: Optional[float] = None
    data_points_used: int


class ProductivitySummaryResponse(BaseModel):
    user_id: str
    productivity_score: ProductivityScoreResponse
    focus_score: FocusScoreResponse
    weekly_trend: WeeklyTrendResponse
    monthly_trend: MonthlyTrendResponse
    completion_percentage: CompletionPercentageResponse
    performance_prediction: PerformancePredictionResponse
    generated_at: datetime
