"""
tests/test_trend_prediction_service.py — Unit tests for services/trend_prediction_service.py.

This engine mostly never touches the database directly — it calls the public async
methods of ForecastService, ProductivityService, and HabitAnalyticsService. The one
exception is predict_goal_completions(), which also reads User.active_goals directly
so non-FINANCE goals can be reported as unsupported rather than silently dropped or
given an incorrect finance-based estimate — tests that exercise it mock User.get too.

Two layers:
1. Pure-function tests for the fitness-only forecasting math (no mocks).
2. Service-level tests: patch the three consumed services' public methods with
   AsyncMock returning real Pydantic response instances from their own schemas.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from beanie import PydanticObjectId

from models.enums import GoalCategory
from models.user import ActiveGoal, Profile, User
from schemas.forecast_schema import (
    ForecastMethod,
    GoalCompletionResponse,
    MonthlyProjectionPoint,
    SavingsForecastResponse,
)
from schemas.habit_analytics_schema import HabitTrendResponse, WeeklyHabitPoint
from schemas.productivity_schema import (
    AnalyticsMethod,
    PerformancePredictionResponse,
    WeeklyProjectionPoint,
)
from services.trend_prediction_service import (
    TrendPredictionService,
    _compute_confidence,
    _linear_regression_forecast,
    _select_method,
)

VALID_USER_ID = "507f1f77bcf86cd799439011"


def _patch(target: str, return_value):
    return patch(target, new=AsyncMock(return_value=return_value))


def _patch_user(active_goals):
    user = User.model_construct(
        email="trend-test@example.com", password_hash="x",
        profile=Profile(name="Trend Test", age=30), active_goals=active_goals,
    )
    user.id = PydanticObjectId(VALID_USER_ID)
    return patch.object(User, "get", new=AsyncMock(return_value=user))


# ─────────────────────────────────────────────────────────────────────────────
# Pure-function tests (fitness forecasting math)
# ─────────────────────────────────────────────────────────────────────────────

def test_select_method_boundaries():
    assert _select_method(0) == "insufficient_data"
    assert _select_method(1) == "naive_last_value"
    assert _select_method(3) == "moving_average"
    assert _select_method(4) == "linear_regression"


def test_linear_regression_perfect_upward_trend():
    forecast, r_squared = _linear_regression_forecast([50.0, 60.0, 70.0, 80.0], periods_ahead=1)
    assert forecast[0] == pytest.approx(90.0, abs=1e-6)
    assert r_squared == pytest.approx(1.0, abs=1e-6)


def test_compute_confidence_stays_within_bounds():
    for method, n, r2 in [
        ("insufficient_data", 0, None),
        ("naive_last_value", 1, None),
        ("moving_average", 3, None),
        ("linear_regression", 6, 0.9),
    ]:
        confidence = _compute_confidence(method, n, r2)
        assert 0.0 <= confidence <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Service-level tests (Financial / Productivity / Habit services mocked)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_predict_savings_trend_wraps_forecast_service_result():
    fake_result = SavingsForecastResponse(
        user_id=VALID_USER_ID,
        projections=[MonthlyProjectionPoint(year=2026, month=9, projected_amount=Decimal("1100.00"))],
        method_used=ForecastMethod.LINEAR_REGRESSION,
        data_points_used=6,
        confidence_score=0.87,
    )
    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.forecast_service.forecast_monthly_savings", fake_result):
        result = await service.predict_savings_trend(VALID_USER_ID, months_ahead=1)

    assert result.user_id == VALID_USER_ID
    assert result.method_used == "linear_regression"
    assert result.confidence_score == 0.87
    assert result.data_points_used == 6
    assert result.projected_savings[0].period == "2026-09"
    assert result.projected_savings[0].value == 1100.0


@pytest.mark.asyncio
async def test_predict_study_trend_wraps_productivity_service_result():
    fake_result = PerformancePredictionResponse(
        user_id=VALID_USER_ID,
        predicted_productivity=[WeeklyProjectionPoint(week_start=date(2026, 8, 17), projected_score=82.5)],
        productivity_method_used=AnalyticsMethod.LINEAR_REGRESSION,
        productivity_confidence_score=0.75,
        predicted_exam_score=Decimal("88.0"),
        exam_method_used=AnalyticsMethod.LINEAR_REGRESSION,
        exam_confidence_score=0.7,
        data_points_used=5,
    )
    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.productivity_service.predict_performance", fake_result):
        result = await service.predict_study_trend(VALID_USER_ID, weeks_ahead=1)

    assert result.productivity_method_used == "linear_regression"
    assert result.productivity_confidence_score == 0.75
    assert result.predicted_exam_score == 88.0
    assert result.exam_method_used == "linear_regression"
    assert result.projected_productivity[0].period == "2026-08-17"
    assert result.projected_productivity[0].value == 82.5


@pytest.mark.asyncio
async def test_predict_study_trend_handles_no_exam_prediction():
    fake_result = PerformancePredictionResponse(
        user_id=VALID_USER_ID,
        predicted_productivity=[WeeklyProjectionPoint(week_start=date(2026, 8, 17), projected_score=50.0)],
        productivity_method_used=AnalyticsMethod.INSUFFICIENT_DATA,
        productivity_confidence_score=0.0,
        predicted_exam_score=None,
        exam_method_used=None,
        exam_confidence_score=None,
        data_points_used=0,
    )
    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.productivity_service.predict_performance", fake_result):
        result = await service.predict_study_trend(VALID_USER_ID)
    assert result.predicted_exam_score is None
    assert result.exam_method_used is None
    assert result.exam_confidence_score is None


@pytest.mark.asyncio
async def test_predict_fitness_trend_only_counts_active_weeks():
    trend = HabitTrendResponse(
        user_id=VALID_USER_ID,
        daily=[],
        weekly=[
            WeeklyHabitPoint(
                week_start=date(2026, 7, 27), days_logged=5, average_habit_score=60.0,
                average_sleep_hours=7.0, average_exercise_minutes=30.0,
                average_water_intake_liters=2.0, average_screen_time_hours=5.0,
            ),
            WeeklyHabitPoint(
                week_start=date(2026, 8, 3), days_logged=0, average_habit_score=0.0,
                average_sleep_hours=0.0, average_exercise_minutes=0.0,
                average_water_intake_liters=0.0, average_screen_time_hours=0.0,
            ),
            WeeklyHabitPoint(
                week_start=date(2026, 8, 10), days_logged=6, average_habit_score=80.0,
                average_sleep_hours=7.5, average_exercise_minutes=35.0,
                average_water_intake_liters=2.2, average_screen_time_hours=4.5,
            ),
        ],
        monthly=[],
    )
    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.habit_analytics_service.get_habit_trend", trend):
        result = await service.predict_fitness_trend(VALID_USER_ID, weeks_ahead=1)

    # Only the 2 active (days_logged > 0) weeks count as data points, not the zero-filled one.
    assert result.data_points_used == 2
    assert result.method_used == "moving_average"
    assert result.projected_fitness_score[0].period == "2026-08-17"  # week after the last active week


@pytest.mark.asyncio
async def test_predict_fitness_trend_insufficient_when_no_active_weeks():
    trend = HabitTrendResponse(
        user_id=VALID_USER_ID,
        daily=[],
        weekly=[
            WeeklyHabitPoint(
                week_start=date(2026, 8, 3), days_logged=0, average_habit_score=0.0,
                average_sleep_hours=0.0, average_exercise_minutes=0.0,
                average_water_intake_liters=0.0, average_screen_time_hours=0.0,
            ),
        ],
        monthly=[],
    )
    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.habit_analytics_service.get_habit_trend", trend):
        result = await service.predict_fitness_trend(VALID_USER_ID)
    assert result.method_used == "insufficient_data"
    assert result.confidence_score == 0.0
    assert result.data_points_used == 0


@pytest.mark.asyncio
async def test_predict_goal_completions_wraps_forecast_service_goals():
    fake_goals = [
        GoalCompletionResponse(
            goal_id="g1", title="Emergency Fund", category=GoalCategory.FINANCE,
            current_value=Decimal("0"), target_value=Decimal("1000"),
            target_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
            monthly_projected_delta=Decimal("200"),
            estimated_months_remaining=5,
            estimated_completion_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
            on_track=True,
            method_used=ForecastMethod.LINEAR_REGRESSION,
            confidence_score=0.8,
        )
    ]
    finance_goal = ActiveGoal(
        goal_id="g1", title="Emergency Fund", category=GoalCategory.FINANCE,
        target_value=Decimal("1000"), current_value=Decimal("0"), unit="USD",
        target_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.forecast_service.estimate_all_goal_completions", fake_goals), \
         _patch_user([finance_goal]):
        result = await service.predict_goal_completions(VALID_USER_ID)

    assert len(result) == 1
    assert result[0].goal_id == "g1"
    assert result[0].category == "FINANCE"
    assert result[0].method_used == "linear_regression"
    assert result[0].on_track is True


@pytest.mark.asyncio
async def test_predict_goal_completions_reports_non_finance_goals_as_insufficient_data():
    """Study/Habit/Fitness goals shouldn't be silently dropped or given an incorrect
    finance-based estimate — they're reported as unsupported instead."""
    study_goal = ActiveGoal(
        goal_id="g2", title="Finish DSA course", category=GoalCategory.STUDY,
        target_value=Decimal("100"), current_value=Decimal("40"), unit="percent",
        target_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.forecast_service.estimate_all_goal_completions", []), \
         _patch_user([study_goal]):
        result = await service.predict_goal_completions(VALID_USER_ID)

    assert len(result) == 1
    assert result[0].goal_id == "g2"
    assert result[0].category == "STUDY"
    assert result[0].method_used == "insufficient_data"
    assert result[0].on_track is None


@pytest.mark.asyncio
async def test_predict_all_trends_aggregates_and_averages_confidence():
    savings_fake = SavingsForecastResponse(
        user_id=VALID_USER_ID, projections=[], method_used=ForecastMethod.NAIVE_LAST_VALUE,
        data_points_used=1, confidence_score=0.2,
    )
    study_fake = PerformancePredictionResponse(
        user_id=VALID_USER_ID, predicted_productivity=[],
        productivity_method_used=AnalyticsMethod.NAIVE_LAST_VALUE, productivity_confidence_score=0.2,
        predicted_exam_score=None, exam_method_used=None, exam_confidence_score=None, data_points_used=1,
    )
    fitness_trend_fake = HabitTrendResponse(user_id=VALID_USER_ID, daily=[], weekly=[], monthly=[])
    goals_fake: list = []

    service = TrendPredictionService()
    with _patch("services.trend_prediction_service.forecast_service.forecast_monthly_savings", savings_fake), \
         _patch("services.trend_prediction_service.productivity_service.predict_performance", study_fake), \
         _patch("services.trend_prediction_service.habit_analytics_service.get_habit_trend", fitness_trend_fake), \
         _patch("services.trend_prediction_service.forecast_service.estimate_all_goal_completions", goals_fake), \
         _patch_user([]):
        summary = await service.predict_all_trends(VALID_USER_ID)

    # savings=0.2, study=0.2, fitness=insufficient_data->0.0, no goals, no exam confidence
    expected_avg = round((0.2 + 0.2 + 0.0) / 3, 2)
    assert summary.overall_confidence_score == pytest.approx(expected_avg)
    assert summary.user_id == VALID_USER_ID
    assert summary.goals == []
