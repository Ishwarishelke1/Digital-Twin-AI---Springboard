"""
tests/test_habit_analytics_service.py — Unit tests for services/habit_analytics_service.py.

Two layers:
1. Pure-function tests: exercise the math directly with plain HabitLogMetrics data,
   no mocking, no DB.
2. Service-level tests: patch HabitTracking.find (the only I/O call the service makes)
   to return canned records (as SimpleNamespace objects — _get_logs only reads plain
   attributes off them, so no real Mongo/Beanie connection is required).
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas.habit_analytics_schema import HabitStatus
from services.habit_analytics_service import (
    HabitAnalyticsService,
    HabitLogMetrics,
    _classify_habits,
    _compute_streak,
    _consistency_score,
    _daily_habit_score,
    _missed_days,
    _build_daily_trend,
    _build_weekly_trend,
    _build_monthly_trend,
    _week_start,
)

VALID_USER_ID = "507f1f77bcf86cd799439011"


def _log(
    sleep_hours=8.0,
    exercise_minutes=30,
    water_intake_liters=2.0,
    screen_time_hours=4.0,
    log_date=None,
) -> HabitLogMetrics:
    return HabitLogMetrics(
        log_date=log_date or datetime(2026, 8, 1, tzinfo=timezone.utc),
        sleep_hours=sleep_hours,
        exercise_minutes=exercise_minutes,
        water_intake_liters=water_intake_liters,
        screen_time_hours=screen_time_hours,
    )


def _record(
    sleep_hours=8.0,
    exercise_minutes=30,
    water_intake_liters=2.0,
    screen_time_hours=4.0,
    log_date=None,
) -> SimpleNamespace:
    """A duck-typed stand-in for a HabitTracking Beanie document."""
    return SimpleNamespace(
        log_date=log_date or datetime(2026, 8, 1, tzinfo=timezone.utc),
        sleep_hours=Decimal(str(sleep_hours)),
        exercise_minutes=exercise_minutes,
        water_intake_liters=Decimal(str(water_intake_liters)),
        screen_time_hours=Decimal(str(screen_time_hours)),
    )


def _patch_find(records):
    mock_query = MagicMock()
    mock_query.to_list = AsyncMock(return_value=records)
    return patch(
        "services.habit_analytics_service.HabitTracking.find",
        new=MagicMock(return_value=mock_query),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pure-function tests
# ─────────────────────────────────────────────────────────────────────────────

def test_daily_habit_score_perfect_day_is_100():
    perfect = _log(sleep_hours=8.0, exercise_minutes=30, water_intake_liters=2.0, screen_time_hours=4.0)
    assert _daily_habit_score(perfect) == 100.0


def test_daily_habit_score_poor_day_is_low():
    poor = _log(sleep_hours=3.0, exercise_minutes=0, water_intake_liters=0.0, screen_time_hours=12.0)
    assert _daily_habit_score(poor) < 50.0


def test_consistency_score_counts_distinct_logged_days():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [
        _log(log_date=datetime(2026, 8, 8, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 9, tzinfo=timezone.utc)),
    ]
    percentage, logged_days = _consistency_score(logs, window_days=10, reference_date=reference)
    assert logged_days == 2
    assert percentage == 20.0


def test_consistency_score_zero_with_no_logs():
    percentage, logged_days = _consistency_score([], window_days=10, reference_date=datetime.now(timezone.utc))
    assert percentage == 0.0
    assert logged_days == 0


def test_consistency_score_window_matches_missed_days_window():
    """logged_days + missed_days must sum to window_days — both helpers must
    agree on the same set of calendar dates for a given window_days/reference."""
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [
        _log(log_date=datetime(2026, 8, 8, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 10, tzinfo=timezone.utc)),
    ]
    _, logged_days = _consistency_score(logs, window_days=3, reference_date=reference)
    missed = _missed_days(logs, window_days=3, reference_date=reference)
    assert logged_days + len(missed) == 3


def test_consistency_score_excludes_day_just_outside_window():
    """A log exactly window_days before the reference date (the boundary
    _missed_days does NOT count) must not be counted as logged either."""
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [_log(log_date=datetime(2026, 7, 31, tzinfo=timezone.utc))]  # 10 days before
    percentage, logged_days = _consistency_score(logs, window_days=10, reference_date=reference)
    assert logged_days == 0
    assert percentage == 0.0


def test_compute_streak_counts_consecutive_days_ending_today():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [
        _log(log_date=datetime(2026, 8, 8, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 9, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 10, tzinfo=timezone.utc)),
    ]
    current, longest, active = _compute_streak(logs, reference)
    assert current == 3
    assert longest == 3
    assert active is True


def test_compute_streak_still_active_when_only_yesterday_logged():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [_log(log_date=datetime(2026, 8, 9, tzinfo=timezone.utc))]
    current, longest, active = _compute_streak(logs, reference)
    assert current == 1
    assert active is True


def test_compute_streak_broken_when_gap_before_yesterday():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [_log(log_date=datetime(2026, 8, 5, tzinfo=timezone.utc))]  # 5 days ago, not yesterday
    current, longest, active = _compute_streak(logs, reference)
    assert current == 0
    assert longest == 1
    assert active is False


def test_compute_streak_finds_longest_historical_run():
    reference = datetime(2026, 8, 20, tzinfo=timezone.utc)
    # 3-day run early in the window, then a gap, then nothing near "today".
    logs = [
        _log(log_date=datetime(2026, 8, 1, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 2, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 3, tzinfo=timezone.utc)),
    ]
    current, longest, active = _compute_streak(logs, reference)
    assert longest == 3
    assert current == 0
    assert active is False


def test_compute_streak_empty_logs():
    current, longest, active = _compute_streak([], datetime.now(timezone.utc))
    assert (current, longest, active) == (0, 0, False)


def test_classify_habits_splits_positive_and_negative():
    logs = [
        _log(sleep_hours=8.0, exercise_minutes=45, water_intake_liters=2.5, screen_time_hours=10.0),
        _log(sleep_hours=8.0, exercise_minutes=45, water_intake_liters=2.5, screen_time_hours=10.0),
    ]
    positive, negative = _classify_habits(logs)
    positive_names = {h.habit for h in positive}
    negative_names = {h.habit for h in negative}
    assert {"sleep", "exercise", "water"} <= positive_names
    assert "screen_time" in negative_names


def test_classify_habits_empty_when_no_logs():
    positive, negative = _classify_habits([])
    assert positive == []
    assert negative == []


def test_missed_days_returns_unlogged_dates_in_window():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [_log(log_date=datetime(2026, 8, 10, tzinfo=timezone.utc))]
    missed = _missed_days(logs, window_days=3, reference_date=reference)
    assert missed == [date(2026, 8, 8), date(2026, 8, 9)]


def test_missed_days_empty_when_fully_logged():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [
        _log(log_date=datetime(2026, 8, 8, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 9, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 10, tzinfo=timezone.utc)),
    ]
    missed = _missed_days(logs, window_days=3, reference_date=reference)
    assert missed == []


def test_week_start_returns_monday():
    assert _week_start(date(2026, 8, 5)) == date(2026, 8, 3)  # Wednesday -> Monday


def test_build_daily_trend_flags_unlogged_days():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    logs = [_log(log_date=datetime(2026, 8, 10, tzinfo=timezone.utc))]
    trend = _build_daily_trend(logs, days_back=2, reference_date=reference)
    assert [p.date for p in trend] == [date(2026, 8, 9), date(2026, 8, 10)]
    assert trend[0].logged is False
    assert trend[0].habit_score == 0.0
    assert trend[1].logged is True
    assert trend[1].habit_score == 100.0


def test_build_weekly_trend_zero_fills_empty_weeks():
    reference = datetime(2026, 8, 12, tzinfo=timezone.utc)  # Wednesday
    logs = [_log(log_date=datetime(2026, 8, 4, tzinfo=timezone.utc))]  # week of Aug 3
    trend = _build_weekly_trend(logs, weeks_back=2, reference_date=reference)
    assert [p.week_start for p in trend] == [date(2026, 8, 3), date(2026, 8, 10)]
    assert trend[0].days_logged == 1
    assert trend[1].days_logged == 0


def test_build_monthly_trend_buckets_by_calendar_month():
    reference = datetime(2026, 8, 15, tzinfo=timezone.utc)
    logs = [
        _log(log_date=datetime(2026, 7, 10, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 1, tzinfo=timezone.utc)),
        _log(log_date=datetime(2026, 8, 10, tzinfo=timezone.utc)),
    ]
    trend = _build_monthly_trend(logs, months_back=3, reference_date=reference)
    assert [(p.year, p.month) for p in trend] == [(2026, 6), (2026, 7), (2026, 8)]
    assert trend[0].days_logged == 0
    assert trend[1].days_logged == 1
    assert trend[2].days_logged == 2


# ─────────────────────────────────────────────────────────────────────────────
# Service-level tests (HabitTracking.find mocked)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_consistency_score_with_no_logs():
    service = HabitAnalyticsService()
    with _patch_find([]):
        result = await service.get_consistency_score(VALID_USER_ID, window_days=30)
    assert result.consistency_score == 0.0
    assert result.logged_days == 0


@pytest.mark.asyncio
async def test_get_consistency_score_computes_percentage():
    now = datetime.now(timezone.utc)
    records = [_record(log_date=now - timedelta(days=i)) for i in range(5)]
    service = HabitAnalyticsService()
    with _patch_find(records):
        result = await service.get_consistency_score(VALID_USER_ID, window_days=10)
    assert result.logged_days == 5
    assert result.consistency_score == 50.0


@pytest.mark.asyncio
async def test_get_habit_streak_reflects_recent_consecutive_logs():
    now = datetime.now(timezone.utc)
    records = [_record(log_date=now - timedelta(days=i)) for i in range(3)]  # today, yesterday, day before
    service = HabitAnalyticsService()
    with _patch_find(records):
        result = await service.get_habit_streak(VALID_USER_ID)
    assert result.current_streak == 3
    assert result.streak_active is True


@pytest.mark.asyncio
async def test_get_positive_habits_returns_only_positive():
    records = [
        _record(sleep_hours=8.0, exercise_minutes=45, water_intake_liters=2.5, screen_time_hours=3.0),
    ]
    service = HabitAnalyticsService()
    with _patch_find(records):
        result = await service.get_positive_habits(VALID_USER_ID)
    assert all(h.status == HabitStatus.POSITIVE for h in result.habits)
    assert len(result.habits) == 4  # all 4 metrics healthy


@pytest.mark.asyncio
async def test_get_negative_habits_returns_only_negative():
    records = [
        _record(sleep_hours=3.0, exercise_minutes=0, water_intake_liters=0.2, screen_time_hours=12.0),
    ]
    service = HabitAnalyticsService()
    with _patch_find(records):
        result = await service.get_negative_habits(VALID_USER_ID)
    assert all(h.status == HabitStatus.NEGATIVE for h in result.habits)
    assert len(result.habits) == 4


@pytest.mark.asyncio
async def test_get_missed_habits_lists_unlogged_dates():
    now = datetime.now(timezone.utc)
    records = [_record(log_date=now)]
    service = HabitAnalyticsService()
    with _patch_find(records):
        result = await service.get_missed_habits(VALID_USER_ID, window_days=3)
    assert result.missed_days == 2
    assert len(result.missed_dates) == 2


@pytest.mark.asyncio
async def test_get_habit_trend_returns_all_three_granularities():
    service = HabitAnalyticsService()
    with _patch_find([]):
        result = await service.get_habit_trend(
            VALID_USER_ID, daily_days=5, weeks_back=2, months_back=2
        )
    assert len(result.daily) == 5
    assert len(result.weekly) == 2
    assert len(result.monthly) == 2
    assert all(p.logged is False for p in result.daily)


@pytest.mark.asyncio
async def test_get_summary_bundles_all_six_outputs_as_structured_response():
    now = datetime.now(timezone.utc)
    records = [_record(log_date=now)]
    service = HabitAnalyticsService()
    with _patch_find(records):
        summary = await service.get_summary(VALID_USER_ID)

    assert summary.user_id == VALID_USER_ID
    assert summary.consistency_score.logged_days == 1
    assert summary.habit_streak.current_streak == 1
    assert isinstance(summary.positive_habits.habits, list)
    assert isinstance(summary.negative_habits.habits, list)
    assert isinstance(summary.missed_habits.missed_dates, list)
    assert summary.habit_trend.daily and summary.habit_trend.weekly and summary.habit_trend.monthly

    # "Return structured JSON" — the whole nested response must serialize cleanly.
    payload = summary.model_dump_json()
    assert isinstance(payload, str)
    assert '"user_id"' in payload
    assert '"habit_trend"' in payload
