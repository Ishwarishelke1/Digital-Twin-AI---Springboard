"""
schemas/user_schema.py — Pydantic request/response schemas for user profile endpoints.
Field names and allowed values strictly mirror backend/database/schemas/user_schema.ts.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from models.enums import Gender, RiskTolerance, GoalCategory, GoalStatus, BurnoutRisk


# ─── Subdocument Schemas ──────────────────────────────────────────────────────

class ProfileResponse(BaseModel):
    name: str
    age: int
    gender: Optional[Gender] = None
    occupation: Optional[str] = None
    monthly_income_baseline: Decimal
    risk_tolerance: RiskTolerance


class ProfileUpdateRequest(BaseModel):
    """PATCH /api/v1/users/me/profile — all fields optional (partial update)."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    age: Optional[int] = Field(default=None, ge=13, le=120)
    gender: Optional[Gender] = None
    occupation: Optional[str] = Field(default=None, max_length=100)
    monthly_income_baseline: Optional[Decimal] = Field(default=None, ge=0)
    risk_tolerance: Optional[RiskTolerance] = None


class PreferencesResponse(BaseModel):
    currency: str
    language: str
    dark_mode: bool
    email_notifications: bool
    weekly_report_enabled: bool


class PreferencesUpdateRequest(BaseModel):
    currency: Optional[str] = Field(default=None, max_length=5)
    language: Optional[str] = Field(default=None, max_length=10)
    dark_mode: Optional[bool] = None
    email_notifications: Optional[bool] = None
    weekly_report_enabled: Optional[bool] = None


class ActiveGoalResponse(BaseModel):
    goal_id: str
    title: str
    category: GoalCategory
    target_value: Decimal
    current_value: Decimal
    unit: str
    target_date: datetime
    created_at: Optional[datetime]
    status: GoalStatus
    # When the goal was first met. Null for goals completed before this field
    # existed, and for goals never completed — see models/user.py for why it is
    # stamped once and never cleared.
    completed_at: Optional[datetime] = None


class ActiveGoalCreateRequest(BaseModel):
    title: str = Field(..., max_length=150)
    category: GoalCategory
    target_value: Decimal = Field(..., gt=0)
    unit: str = Field(..., max_length=20)
    target_date: datetime


class ActiveGoalUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=150)
    category: Optional[GoalCategory] = None
    target_value: Optional[Decimal] = Field(default=None, gt=0)
    current_value: Optional[Decimal] = Field(default=None, ge=0)
    unit: Optional[str] = Field(default=None, max_length=20)
    target_date: Optional[datetime] = None


class DigitalTwinStateResponse(BaseModel):
    savings_rate_pct: Decimal
    emergency_fund_months: Decimal
    study_consistency_score: Decimal
    predicted_exam_score: Optional[Decimal]
    habit_completion_rate: Decimal
    lifestyle_score: Decimal
    productivity_score: Decimal
    burnout_risk_cluster: BurnoutRisk
    last_updated_at: datetime


# ─── Top-Level User Response ──────────────────────────────────────────────────

class UserResponse(BaseModel):
    """Full user context response — the FastAPI equivalent of getTwinContext() output."""
    id: str
    email: str
    profile: ProfileResponse
    preferences: PreferencesResponse
    active_goals: list[ActiveGoalResponse]
    digital_twin_state: DigitalTwinStateResponse
    created_at: datetime
    updated_at: datetime
