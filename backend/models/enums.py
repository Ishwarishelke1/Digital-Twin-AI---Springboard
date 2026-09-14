"""
models/enums.py — Centralized Python Enums, exactly mirroring backend/database/schemas/enums.ts.
All string values are IDENTICAL to the TypeScript enums to preserve 100% MongoDB compatibility.
DO NOT alter the string values — they are stored in MongoDB documents.
"""
from enum import Enum


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    NON_BINARY = "NON_BINARY"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


class RiskTolerance(str, Enum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class GoalCategory(str, Enum):
    FINANCE = "FINANCE"
    STUDY = "STUDY"
    HABIT = "HABIT"
    FITNESS = "FITNESS"
    CAREER = "CAREER"


class GoalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class TransactionType(str, Enum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    SAVINGS_DEPOSIT = "SAVINGS_DEPOSIT"
    INVESTMENT = "INVESTMENT"


class FinancialCategory(str, Enum):
    HOUSING = "HOUSING"
    FOOD = "FOOD"
    UTILITIES = "UTILITIES"
    SALARY = "SALARY"
    ENTERTAINMENT = "ENTERTAINMENT"
    HEALTH = "HEALTH"
    EDUCATION = "EDUCATION"
    INVESTMENT = "INVESTMENT"
    TRANSPORT = "TRANSPORT"
    SAVINGS = "SAVINGS"
    OTHER = "OTHER"


class RecurringFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY = "ANNUALLY"


class SessionType(str, Enum):
    DEEP_WORK = "DEEP_WORK"
    REVIEW = "REVIEW"
    LECTURE = "LECTURE"
    PRACTICE_EXAM = "PRACTICE_EXAM"
    ASSIGNMENT = "ASSIGNMENT"
    RESEARCH = "RESEARCH"


class BurnoutRisk(str, Enum):
    LOW_RISK = "LOW_RISK"
    MODERATE_RISK = "MODERATE_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL_BURNOUT = "CRITICAL_BURNOUT"
    UNKNOWN = "UNKNOWN"


class SimulationDomain(str, Enum):
    FINANCE = "FINANCE"
    ACADEMIC = "ACADEMIC"
    HABIT = "HABIT"
    HYBRID_LIFESTYLE = "HYBRID_LIFESTYLE"


class SimulationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class RecommendationCategory(str, Enum):
    FINANCE = "FINANCE"
    ACADEMIC = "ACADEMIC"
    HABIT = "HABIT"
    FITNESS = "FITNESS"
    PRODUCTIVITY = "PRODUCTIVITY"
    WELL_BEING = "WELL_BEING"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class UserFeedback(str, Enum):
    HELPFUL = "HELPFUL"
    UNHELPFUL = "UNHELPFUL"
    IRRELEVANT = "IRRELEVANT"


class RecommendationDomain(str, Enum):
    """Which page a cached AI recommendation set belongs to."""
    HABITS = "HABITS"
    STUDY = "STUDY"


class SleepBand(str, Enum):
    """Sleep filter buckets for the habit history table. The boundaries are
    habit_analytics_service.SLEEP_HEALTHY_RANGE — imported, never re-typed, so the
    table and the analytics engine cannot end up disagreeing about what counts as
    a healthy night."""
    BELOW = "BELOW"
    HEALTHY = "HEALTHY"
    ABOVE = "ABOVE"
