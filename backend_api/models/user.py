"""
models/user.py — Beanie ODM Document mirroring backend/database/schemas/user_schema.ts.
Collection: `users`
Subdocuments: UserPreferences, ActiveGoal, DigitalTwinState (embedded, no _id).
DO NOT alter field names or collection name — they map directly to existing MongoDB documents.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Annotated

from beanie import Document, Indexed, DecimalAnnotation
from pydantic import BaseModel, Field, field_validator, model_validator, EmailStr

from models.enums import Gender, RiskTolerance, GoalCategory, GoalStatus, BurnoutRisk


# ─── Subdocument: UserPreferences ─────────────────────────────────────────────
# Mirrors: backend/database/schemas/subdocuments/user_preferences.ts
class UserPreferences(BaseModel):
    currency: str = Field(default="INR", max_length=5)
    language: str = Field(default="en", max_length=10)
    dark_mode: bool = True
    email_notifications: bool = True
    weekly_report_enabled: bool = True

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("language")
    @classmethod
    def language_lower(cls, v: str) -> str:
        return v.lower().strip()

    class Config:
        populate_by_name = True


# ─── Subdocument: ActiveGoal ──────────────────────────────────────────────────
# Mirrors: backend/database/schemas/subdocuments/active_goal.ts
# Note: goal_id is stored as a string UUID (compatible with MongoDB ObjectId-less embedded docs)
class ActiveGoal(BaseModel):
    goal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., max_length=150)
    category: GoalCategory
    target_value: DecimalAnnotation = Field(..., gt=0)
    current_value: DecimalAnnotation = Field(default=Decimal("0.00"), ge=0)
    unit: str = Field(..., max_length=20)
    target_date: datetime
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Auto-derived from current_value vs target_value on every update (see
    # user_service.update_active_goal) — not user-settable directly. Defaults to ACTIVE
    # for both new goals and every pre-existing goal subdocument (which has no status
    # key at all), matching the token_version backward-compatibility pattern above.
    status: GoalStatus = Field(default=GoalStatus.ACTIVE)
    # Set once, on the first ACTIVE → COMPLETED transition, and deliberately NOT
    # cleared if progress later dips back below target (deleting a linked
    # transaction reverses current_value): the completion happened, and a later
    # reversal is a separate fact. `status` stays symmetric and reversible;
    # this field is the durable record of *when* the goal was first met.
    #
    # This is the training label for goal-completion prediction — "did it
    # complete before target_date" is not derivable without it, and it is only
    # capturable going forward, which is why it exists ahead of any model.
    # Pre-existing goals default to None and are excluded from training rather
    # than having a completion date imputed. Same backward-compatibility shape
    # as token_version / GoalStatus.
    completed_at: Optional[datetime] = Field(default=None)

    class Config:
        populate_by_name = True


# ─── Subdocument: DigitalTwinState ────────────────────────────────────────────
# Mirrors: backend/database/schemas/subdocuments/digital_twin_state.ts
class DigitalTwinState(BaseModel):
    savings_rate_pct: DecimalAnnotation = Field(default=Decimal("0.0"), ge=0, le=100)
    emergency_fund_months: DecimalAnnotation = Field(default=Decimal("0.0"), ge=0)
    study_consistency_score: DecimalAnnotation = Field(default=Decimal("0.0"), ge=0, le=100)
    predicted_exam_score: Optional[DecimalAnnotation] = Field(default=None, ge=0, le=100)
    habit_completion_rate: DecimalAnnotation = Field(default=Decimal("0.0"), ge=0, le=100)
    lifestyle_score: DecimalAnnotation = Field(default=Decimal("0.0"), ge=0, le=100)
    productivity_score: DecimalAnnotation = Field(default=Decimal("0.0"), ge=0, le=100)
    burnout_risk_cluster: BurnoutRisk = BurnoutRisk.UNKNOWN
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True


# ─── Subdocument: Profile ─────────────────────────────────────────────────────
# Mirrors: ProfileSchema within backend/database/schemas/user_schema.ts
class Profile(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    age: int = Field(..., ge=13, le=120)
    gender: Optional[Gender] = None
    occupation: Optional[str] = Field(default=None, max_length=100)
    monthly_income_baseline: DecimalAnnotation = Field(default=Decimal("0.00"), ge=0)
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE

    class Config:
        populate_by_name = True


# ─── Document: User ───────────────────────────────────────────────────────────
# Mirrors: UserSchema → Collection `users`
class User(Document):
    email: Annotated[str, Indexed(unique=True)]
    password_hash: str = Field(..., exclude=True)  # Never serialised in responses
    profile: Profile = Field(default_factory=Profile.model_construct)
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    active_goals: list[ActiveGoal] = Field(default_factory=list)
    digital_twin_state: DigitalTwinState = Field(default_factory=DigitalTwinState)
    # Bumped on logout / password change to invalidate every previously issued JWT for
    # this user (see core/security.py's "tv" claim + api/dependencies.py's check).
    # Defaults to 0 for both new users and every pre-existing user document (which has
    # no token_version key at all) — matching a missing "tv" claim on already-issued
    # tokens, so this doesn't invalidate anyone's current session when it first deploys.
    token_version: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("active_goals")
    @classmethod
    def goals_cap(cls, v: list[ActiveGoal]) -> list[ActiveGoal]:
        if len(v) > 30:
            raise ValueError("Active goals array cannot exceed 30 items.")
        return v

    class Settings:
        name = "users"               # ← Exact collection name from TS layer
        use_state_management = True

    class Config:
        populate_by_name = True
