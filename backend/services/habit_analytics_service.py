"""
services/habit_analytics_service.py — Habit Analytics Engine (Milestone 2, Pillar B).

Reads existing habit history directly from the existing `HabitTracking` Beanie model
(no new collection, habit_service.py is untouched) and analyzes it at daily, weekly,
and monthly granularity to produce:
  - consistency score   (% of days in a window with a logged check-in)
  - habit streak        (current + longest consecutive-day logging streak)
  - positive habits     (tracked metrics consistently meeting healthy thresholds)
  - negative habits     (tracked metrics consistently missing healthy thresholds)
  - missed habits       (days in the window with no log at all)
  - habit trend         (daily / weekly / monthly breakdown)

This module is fully self-contained: it does not import from or modify any
financial or productivity code. Healthy-range thresholds reuse the exact 4D
biometric feature space already documented in
backend/database/docs/ml_feature_mapping.md (sleep_hours, exercise_minutes,
water_intake_liters, screen_time_hours) — simple threshold scoring, not the
K-Means clustering described there, to avoid overengineering a Milestone 2
slice that only asked for these six outputs.

All the actual math lives in plain module-level functions operating on plain data
(the HabitLogMetrics dataclass) — no Beanie/Mongo involved — so it is unit-testable
without a live database. HabitAnalyticsService only orchestrates: fetch -> pure
functions -> schema (all of which are directly JSON-serializable via
`.model_dump()` / `.model_dump_json()`).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from beanie import PydanticObjectId

from models.habit import HabitTracking
from schemas.habit_analytics_schema import (
    ConsistencyScoreResponse,
    DailyHabitPoint,
    HabitAnalyticsSummaryResponse,
    HabitInsight,
    HabitStatus,
    HabitStreakResponse,
    HabitTrendResponse,
    MissedHabitsResponse,
    MonthlyHabitPoint,
    NegativeHabitsResponse,
    PositiveHabitsResponse,
    WeeklyHabitPoint,
)

DEFAULT_WINDOW_DAYS = 30
DEFAULT_STREAK_LOOKBACK_DAYS = 90
DEFAULT_DAILY_TREND_DAYS = 14
DEFAULT_WEEKS_BACK = 8
DEFAULT_MONTHS_BACK = 6

# Healthy-range thresholds for the 4D biometric feature space, mirroring
# ml_feature_mapping.md. A metric is classified "positive" when its windowed
# average scores >= POSITIVE_THRESHOLD on its own 0-100 scale.
POSITIVE_THRESHOLD = 70.0
SLEEP_HEALTHY_RANGE = (7.0, 9.0)          # hours
EXERCISE_TARGET_MINUTES = 30.0
WATER_TARGET_LITERS = 2.0
SCREEN_TIME_HEALTHY_MAX = 6.0             # hours


# ─── Pure data structures & helpers (no I/O — unit-tested directly) ───────────

@dataclass
class HabitLogMetrics:
    log_date: datetime
    sleep_hours: float
    exercise_minutes: int
    water_intake_liters: float
    screen_time_hours: float


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _sleep_score(hours: float) -> float:
    lo, hi = SLEEP_HEALTHY_RANGE
    if lo <= hours <= hi:
        return 100.0
    deficit_or_excess = (lo - hours) if hours < lo else (hours - hi)
    return _clamp(100.0 - deficit_or_excess * 25.0)


def _exercise_score(minutes: float) -> float:
    return _clamp((minutes / EXERCISE_TARGET_MINUTES) * 100.0)


def _water_score(liters: float) -> float:
    return _clamp((liters / WATER_TARGET_LITERS) * 100.0)


def _screen_time_score(hours: float) -> float:
    if hours <= SCREEN_TIME_HEALTHY_MAX:
        return 100.0
    excess = hours - SCREEN_TIME_HEALTHY_MAX
    return _clamp(100.0 - excess * 20.0)


def _daily_habit_score(log: HabitLogMetrics) -> float:
    """Equal-weighted composite over the 4D biometric feature space."""
    scores = [
        _sleep_score(log.sleep_hours),
        _exercise_score(log.exercise_minutes),
        _water_score(log.water_intake_liters),
        _screen_time_score(log.screen_time_hours),
    ]
    return round(sum(scores) / len(scores), 2)


def _consistency_score(
    logs: list[HabitLogMetrics], window_days: int, reference_date: datetime
) -> tuple[float, int]:
    """Window is the same window_days calendar dates _missed_days uses (today
    plus the window_days-1 days before it) — logged_days + missed_days always
    sums to window_days. An earlier version used an inclusive-both-ends range
    here (window_days + 1 distinct dates), which double-counted the far edge
    of the window relative to _missed_days."""
    if window_days <= 0:
        return 0.0, 0
    window_dates = {(reference_date - timedelta(days=i)).date() for i in range(window_days)}
    logged_days = {l.log_date.date() for l in logs} & window_dates
    percentage = round(min(100.0, (len(logged_days) / window_days) * 100.0), 2)
    return percentage, len(logged_days)


def _compute_streak(
    logs: list[HabitLogMetrics], reference_date: datetime
) -> tuple[int, int, bool]:
    """Returns (current_streak, longest_streak, streak_active).
    A streak is "active" if today or yesterday has a log — i.e. not yet broken,
    even if today's entry hasn't been logged yet (common habit-tracker semantics)."""
    logged_dates = {l.log_date.date() for l in logs}
    if not logged_dates:
        return 0, 0, False

    sorted_dates = sorted(logged_dates)
    longest = 1
    run = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)

    today = reference_date.date()
    if today in logged_dates:
        cursor = today
    elif (today - timedelta(days=1)) in logged_dates:
        cursor = today - timedelta(days=1)
    else:
        return 0, longest, False

    current = 0
    while cursor in logged_dates:
        current += 1
        cursor -= timedelta(days=1)

    return current, longest, True


def _classify_habits(logs: list[HabitLogMetrics]) -> tuple[list[HabitInsight], list[HabitInsight]]:
    """Splits the 4 tracked biometrics into positive/negative based on their
    windowed average score against POSITIVE_THRESHOLD."""
    if not logs:
        return [], []

    n = len(logs)
    avg_sleep = sum(l.sleep_hours for l in logs) / n
    avg_exercise = sum(l.exercise_minutes for l in logs) / n
    avg_water = sum(l.water_intake_liters for l in logs) / n
    avg_screen = sum(l.screen_time_hours for l in logs) / n

    candidates = [
        ("sleep", avg_sleep, "hours", _sleep_score(avg_sleep), "Healthy range is 7-9 hours/night."),
        ("exercise", avg_exercise, "minutes", _exercise_score(avg_exercise), "Target is 30+ minutes/day."),
        ("water", avg_water, "liters", _water_score(avg_water), "Target is 2.0+ liters/day."),
        ("screen_time", avg_screen, "hours", _screen_time_score(avg_screen), "Target is 6 hours/day or less."),
    ]

    positive: list[HabitInsight] = []
    negative: list[HabitInsight] = []
    for habit, avg_value, unit, score, detail in candidates:
        insight = HabitInsight(
            habit=habit,
            status=HabitStatus.POSITIVE if score >= POSITIVE_THRESHOLD else HabitStatus.NEGATIVE,
            average_value=round(avg_value, 2),
            unit=unit,
            detail=detail,
        )
        (positive if score >= POSITIVE_THRESHOLD else negative).append(insight)
    return positive, negative


def _missed_days(
    logs: list[HabitLogMetrics], window_days: int, reference_date: datetime
) -> list[date]:
    if window_days <= 0:
        return []
    logged_dates = {l.log_date.date() for l in logs}
    all_days = [(reference_date - timedelta(days=i)).date() for i in range(window_days)]
    return sorted(d for d in all_days if d not in logged_dates)


def _build_daily_trend(
    logs: list[HabitLogMetrics], days_back: int, reference_date: datetime
) -> list[DailyHabitPoint]:
    by_date = {l.log_date.date(): l for l in logs}
    days = [(reference_date - timedelta(days=i)).date() for i in range(days_back - 1, -1, -1)]
    points = []
    for d in days:
        log = by_date.get(d)
        if log is None:
            points.append(DailyHabitPoint(date=d, logged=False, habit_score=0.0))
        else:
            points.append(
                DailyHabitPoint(
                    date=d,
                    logged=True,
                    habit_score=_daily_habit_score(log),
                    sleep_hours=log.sleep_hours,
                    exercise_minutes=log.exercise_minutes,
                    water_intake_liters=log.water_intake_liters,
                    screen_time_hours=log.screen_time_hours,
                )
            )
    return points


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday of that week


def _summarize_week(week_start: date, bucket: list[HabitLogMetrics]) -> WeeklyHabitPoint:
    if not bucket:
        return WeeklyHabitPoint(
            week_start=week_start, days_logged=0, average_habit_score=0.0,
            average_sleep_hours=0.0, average_exercise_minutes=0.0,
            average_water_intake_liters=0.0, average_screen_time_hours=0.0,
        )
    n = len(bucket)
    return WeeklyHabitPoint(
        week_start=week_start,
        days_logged=n,
        average_habit_score=round(sum(_daily_habit_score(l) for l in bucket) / n, 2),
        average_sleep_hours=round(sum(l.sleep_hours for l in bucket) / n, 2),
        average_exercise_minutes=round(sum(l.exercise_minutes for l in bucket) / n, 2),
        average_water_intake_liters=round(sum(l.water_intake_liters for l in bucket) / n, 2),
        average_screen_time_hours=round(sum(l.screen_time_hours for l in bucket) / n, 2),
    )


def _build_weekly_trend(
    logs: list[HabitLogMetrics], weeks_back: int, reference_date: datetime
) -> list[WeeklyHabitPoint]:
    reference_week = _week_start(reference_date.date())
    week_starts = [reference_week - timedelta(weeks=i) for i in range(weeks_back - 1, -1, -1)]
    buckets: dict[date, list[HabitLogMetrics]] = {ws: [] for ws in week_starts}
    for l in logs:
        ws = _week_start(l.log_date.date())
        if ws in buckets:
            buckets[ws].append(l)
    return [_summarize_week(ws, buckets[ws]) for ws in week_starts]


def _generate_month_range(reference_date: datetime, months_back: int) -> list[tuple[int, int]]:
    base = reference_date.year * 12 + (reference_date.month - 1)
    periods = []
    for i in range(months_back - 1, -1, -1):
        total = base - i
        year, month0 = divmod(total, 12)
        periods.append((year, month0 + 1))
    return periods


def _summarize_month(year: int, month: int, bucket: list[HabitLogMetrics]) -> MonthlyHabitPoint:
    if not bucket:
        return MonthlyHabitPoint(
            year=year, month=month, days_logged=0, average_habit_score=0.0,
            average_sleep_hours=0.0, average_exercise_minutes=0.0,
            average_water_intake_liters=0.0, average_screen_time_hours=0.0,
        )
    n = len(bucket)
    return MonthlyHabitPoint(
        year=year,
        month=month,
        days_logged=n,
        average_habit_score=round(sum(_daily_habit_score(l) for l in bucket) / n, 2),
        average_sleep_hours=round(sum(l.sleep_hours for l in bucket) / n, 2),
        average_exercise_minutes=round(sum(l.exercise_minutes for l in bucket) / n, 2),
        average_water_intake_liters=round(sum(l.water_intake_liters for l in bucket) / n, 2),
        average_screen_time_hours=round(sum(l.screen_time_hours for l in bucket) / n, 2),
    )


def _build_monthly_trend(
    logs: list[HabitLogMetrics], months_back: int, reference_date: datetime
) -> list[MonthlyHabitPoint]:
    months = _generate_month_range(reference_date, months_back)
    buckets: dict[tuple[int, int], list[HabitLogMetrics]] = {m: [] for m in months}
    for l in logs:
        key = (l.log_date.year, l.log_date.month)
        if key in buckets:
            buckets[key].append(l)
    return [_summarize_month(y, m, buckets[(y, m)]) for y, m in months]


# ─── HabitAnalyticsService ─────────────────────────────────────────────────

class HabitAnalyticsService:
    async def _get_logs(
        self, user_id: str, start_date: datetime, end_date: Optional[datetime] = None
    ) -> list[HabitLogMetrics]:
        uid = PydanticObjectId(user_id)
        end = end_date or datetime.now(timezone.utc)
        records = await HabitTracking.find(
            {"user_id": uid, "log_date": {"$gte": start_date, "$lte": end}},
            sort=[("log_date", 1)],
        ).to_list()
        return [
            HabitLogMetrics(
                log_date=r.log_date,
                sleep_hours=float(r.sleep_hours),
                exercise_minutes=int(r.exercise_minutes),
                water_intake_liters=float(r.water_intake_liters),
                screen_time_hours=float(r.screen_time_hours),
            )
            for r in records
        ]

    async def get_consistency_score(
        self, user_id: str, window_days: int = DEFAULT_WINDOW_DAYS
    ) -> ConsistencyScoreResponse:
        now = datetime.now(timezone.utc)
        logs = await self._get_logs(user_id, now - timedelta(days=window_days), now)
        percentage, logged_days = _consistency_score(logs, window_days, now)
        return ConsistencyScoreResponse(
            user_id=user_id, consistency_score=percentage, logged_days=logged_days, window_days=window_days
        )

    async def get_habit_streak(
        self, user_id: str, lookback_days: int = DEFAULT_STREAK_LOOKBACK_DAYS
    ) -> HabitStreakResponse:
        now = datetime.now(timezone.utc)
        logs = await self._get_logs(user_id, now - timedelta(days=lookback_days), now)
        current, longest, active = _compute_streak(logs, now)
        return HabitStreakResponse(
            user_id=user_id, current_streak=current, longest_streak=longest, streak_active=active
        )

    async def get_positive_habits(
        self, user_id: str, window_days: int = DEFAULT_WINDOW_DAYS
    ) -> PositiveHabitsResponse:
        now = datetime.now(timezone.utc)
        logs = await self._get_logs(user_id, now - timedelta(days=window_days), now)
        positive, _ = _classify_habits(logs)
        return PositiveHabitsResponse(user_id=user_id, habits=positive, window_days=window_days)

    async def get_negative_habits(
        self, user_id: str, window_days: int = DEFAULT_WINDOW_DAYS
    ) -> NegativeHabitsResponse:
        now = datetime.now(timezone.utc)
        logs = await self._get_logs(user_id, now - timedelta(days=window_days), now)
        _, negative = _classify_habits(logs)
        return NegativeHabitsResponse(user_id=user_id, habits=negative, window_days=window_days)

    async def get_missed_habits(
        self, user_id: str, window_days: int = DEFAULT_WINDOW_DAYS
    ) -> MissedHabitsResponse:
        now = datetime.now(timezone.utc)
        logs = await self._get_logs(user_id, now - timedelta(days=window_days), now)
        missed_dates = _missed_days(logs, window_days, now)
        return MissedHabitsResponse(
            user_id=user_id, missed_days=len(missed_dates), window_days=window_days, missed_dates=missed_dates
        )

    async def get_habit_trend(
        self,
        user_id: str,
        daily_days: int = DEFAULT_DAILY_TREND_DAYS,
        weeks_back: int = DEFAULT_WEEKS_BACK,
        months_back: int = DEFAULT_MONTHS_BACK,
    ) -> HabitTrendResponse:
        now = datetime.now(timezone.utc)
        lookback_days = max(daily_days, weeks_back * 7, months_back * 31)
        logs = await self._get_logs(user_id, now - timedelta(days=lookback_days), now)
        return HabitTrendResponse(
            user_id=user_id,
            daily=_build_daily_trend(logs, daily_days, now),
            weekly=_build_weekly_trend(logs, weeks_back, now),
            monthly=_build_monthly_trend(logs, months_back, now),
        )

    async def get_summary(self, user_id: str) -> HabitAnalyticsSummaryResponse:
        consistency, streak, positive, negative, missed, trend = await asyncio.gather(
            self.get_consistency_score(user_id),
            self.get_habit_streak(user_id),
            self.get_positive_habits(user_id),
            self.get_negative_habits(user_id),
            self.get_missed_habits(user_id),
            self.get_habit_trend(user_id),
        )
        return HabitAnalyticsSummaryResponse(
            user_id=user_id,
            consistency_score=consistency,
            habit_streak=streak,
            positive_habits=positive,
            negative_habits=negative,
            missed_habits=missed,
            habit_trend=trend,
            generated_at=datetime.now(timezone.utc),
        )


habit_analytics_service = HabitAnalyticsService()
