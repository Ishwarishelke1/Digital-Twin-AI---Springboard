"""
schemas/habit_analytics_schema.py — Pydantic response schemas for the Habit Analytics Engine.
Follows the same style as forecast_schema.py / productivity_schema.py, and is fully
self-contained (no shared types with either).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class HabitStatus(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class DailyHabitPoint(BaseModel):
    date: date
    logged: bool
    habit_score: float
    sleep_hours: Optional[float] = None
    exercise_minutes: Optional[int] = None
    water_intake_liters: Optional[float] = None
    screen_time_hours: Optional[float] = None


class WeeklyHabitPoint(BaseModel):
    week_start: date
    days_logged: int
    average_habit_score: float
    average_sleep_hours: float
    average_exercise_minutes: float
    average_water_intake_liters: float
    average_screen_time_hours: float


class MonthlyHabitPoint(BaseModel):
    year: int
    month: int
    days_logged: int
    average_habit_score: float
    average_sleep_hours: float
    average_exercise_minutes: float
    average_water_intake_liters: float
    average_screen_time_hours: float


class HabitTrendResponse(BaseModel):
    """Habit trend analyzed at all three granularities."""
    user_id: str
    daily: list[DailyHabitPoint]
    weekly: list[WeeklyHabitPoint]
    monthly: list[MonthlyHabitPoint]


class ConsistencyScoreResponse(BaseModel):
    user_id: str
    consistency_score: float  # % of days in the window with a logged entry
    logged_days: int
    window_days: int


class HabitStreakResponse(BaseModel):
    user_id: str
    current_streak: int
    longest_streak: int
    streak_active: bool  # True if today or yesterday has a log (streak not yet broken)


class HabitInsight(BaseModel):
    habit: str  # "sleep" | "exercise" | "water" | "screen_time"
    status: HabitStatus
    average_value: float
    unit: str
    detail: str


class PositiveHabitsResponse(BaseModel):
    user_id: str
    habits: list[HabitInsight]
    window_days: int


class NegativeHabitsResponse(BaseModel):
    user_id: str
    habits: list[HabitInsight]
    window_days: int


class MissedHabitsResponse(BaseModel):
    user_id: str
    missed_days: int
    window_days: int
    missed_dates: list[date]


class HabitAnalyticsSummaryResponse(BaseModel):
    user_id: str
    consistency_score: ConsistencyScoreResponse
    habit_streak: HabitStreakResponse
    positive_habits: PositiveHabitsResponse
    negative_habits: NegativeHabitsResponse
    missed_habits: MissedHabitsResponse
    habit_trend: HabitTrendResponse
    generated_at: datetime
