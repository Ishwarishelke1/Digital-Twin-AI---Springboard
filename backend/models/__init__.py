"""
models/__init__.py — Barrel export for all Beanie Document models.
Used by core/database.py for Beanie initialisation.
"""
from models.user import User, UserPreferences, ActiveGoal, DigitalTwinState, Profile
from models.finance import FinancialRecord
from models.study import StudyActivity
from models.habit import HabitTracking
from models.simulation import Simulation, Recommendation, ScenarioResult, MetricPoint
from models.enums import *

__all__ = [
    "User",
    "UserPreferences",
    "ActiveGoal",
    "DigitalTwinState",
    "Profile",
    "FinancialRecord",
    "StudyActivity",
    "HabitTracking",
    "Simulation",
    "Recommendation",
    "ScenarioResult",
    "MetricPoint",
]
