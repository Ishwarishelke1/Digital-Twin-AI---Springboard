"""
schemas/simulation_schema.py — Pydantic request/response schemas for the Decision
Simulation & Recommendation Engine (Milestone 3). Follows the same style as
schemas/forecast_schema.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from models.enums import Priority, RecommendationCategory, SimulationDomain


# ─── Requests ──────────────────────────────────────────────────────────────────

class FinanceScenarioRequest(BaseModel):
    additional_monthly_saving: float = Field(default=0.0, ge=0)
    expense_reduction_pct: float = Field(default=0.0, ge=0, le=100)
    months_ahead: int = Field(default=6, gt=0, le=120)


class StudyScenarioRequest(BaseModel):
    additional_weekly_study_hours: float = Field(default=0.0, ge=0, le=80)
    weeks_ahead: int = Field(default=4, gt=0, le=52)


class FitnessScenarioRequest(BaseModel):
    additional_exercise_minutes: float = Field(default=0.0, ge=0, le=600)
    sleep_adjustment_hours: float = Field(default=0.0, ge=-6, le=6)
    weeks_ahead: int = Field(default=4, gt=0, le=52)


class HybridScenarioRequest(BaseModel):
    additional_monthly_saving: float = Field(default=0.0, ge=0)
    additional_weekly_study_hours: float = Field(default=0.0, ge=0, le=80)
    additional_exercise_minutes: float = Field(default=0.0, ge=0, le=600)
    sleep_adjustment_hours: float = Field(default=0.0, ge=-6, le=6)
    months_ahead: int = Field(default=6, gt=0, le=120)

    @model_validator(mode="after")
    def at_least_one_delta(self) -> "HybridScenarioRequest":
        if (
            self.additional_monthly_saving == 0
            and self.additional_weekly_study_hours == 0
            and self.additional_exercise_minutes == 0
            and self.sleep_adjustment_hours == 0
        ):
            raise ValueError("At least one delta must be non-zero to simulate a hybrid scenario.")
        return self


class RecommendationFeedbackRequest(BaseModel):
    feedback: str  # validated against UserFeedback enum in the service layer


# ─── Responses ─────────────────────────────────────────────────────────────────

class MetricPointResponse(BaseModel):
    label: str
    value: float
    unit: Optional[str] = None


class ScenarioResultResponse(BaseModel):
    name: str
    deltas: dict[str, float]
    metrics: list[MetricPointResponse]
    primary_metric_label: str
    primary_metric_value: float
    score: float
    confidence_score: float


class RecommendationResponse(BaseModel):
    id: str
    category: RecommendationCategory
    title: str
    reason: str
    recommended_scenario_name: str
    priority: Priority
    stats: list[MetricPointResponse]


class SimulationResponse(BaseModel):
    id: str
    domain: SimulationDomain
    scenarios: list[ScenarioResultResponse]
    recommendation: RecommendationResponse
    generated_at: datetime


class SimulationHistoryItem(BaseModel):
    id: str
    domain: SimulationDomain
    status: str
    top_scenario_name: str
    created_at: datetime


class SimulationDetailResponse(BaseModel):
    """GET /simulation/{simulation_id} — one persisted simulation, scenarios only
    (no recommendation attached; use the /scenarios or /compare endpoints for that)."""
    id: str
    user_id: str
    domain: SimulationDomain
    input_parameters: dict
    scenarios: list[ScenarioResultResponse]
    status: str
    created_at: datetime


class DomainComparisonResponse(BaseModel):
    """GET /simulation/compare — bundles a default-delta run of every domain
    plus one overall top recommendation across all of them."""
    user_id: str
    finance: SimulationResponse
    study: SimulationResponse
    fitness: SimulationResponse
    overall_recommendation: RecommendationResponse
    generated_at: datetime
