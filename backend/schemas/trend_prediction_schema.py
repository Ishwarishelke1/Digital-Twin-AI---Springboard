"""
schemas/trend_prediction_schema.py — Pydantic response schemas for the Trend Prediction Engine.
Fields that echo a method name from an upstream service (Financial Forecasting,
Productivity Analytics) are typed as plain `str` rather than importing that
service's enum, to keep this engine's schema decoupled from theirs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectedValue(BaseModel):
    period: str  # "2026-09" for monthly points, ISO week-start date for weekly points
    value: float


class SavingsTrendPrediction(BaseModel):
    """Wraps services.forecast_service.ForecastService.forecast_monthly_savings()."""
    user_id: str
    projected_savings: list[ProjectedValue]
    method_used: str
    confidence_score: float
    data_points_used: int


class StudyTrendPrediction(BaseModel):
    """Wraps services.productivity_service.ProductivityService.predict_performance()."""
    user_id: str
    projected_productivity: list[ProjectedValue]
    productivity_method_used: str
    productivity_confidence_score: float
    predicted_exam_score: Optional[float] = None
    exam_method_used: Optional[str] = None
    exam_confidence_score: Optional[float] = None
    data_points_used: int


class FitnessTrendPrediction(BaseModel):
    """Forecasts the habit-trend average score forward — the Habit Analytics Engine
    only reports historical/current trend, so the forward projection lives here."""
    user_id: str
    projected_fitness_score: list[ProjectedValue]
    method_used: str
    confidence_score: float
    data_points_used: int


class GoalTrendPrediction(BaseModel):
    """Wraps services.forecast_service.ForecastService.estimate_all_goal_completions().
    Currently scoped to FINANCE-category goals, since that is the only goal-completion
    estimator that exists among the consumed services."""
    goal_id: str
    title: str
    category: str
    estimated_months_remaining: Optional[int] = None
    estimated_completion_date: Optional[datetime] = None
    on_track: Optional[bool] = None
    method_used: str
    confidence_score: float


class TrendPredictionSummary(BaseModel):
    user_id: str
    savings: SavingsTrendPrediction
    study: StudyTrendPrediction
    fitness: FitnessTrendPrediction
    goals: list[GoalTrendPrediction]
    overall_confidence_score: float
    generated_at: datetime
