"""
services/trend_prediction_service.py — Trend Prediction Engine (Milestone 2, Pillar C).

Does NOT reimplement any other engine's logic. It consumes the *public outputs*
of the three existing engines:
  - services.forecast_service.forecast_service            (Savings, Goals)
  - services.productivity_service.productivity_service    (Study)
  - services.habit_analytics_service.habit_analytics_service (Fitness — trend data only)

...and produces four forward-looking predictions, each carrying its own
probability/confidence score:
  - Savings  -> thin wrapper around ForecastService.forecast_monthly_savings()
  - Study    -> thin wrapper around ProductivityService.predict_performance()
  - Fitness  -> HabitAnalyticsService only reports historical/current trend, so this
                engine applies its own forward projection on top of that trend
  - Goals    -> wraps ForecastService.estimate_all_goal_completions() for FINANCE
                goals; also reads User.active_goals directly (the one direct DB
                read in this module) so STUDY/HABIT/FITNESS goals can be reported
                as "insufficient_data" instead of being silently dropped or given
                an incorrect finance-based estimate

This module is kept independent: it never modifies the three services it consumes,
and its own fitness-forecasting math is self-contained (duplicated in miniature from
the same naive/moving-average/linear-regression pattern used elsewhere in the codebase,
rather than imported, so this engine has no hard dependency on any other engine's
internals — only on their public async method signatures).
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from beanie import PydanticObjectId

from core.exceptions import NotFoundError
from models.enums import GoalCategory
from models.user import User

from schemas.trend_prediction_schema import (
    FitnessTrendPrediction,
    GoalTrendPrediction,
    ProjectedValue,
    SavingsTrendPrediction,
    StudyTrendPrediction,
    TrendPredictionSummary,
)
from services.forecast_service import forecast_service
from services.habit_analytics_service import habit_analytics_service
from services.productivity_service import productivity_service

DEFAULT_MONTHS_AHEAD = 1
DEFAULT_WEEKS_AHEAD = 1

_METHOD_INSUFFICIENT = "insufficient_data"
_METHOD_NAIVE = "naive_last_value"
_METHOD_MOVING_AVERAGE = "moving_average"
_METHOD_LINEAR_REGRESSION = "linear_regression"
_MOVING_AVERAGE_WINDOW = 3


# ─── Fitness-only forecasting math (pure, unit-tested directly) ──────────────
# Habit Analytics only reports past/current trend, not a forward projection —
# this is the one place this engine has to do its own forecasting.

def _select_method(n_points: int) -> str:
    if n_points <= 0:
        return _METHOD_INSUFFICIENT
    if n_points == 1:
        return _METHOD_NAIVE
    if n_points <= 3:
        return _METHOD_MOVING_AVERAGE
    return _METHOD_LINEAR_REGRESSION


def _naive_forecast(values: list[float], periods_ahead: int) -> list[float]:
    return [values[-1]] * periods_ahead


def _moving_average_forecast(
    values: list[float], periods_ahead: int, window: int = _MOVING_AVERAGE_WINDOW
) -> list[float]:
    window_values = values[-window:] if len(values) >= window else values
    average = sum(window_values) / len(window_values)
    return [average] * periods_ahead


def _linear_regression_forecast(values: list[float], periods_ahead: int) -> tuple[list[float], float]:
    n = len(values)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n

    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    slope = (ss_xy / ss_xx) if ss_xx != 0 else 0.0
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in values)
    if ss_tot == 0:
        r_squared = 1.0
    else:
        predicted = [slope * x + intercept for x in xs]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(values, predicted))
        r_squared = max(0.0, 1 - (ss_res / ss_tot))

    forecast = [slope * (n + i) + intercept for i in range(periods_ahead)]
    return forecast, r_squared


def _forecast_series(values: list[float], periods_ahead: int) -> tuple[str, list[float], Optional[float]]:
    method = _select_method(len(values))
    if method == _METHOD_INSUFFICIENT:
        return method, [0.0] * periods_ahead, None
    if method == _METHOD_NAIVE:
        return method, _naive_forecast(values, periods_ahead), None
    if method == _METHOD_MOVING_AVERAGE:
        return method, _moving_average_forecast(values, periods_ahead), None
    forecast, r_squared = _linear_regression_forecast(values, periods_ahead)
    return method, forecast, r_squared


def _compute_confidence(method: str, n_points: int, r_squared: Optional[float]) -> float:
    if method == _METHOD_INSUFFICIENT:
        return 0.0
    if method == _METHOD_NAIVE:
        return 0.2
    if method == _METHOD_MOVING_AVERAGE:
        return round(0.35 + 0.05 * (n_points - 2), 2)
    r2 = max(0.0, min(1.0, r_squared or 0.0))
    extra_points_bonus = min(0.1, max(0.0, 0.01 * (n_points - 4)))
    confidence = 0.5 + 0.4 * r2 + extra_points_bonus
    return round(min(0.95, max(0.0, confidence)), 2)


# ─── TrendPredictionService ────────────────────────────────────────────────

class TrendPredictionService:
    async def predict_savings_trend(
        self, user_id: str, months_ahead: int = DEFAULT_MONTHS_AHEAD
    ) -> SavingsTrendPrediction:
        result = await forecast_service.forecast_monthly_savings(user_id, months_ahead)
        return SavingsTrendPrediction(
            user_id=user_id,
            projected_savings=[
                ProjectedValue(period=f"{p.year}-{p.month:02d}", value=float(p.projected_amount))
                for p in result.projections
            ],
            method_used=result.method_used.value,
            confidence_score=result.confidence_score,
            data_points_used=result.data_points_used,
        )

    async def predict_study_trend(
        self, user_id: str, weeks_ahead: int = DEFAULT_WEEKS_AHEAD
    ) -> StudyTrendPrediction:
        result = await productivity_service.predict_performance(user_id, weeks_ahead)
        return StudyTrendPrediction(
            user_id=user_id,
            projected_productivity=[
                ProjectedValue(period=p.week_start.isoformat(), value=p.projected_score)
                for p in result.predicted_productivity
            ],
            productivity_method_used=result.productivity_method_used.value,
            productivity_confidence_score=result.productivity_confidence_score,
            predicted_exam_score=float(result.predicted_exam_score) if result.predicted_exam_score is not None else None,
            exam_method_used=result.exam_method_used.value if result.exam_method_used is not None else None,
            exam_confidence_score=result.exam_confidence_score,
            data_points_used=result.data_points_used,
        )

    async def predict_fitness_trend(
        self, user_id: str, weeks_ahead: int = DEFAULT_WEEKS_AHEAD
    ) -> FitnessTrendPrediction:
        trend = await habit_analytics_service.get_habit_trend(user_id)

        # Only weeks that actually had logged days count as real data points —
        # a zero-filled "no data" week is not the same signal as a genuine 0 score.
        active_weeks = [p for p in trend.weekly if p.days_logged > 0]
        values = [p.average_habit_score for p in active_weeks]

        if active_weeks:
            anchor: date = active_weeks[-1].week_start
        elif trend.weekly:
            anchor = trend.weekly[-1].week_start
        else:
            anchor = datetime.now(timezone.utc).date()

        method, forecast_values, r_squared = _forecast_series(values, weeks_ahead)
        confidence = _compute_confidence(method, len(values), r_squared)

        future_weeks = [anchor + timedelta(weeks=i) for i in range(1, weeks_ahead + 1)]
        projected = [
            ProjectedValue(period=ws.isoformat(), value=round(v, 2))
            for ws, v in zip(future_weeks, forecast_values)
        ]

        return FitnessTrendPrediction(
            user_id=user_id,
            projected_fitness_score=projected,
            method_used=method,
            confidence_score=confidence,
            data_points_used=len(values),
        )

    async def predict_goal_completions(self, user_id: str) -> list[GoalTrendPrediction]:
        """
        Returns goal predictions for all supported goal categories.

        Finance goals use the existing financial completion estimator.
        Study/Habit/Fitness goals are currently returned as unsupported rather
        than being given an incorrect finance-based completion calculation.
        """

        user = await User.get(PydanticObjectId(user_id))
        if not user:
            raise NotFoundError("User", user_id)

        finance_results = await forecast_service.estimate_all_goal_completions(user_id)
        finance_by_id = {g.goal_id: g for g in finance_results}

        predictions: list[GoalTrendPrediction] = []

        for goal in user.active_goals:
            if goal.category == GoalCategory.FINANCE:
                g = finance_by_id.get(goal.goal_id)
                if g is not None:
                    predictions.append(
                        GoalTrendPrediction(
                            goal_id=g.goal_id,
                            title=g.title,
                            category=g.category.value,
                            estimated_months_remaining=g.estimated_months_remaining,
                            estimated_completion_date=g.estimated_completion_date,
                            on_track=g.on_track,
                            method_used=g.method_used.value,
                            confidence_score=g.confidence_score,
                        )
                    )

            elif goal.category in {
                GoalCategory.STUDY,
                GoalCategory.HABIT,
                GoalCategory.FITNESS,
            }:
                predictions.append(
                    GoalTrendPrediction(
                        goal_id=goal.goal_id,
                        title=goal.title,
                        category=goal.category.value,
                        estimated_months_remaining=None,
                        estimated_completion_date=None,
                        on_track=None,
                        method_used="insufficient_data",
                        confidence_score=0.0,
                    )
                )

        return predictions

    async def predict_all_trends(
        self,
        user_id: str,
        months_ahead: int = DEFAULT_MONTHS_AHEAD,
        weeks_ahead: int = DEFAULT_WEEKS_AHEAD,
    ) -> TrendPredictionSummary:
        savings, study, fitness, goals = await asyncio.gather(
            self.predict_savings_trend(user_id, months_ahead),
            self.predict_study_trend(user_id, weeks_ahead),
            self.predict_fitness_trend(user_id, weeks_ahead),
            self.predict_goal_completions(user_id),
        )

        confidences = [savings.confidence_score, study.productivity_confidence_score, fitness.confidence_score]
        if study.exam_confidence_score is not None:
            confidences.append(study.exam_confidence_score)
        confidences.extend(g.confidence_score for g in goals)
        overall_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

        return TrendPredictionSummary(
            user_id=user_id,
            savings=savings,
            study=study,
            fitness=fitness,
            goals=goals,
            overall_confidence_score=overall_confidence,
            generated_at=datetime.now(timezone.utc),
        )


trend_prediction_service = TrendPredictionService()
