"""
models/simulation.py — Beanie ODM Documents for the Decision Simulation & Recommendation Engine
(Milestone 3). New collections: `simulations`, `recommendations`.

Uses the SimulationDomain/SimulationStatus/RecommendationCategory/Priority/
UserFeedback enums already defined in models/enums.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pymongo
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

from models.enums import (
    Priority,
    RecommendationCategory,
    SimulationDomain,
    SimulationStatus,
    UserFeedback,
)


class MetricPoint(BaseModel):
    """One labelled figure surfaced on a scenario, e.g. {label: 'Future Saving', value: 42000, unit: 'INR'}."""
    label: str
    value: float
    unit: Optional[str] = None


class ScenarioResult(BaseModel):
    """One simulated what-if outcome within a Simulation. Embedded, no _id."""
    name: str
    deltas: dict[str, float] = Field(default_factory=dict)
    metrics: list[MetricPoint] = Field(default_factory=list)
    primary_metric_label: str
    primary_metric_value: float
    score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=1)


class Simulation(Document):
    user_id: PydanticObjectId
    domain: SimulationDomain
    input_parameters: dict = Field(default_factory=dict)
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    status: SimulationStatus = SimulationStatus.SUCCESS
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "simulations"
        # Every query on this collection is per-user: history listing sorts by
        # created_at desc (simulation_service.get_history), and account deletion
        # does a delete-by-user_id (user_service). Without this the history page
        # and account deletion both scan the whole collection — matches the
        # pattern models/activity.py already uses.
        indexes = [
            [("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        ]

    class Config:
        populate_by_name = True


class Recommendation(Document):
    user_id: PydanticObjectId
    simulation_id: Optional[PydanticObjectId] = None
    category: RecommendationCategory
    title: str = Field(..., max_length=200)
    reason: str = Field(..., max_length=1000)
    recommended_scenario_name: str
    priority: Priority = Priority.MEDIUM
    user_feedback: Optional[UserFeedback] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "recommendations"
        # user_id + created_at: per-user listing and delete-by-user (user_service).
        # user_feedback: feedback_service.get_satisfaction_summary() filters on
        # `user_feedback != None` app-wide, which is a full scan without this.
        indexes = [
            [("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
            [("user_feedback", pymongo.ASCENDING)],
        ]

    class Config:
        populate_by_name = True
