"""
services/productivity_service.py — Productivity Analytics Engine (Milestone 2, Pillar B).

Reads existing study history directly from the existing `StudyActivity` Beanie model
(no new collection, study_service.py is untouched) and produces:
  - productivity score      (composite 0-100 over a lookback window)
  - focus score              (average of recorded focus_score; reports insufficient_data
                               when no session has one recorded)
  - weekly trend
  - monthly trend
  - completion percentage    (% of days in a window with at least one logged session)
  - performance prediction   (productivity + exam-score trend projected forward)

This module is fully self-contained: it does not import from or modify any
financial code (models/finance.py, services/finance_service.py, services/forecast_service.py).
The trend-forecasting method (naive / moving-average / linear-regression, chosen by
data volume) mirrors the approach used for financial forecasting but is duplicated
here in miniature rather than shared, to keep the two engines fully decoupled.

All the actual math lives in plain module-level functions operating on plain data
(the StudySessionMetrics dataclass) — no Beanie/Mongo involved — so it is unit-testable
without a live database. ProductivityService only orchestrates: fetch -> pure functions -> schema.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from beanie import PydanticObjectId

from models.study import StudyActivity
from schemas.productivity_schema import (
    AnalyticsMethod,
    CompletionPercentageResponse,
    FocusScoreResponse,
    MonthlyTrendPoint,
    MonthlyTrendResponse,
    PerformancePredictionResponse,
    ProductivityScoreResponse,
    ProductivitySummaryResponse,
    WeeklyProjectionPoint,
    WeeklyTrendPoint,
    WeeklyTrendResponse,
)

DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_WEEKS_BACK = 8
DEFAULT_MONTHS_BACK = 6
DEFAULT_PREDICTION_LOOKBACK_WEEKS = 26
MOVING_AVERAGE_WINDOW = 3

# Composite productivity score weights. Renormalized over whichever components are
# actually present on a given session — only hours is guaranteed; focus and performance
# are weighted in when recorded.
#
# Attendance used to carry 0.30 here and was dropped: it defaulted to 100 and nobody
# ever edited it, so it contributed a constant 30 points to every score and inflated
# the composite for sessions with nothing else recorded. Its weight was redistributed
# proportionally across the three components that carry real signal.
PRODUCTIVITY_WEIGHTS = {"focus": 0.35, "performance": 0.35, "hours": 0.30}
STUDY_HOURS_BENCHMARK = 2.0  # a 2-hour session maps to a full 100 on the "hours" component


# ─── Pure data structures & helpers (no I/O — unit-tested directly) ───────────

@dataclass
class StudySessionMetrics:
    subject: str
    study_hours: float
    focus_score: Optional[float]
    quiz_marks_pct: Optional[float]
    exam_marks_pct: Optional[float]
    session_date: datetime


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _session_productivity_score(session: StudySessionMetrics) -> float:
    """Weighted composite of focus, quiz/exam performance, and study-hours consistency.
    Only components actually present on the session are weighted in — a session with
    hours alone scores purely on hours."""
    values: dict[str, float] = {
        "hours": _clamp((session.study_hours / STUDY_HOURS_BENCHMARK) * 100.0),
    }
    if session.focus_score is not None:
        values["focus"] = _clamp(session.focus_score)

    performance_values = [v for v in (session.quiz_marks_pct, session.exam_marks_pct) if v is not None]
    if performance_values:
        values["performance"] = _clamp(sum(performance_values) / len(performance_values))

    weight_total = sum(PRODUCTIVITY_WEIGHTS[k] for k in values)
    weighted_sum = sum(values[k] * PRODUCTIVITY_WEIGHTS[k] for k in values)
    return round(weighted_sum / weight_total, 2)


def _aggregate_productivity_score(sessions: list[StudySessionMetrics]) -> float:
    if not sessions:
        return 0.0
    scores = [_session_productivity_score(s) for s in sessions]
    return round(sum(scores) / len(scores), 2)


def _average_focus_score(sessions: list[StudySessionMetrics]) -> tuple[float, AnalyticsMethod]:
    recorded = [s.focus_score for s in sessions if s.focus_score is not None]
    if recorded:
        return round(sum(recorded) / len(recorded), 2), AnalyticsMethod.RECORDED_AVERAGE

    # No session has focus_score recorded. There is no proxy for it — attendance used
    # to stand in here, but it defaulted to 100 and measured nothing, so the fallback
    # reported a confident 100% focus for users who had never rated a session. Saying
    # there is no data is the accurate answer.
    return 0.0, AnalyticsMethod.INSUFFICIENT_DATA


def _completion_percentage(
    sessions: list[StudySessionMetrics], window_days: int, reference_date: datetime
) -> tuple[float, int]:
    """% of days in [reference_date - window_days, reference_date] with >=1 logged session."""
    if window_days <= 0:
        return 0.0, 0
    window_start = reference_date - timedelta(days=window_days)
    active_days = {
        s.session_date.date() for s in sessions if window_start <= s.session_date <= reference_date
    }
    percentage = round(min(100.0, (len(active_days) / window_days) * 100.0), 2)
    return percentage, len(active_days)


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday of that week


def _generate_week_range(reference_date: datetime, weeks_back: int) -> list[date]:
    reference_week = _week_start(reference_date.date())
    return [reference_week - timedelta(weeks=i) for i in range(weeks_back - 1, -1, -1)]


def _group_by_week(
    sessions: list[StudySessionMetrics], weeks_back: int, reference_date: datetime
) -> list[WeeklyTrendPoint]:
    week_starts = _generate_week_range(reference_date, weeks_back)
    buckets: dict[date, list[StudySessionMetrics]] = {ws: [] for ws in week_starts}
    for s in sessions:
        ws = _week_start(s.session_date.date())
        if ws in buckets:
            buckets[ws].append(s)

    points = []
    for ws in week_starts:
        bucket = buckets[ws]
        avg_focus, _ = _average_focus_score(bucket)
        points.append(
            WeeklyTrendPoint(
                week_start=ws,
                total_study_hours=round(sum(s.study_hours for s in bucket), 2),
                average_focus_score=avg_focus,
                average_productivity_score=_aggregate_productivity_score(bucket),
                session_count=len(bucket),
            )
        )
    return points


def _generate_month_range(reference_date: datetime, months_back: int) -> list[tuple[int, int]]:
    base = reference_date.year * 12 + (reference_date.month - 1)
    periods = []
    for i in range(months_back - 1, -1, -1):
        total = base - i
        year, month0 = divmod(total, 12)
        periods.append((year, month0 + 1))
    return periods


def _group_by_month(
    sessions: list[StudySessionMetrics], months_back: int, reference_date: datetime
) -> list[MonthlyTrendPoint]:
    months = _generate_month_range(reference_date, months_back)
    buckets: dict[tuple[int, int], list[StudySessionMetrics]] = {m: [] for m in months}
    for s in sessions:
        key = (s.session_date.year, s.session_date.month)
        if key in buckets:
            buckets[key].append(s)

    points = []
    for year, month in months:
        bucket = buckets[(year, month)]
        avg_focus, _ = _average_focus_score(bucket)
        points.append(
            MonthlyTrendPoint(
                year=year,
                month=month,
                total_study_hours=round(sum(s.study_hours for s in bucket), 2),
                average_focus_score=avg_focus,
                average_productivity_score=_aggregate_productivity_score(bucket),
                session_count=len(bucket),
            )
        )
    return points


# ─── Trend forecasting (method chosen by data volume — mirrors the financial
#     forecasting approach, duplicated here to keep the two engines decoupled) ──

def _select_method(n_points: int) -> AnalyticsMethod:
    if n_points <= 0:
        return AnalyticsMethod.INSUFFICIENT_DATA
    if n_points == 1:
        return AnalyticsMethod.NAIVE_LAST_VALUE
    if n_points <= 3:
        return AnalyticsMethod.MOVING_AVERAGE
    return AnalyticsMethod.LINEAR_REGRESSION


def _naive_forecast(values: list[float], periods_ahead: int) -> list[float]:
    return [values[-1]] * periods_ahead


def _moving_average_forecast(
    values: list[float], periods_ahead: int, window: int = MOVING_AVERAGE_WINDOW
) -> list[float]:
    window_values = values[-window:] if len(values) >= window else values
    average = sum(window_values) / len(window_values)
    return [average] * periods_ahead


def _linear_regression_forecast(values: list[float], periods_ahead: int) -> tuple[list[float], float]:
    """Manual least-squares fit over x = 0..n-1. Returns (forecast_values, r_squared)."""
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


def _forecast_series(
    values: list[float], periods_ahead: int
) -> tuple[AnalyticsMethod, list[float], Optional[float]]:
    method = _select_method(len(values))
    if method == AnalyticsMethod.INSUFFICIENT_DATA:
        return method, [0.0] * periods_ahead, None
    if method == AnalyticsMethod.NAIVE_LAST_VALUE:
        return method, _naive_forecast(values, periods_ahead), None
    if method == AnalyticsMethod.MOVING_AVERAGE:
        return method, _moving_average_forecast(values, periods_ahead), None
    forecast, r_squared = _linear_regression_forecast(values, periods_ahead)
    return method, forecast, r_squared


def _compute_confidence(method: AnalyticsMethod, n_points: int, r_squared: Optional[float]) -> float:
    if method in (AnalyticsMethod.INSUFFICIENT_DATA,):
        return 0.0
    if method == AnalyticsMethod.NAIVE_LAST_VALUE:
        return 0.2
    if method == AnalyticsMethod.MOVING_AVERAGE:
        return round(0.35 + 0.05 * (n_points - 2), 2)  # 0.35 .. 0.45 for n=2..3

    # LINEAR_REGRESSION
    r2 = max(0.0, min(1.0, r_squared or 0.0))
    extra_points_bonus = min(0.1, max(0.0, 0.01 * (n_points - 4)))
    confidence = 0.5 + 0.4 * r2 + extra_points_bonus
    return round(min(0.95, max(0.0, confidence)), 2)


# ─── ProductivityService ────────────────────────────────────────────────────

class ProductivityService:
    async def _get_sessions(
        self, user_id: str, start_date: datetime, end_date: Optional[datetime] = None
    ) -> list[StudySessionMetrics]:
        uid = PydanticObjectId(user_id)
        end = end_date or datetime.now(timezone.utc)
        records = await StudyActivity.find(
            {"user_id": uid, "session_date": {"$gte": start_date, "$lte": end}},
            sort=[("session_date", 1)],
        ).to_list()
        return [
            StudySessionMetrics(
                subject=r.subject,
                study_hours=float(r.study_hours),
                focus_score=float(r.focus_score) if r.focus_score is not None else None,
                quiz_marks_pct=float(r.quiz_marks_pct) if r.quiz_marks_pct is not None else None,
                exam_marks_pct=float(r.exam_marks_pct) if r.exam_marks_pct is not None else None,
                session_date=r.session_date,
            )
            for r in records
        ]

    async def get_productivity_score(
        self, user_id: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS
    ) -> ProductivityScoreResponse:
        now = datetime.now(timezone.utc)
        sessions = await self._get_sessions(user_id, now - timedelta(days=lookback_days), now)
        return ProductivityScoreResponse(
            user_id=user_id,
            productivity_score=_aggregate_productivity_score(sessions),
            data_points_used=len(sessions),
            lookback_days=lookback_days,
        )

    async def get_focus_score(
        self, user_id: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS
    ) -> FocusScoreResponse:
        now = datetime.now(timezone.utc)
        sessions = await self._get_sessions(user_id, now - timedelta(days=lookback_days), now)
        score, method = _average_focus_score(sessions)
        return FocusScoreResponse(
            user_id=user_id, focus_score=score, method_used=method, data_points_used=len(sessions)
        )

    async def get_weekly_trend(
        self, user_id: str, weeks_back: int = DEFAULT_WEEKS_BACK
    ) -> WeeklyTrendResponse:
        now = datetime.now(timezone.utc)
        sessions = await self._get_sessions(user_id, now - timedelta(weeks=weeks_back), now)
        return WeeklyTrendResponse(user_id=user_id, trend=_group_by_week(sessions, weeks_back, now))

    async def get_monthly_trend(
        self, user_id: str, months_back: int = DEFAULT_MONTHS_BACK
    ) -> MonthlyTrendResponse:
        now = datetime.now(timezone.utc)
        sessions = await self._get_sessions(user_id, now - timedelta(days=months_back * 31), now)
        return MonthlyTrendResponse(user_id=user_id, trend=_group_by_month(sessions, months_back, now))

    async def get_completion_percentage(
        self, user_id: str, window_days: int = DEFAULT_LOOKBACK_DAYS
    ) -> CompletionPercentageResponse:
        now = datetime.now(timezone.utc)
        sessions = await self._get_sessions(user_id, now - timedelta(days=window_days), now)
        percentage, active_days = _completion_percentage(sessions, window_days, now)
        return CompletionPercentageResponse(
            user_id=user_id, completion_percentage=percentage, active_days=active_days, window_days=window_days
        )

    async def predict_performance(
        self, user_id: str, weeks_ahead: int = 1
    ) -> PerformancePredictionResponse:
        """Projects the weekly productivity trend forward, and — when exam data
        exists — the raw chronological exam-score trend, each with its own
        method/confidence."""
        now = datetime.now(timezone.utc)
        sessions = await self._get_sessions(
            user_id, now - timedelta(weeks=DEFAULT_PREDICTION_LOOKBACK_WEEKS), now
        )
        weekly_points = _group_by_week(sessions, DEFAULT_PREDICTION_LOOKBACK_WEEKS, now)

        active_indices = [i for i, p in enumerate(weekly_points) if p.session_count > 0]
        if active_indices:
            trimmed = weekly_points[active_indices[0]:]
            productivity_values = [p.average_productivity_score for p in trimmed]
            anchor_week = trimmed[-1].week_start
        else:
            productivity_values = []
            anchor_week = _week_start(now.date())

        method, forecast_values, r_squared = _forecast_series(productivity_values, weeks_ahead)
        confidence = _compute_confidence(method, len(productivity_values), r_squared)

        future_weeks = [anchor_week + timedelta(weeks=i) for i in range(1, weeks_ahead + 1)]
        predicted_productivity = [
            WeeklyProjectionPoint(week_start=ws, projected_score=round(v, 2))
            for ws, v in zip(future_weeks, forecast_values)
        ]

        exam_values = [s.exam_marks_pct for s in sessions if s.exam_marks_pct is not None]
        exam_method: Optional[AnalyticsMethod] = None
        exam_confidence: Optional[float] = None
        predicted_exam: Optional[Decimal] = None
        if exam_values:
            exam_method, exam_forecast, exam_r_squared = _forecast_series(exam_values, 1)
            exam_confidence = _compute_confidence(exam_method, len(exam_values), exam_r_squared)
            predicted_exam = Decimal(str(round(exam_forecast[0], 2))) if exam_forecast else None

        return PerformancePredictionResponse(
            user_id=user_id,
            predicted_productivity=predicted_productivity,
            productivity_method_used=method,
            productivity_confidence_score=confidence,
            predicted_exam_score=predicted_exam,
            exam_method_used=exam_method,
            exam_confidence_score=exam_confidence,
            data_points_used=len(productivity_values),
        )

    async def get_summary(self, user_id: str) -> ProductivitySummaryResponse:
        score, focus, weekly, monthly, completion, prediction = await asyncio.gather(
            self.get_productivity_score(user_id),
            self.get_focus_score(user_id),
            self.get_weekly_trend(user_id),
            self.get_monthly_trend(user_id),
            self.get_completion_percentage(user_id),
            self.predict_performance(user_id),
        )
        return ProductivitySummaryResponse(
            user_id=user_id,
            productivity_score=score,
            focus_score=focus,
            weekly_trend=weekly,
            monthly_trend=monthly,
            completion_percentage=completion,
            performance_prediction=prediction,
            generated_at=datetime.now(timezone.utc),
        )


productivity_service = ProductivityService()
