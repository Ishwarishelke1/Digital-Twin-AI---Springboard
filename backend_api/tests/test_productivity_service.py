"""
tests/test_productivity_service.py — Unit tests for services/productivity_service.py.

Two layers:
1. Pure-function tests: exercise the math directly with plain StudySessionMetrics data,
   no mocking, no DB.
2. Service-level tests: patch StudyActivity.find (the only I/O call the service makes)
   to return canned records (as SimpleNamespace objects, since _get_sessions only reads
   plain attributes off them — no real Mongo/Beanie connection required).
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas.productivity_schema import AnalyticsMethod
from services.productivity_service import (
    ProductivityService,
    StudySessionMetrics,
    _aggregate_productivity_score,
    _average_focus_score,
    _completion_percentage,
    _group_by_month,
    _group_by_week,
    _linear_regression_forecast,
    _select_method,
    _session_productivity_score,
    _week_start,
)

VALID_USER_ID = "507f1f77bcf86cd799439011"
DEFAULT_WEEKS_BACK_FOR_TEST = 8  # matches services.productivity_service.DEFAULT_WEEKS_BACK


def _session(
    subject="Math",
    study_hours=2.0,
    focus_score=None,
    quiz_marks_pct=None,
    exam_marks_pct=None,
    session_date=None,
) -> StudySessionMetrics:
    return StudySessionMetrics(
        subject=subject,
        study_hours=study_hours,
        focus_score=focus_score,
        quiz_marks_pct=quiz_marks_pct,
        exam_marks_pct=exam_marks_pct,
        session_date=session_date or datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def _record(
    subject="Math",
    study_hours=2.0,
    focus_score=None,
    quiz_marks_pct=None,
    exam_marks_pct=None,
    session_date=None,
) -> SimpleNamespace:
    """A duck-typed stand-in for a StudyActivity Beanie document."""
    return SimpleNamespace(
        subject=subject,
        study_hours=Decimal(str(study_hours)),
        focus_score=focus_score,
        quiz_marks_pct=quiz_marks_pct,
        exam_marks_pct=exam_marks_pct,
        session_date=session_date or datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def _patch_find(records):
    """Patches StudyActivity.find(...).to_list() to resolve to `records`."""
    mock_query = MagicMock()
    mock_query.to_list = AsyncMock(return_value=records)
    return patch(
        "services.productivity_service.StudyActivity.find",
        new=MagicMock(return_value=mock_query),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pure-function tests
# ─────────────────────────────────────────────────────────────────────────────

def test_session_productivity_uses_only_available_components():
    # Hours alone: it is the only guaranteed component, so it carries the score
    # outright. A session at the 2h benchmark with nothing else recorded is 100 —
    # and one with no hours is 0, where attendance's old default used to floor it at 60.
    assert _session_productivity_score(_session(study_hours=2.0)) == 100.0
    assert _session_productivity_score(_session(study_hours=0.0)) == 0.0


def test_session_productivity_includes_focus_and_performance_when_present():
    full = _session(
        study_hours=2.0, focus_score=100.0,
        quiz_marks_pct=100.0, exam_marks_pct=100.0,
    )
    assert _session_productivity_score(full) == 100.0

    mixed = _session(
        study_hours=1.0, focus_score=50.0,
        quiz_marks_pct=50.0, exam_marks_pct=50.0,
    )
    assert _session_productivity_score(mixed) == 50.0


def test_session_productivity_caps_long_sessions_at_full_hours_component():
    # 10-hour session shouldn't blow past the 100 cap on the "hours" component.
    long_session = _session(study_hours=10.0)
    assert _session_productivity_score(long_session) == 100.0


def test_aggregate_productivity_score_empty_is_zero():
    assert _aggregate_productivity_score([]) == 0.0


def test_aggregate_productivity_score_averages_sessions():
    sessions = [
        _session(study_hours=2.0),  # 100
        _session(study_hours=0.0),  # 0
    ]
    assert _aggregate_productivity_score(sessions) == 50.0


def test_average_focus_score_uses_recorded_values_when_present():
    sessions = [_session(focus_score=80.0), _session(focus_score=60.0)]
    score, method = _average_focus_score(sessions)
    assert score == 70.0
    assert method == AnalyticsMethod.RECORDED_AVERAGE


def test_average_focus_score_reports_insufficient_data_when_none_recorded():
    """There is no proxy for focus. Attendance used to stand in here and reported a
    confident score for users who had never rated a session — sessions with no focus
    rating must say so instead."""
    sessions = [_session(focus_score=None), _session(focus_score=None)]
    score, method = _average_focus_score(sessions)
    assert score == 0.0
    assert method == AnalyticsMethod.INSUFFICIENT_DATA


def test_average_focus_score_insufficient_data_when_no_sessions():
    score, method = _average_focus_score([])
    assert score == 0.0
    assert method == AnalyticsMethod.INSUFFICIENT_DATA


def test_completion_percentage_counts_distinct_active_days():
    reference = datetime(2026, 8, 10, tzinfo=timezone.utc)
    sessions = [
        _session(session_date=datetime(2026, 8, 8, tzinfo=timezone.utc)),
        _session(session_date=datetime(2026, 8, 8, 12, tzinfo=timezone.utc)),  # same day, 2nd session
        _session(session_date=datetime(2026, 8, 9, tzinfo=timezone.utc)),
    ]
    percentage, active_days = _completion_percentage(sessions, window_days=10, reference_date=reference)
    assert active_days == 2
    assert percentage == 20.0


def test_completion_percentage_zero_when_no_sessions():
    percentage, active_days = _completion_percentage([], window_days=10, reference_date=datetime.now(timezone.utc))
    assert percentage == 0.0
    assert active_days == 0


def test_week_start_returns_monday():
    # 2026-08-05 is a Wednesday.
    assert _week_start(date(2026, 8, 5)) == date(2026, 8, 3)


def test_group_by_week_buckets_sessions_and_zero_fills_empty_weeks():
    reference = datetime(2026, 8, 12, tzinfo=timezone.utc)  # Wednesday
    sessions = [
        _session(study_hours=2.0, session_date=datetime(2026, 8, 4, tzinfo=timezone.utc)),  # week of Aug 3
        _session(study_hours=3.0, session_date=datetime(2026, 8, 5, tzinfo=timezone.utc)),  # same week
        # week of Aug 10 has no sessions at all
    ]
    trend = _group_by_week(sessions, weeks_back=2, reference_date=reference)
    assert [p.week_start for p in trend] == [date(2026, 8, 3), date(2026, 8, 10)]
    assert trend[0].session_count == 2
    assert trend[0].total_study_hours == 5.0
    assert trend[1].session_count == 0
    assert trend[1].total_study_hours == 0.0


def test_group_by_month_buckets_sessions_by_calendar_month():
    reference = datetime(2026, 8, 15, tzinfo=timezone.utc)
    sessions = [
        _session(study_hours=1.0, session_date=datetime(2026, 7, 10, tzinfo=timezone.utc)),
        _session(study_hours=2.0, session_date=datetime(2026, 8, 1, tzinfo=timezone.utc)),
        _session(study_hours=4.0, session_date=datetime(2026, 8, 10, tzinfo=timezone.utc)),
    ]
    trend = _group_by_month(sessions, months_back=3, reference_date=reference)
    assert [(p.year, p.month) for p in trend] == [(2026, 6), (2026, 7), (2026, 8)]
    assert trend[0].session_count == 0
    assert trend[1].total_study_hours == 1.0
    assert trend[2].total_study_hours == 6.0
    assert trend[2].session_count == 2


def test_select_method_boundaries():
    assert _select_method(0) == AnalyticsMethod.INSUFFICIENT_DATA
    assert _select_method(1) == AnalyticsMethod.NAIVE_LAST_VALUE
    assert _select_method(3) == AnalyticsMethod.MOVING_AVERAGE
    assert _select_method(4) == AnalyticsMethod.LINEAR_REGRESSION


def test_linear_regression_perfect_upward_trend():
    forecast, r_squared = _linear_regression_forecast([10.0, 20.0, 30.0, 40.0], periods_ahead=1)
    assert forecast[0] == pytest.approx(50.0, abs=1e-6)
    assert r_squared == pytest.approx(1.0, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Service-level tests (StudyActivity.find mocked)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_productivity_score_with_no_sessions():
    service = ProductivityService()
    with _patch_find([]):
        result = await service.get_productivity_score(VALID_USER_ID, lookback_days=30)
    assert result.productivity_score == 0.0
    assert result.data_points_used == 0


@pytest.mark.asyncio
async def test_get_productivity_score_averages_sessions():
    records = [
        _record(study_hours=2.0),
        _record(study_hours=1.0),
    ]
    service = ProductivityService()
    with _patch_find(records):
        result = await service.get_productivity_score(VALID_USER_ID, lookback_days=30)
    assert result.data_points_used == 2
    assert 0.0 < result.productivity_score <= 100.0


@pytest.mark.asyncio
async def test_get_focus_score_reports_insufficient_data_when_none_recorded():
    records = [_record(study_hours=2.0, focus_score=None)]
    service = ProductivityService()
    with _patch_find(records):
        result = await service.get_focus_score(VALID_USER_ID)
    assert result.method_used == AnalyticsMethod.INSUFFICIENT_DATA
    assert result.focus_score == 0.0


@pytest.mark.asyncio
async def test_get_focus_score_uses_recorded_values():
    records = [_record(focus_score=90.0), _record(focus_score=70.0)]
    service = ProductivityService()
    with _patch_find(records):
        result = await service.get_focus_score(VALID_USER_ID)
    assert result.method_used == AnalyticsMethod.RECORDED_AVERAGE
    assert result.focus_score == 80.0


@pytest.mark.asyncio
async def test_get_weekly_trend_returns_requested_number_of_weeks():
    service = ProductivityService()
    with _patch_find([]):
        result = await service.get_weekly_trend(VALID_USER_ID, weeks_back=4)
    assert len(result.trend) == 4
    assert all(p.session_count == 0 for p in result.trend)


@pytest.mark.asyncio
async def test_get_monthly_trend_returns_requested_number_of_months():
    service = ProductivityService()
    with _patch_find([]):
        result = await service.get_monthly_trend(VALID_USER_ID, months_back=3)
    assert len(result.trend) == 3


@pytest.mark.asyncio
async def test_get_completion_percentage_computes_active_days():
    now = datetime.now(timezone.utc)
    records = [
        _record(session_date=now - timedelta(days=1)),
        _record(session_date=now - timedelta(days=2)),
    ]
    service = ProductivityService()
    with _patch_find(records):
        result = await service.get_completion_percentage(VALID_USER_ID, window_days=10)
    assert result.active_days == 2
    assert result.completion_percentage == 20.0


@pytest.mark.asyncio
async def test_predict_performance_insufficient_data_when_no_sessions():
    service = ProductivityService()
    with _patch_find([]):
        result = await service.predict_performance(VALID_USER_ID, weeks_ahead=2)
    assert result.productivity_method_used == AnalyticsMethod.INSUFFICIENT_DATA
    assert result.productivity_confidence_score == 0.0
    assert len(result.predicted_productivity) == 2
    assert result.predicted_exam_score is None
    assert result.exam_method_used is None


@pytest.mark.asyncio
async def test_predict_performance_linear_regression_with_upward_trend():
    now = datetime.now(timezone.utc)
    # 4 distinct weeks, strictly increasing productivity via increasing study_hours.
    records = [
        _record(study_hours=1.0, session_date=now - timedelta(weeks=3)),
        _record(study_hours=1.3, session_date=now - timedelta(weeks=2)),
        _record(study_hours=1.6, session_date=now - timedelta(weeks=1)),
        _record(study_hours=2.0, session_date=now),
    ]
    service = ProductivityService()
    with _patch_find(records):
        result = await service.predict_performance(VALID_USER_ID, weeks_ahead=1)
    assert result.productivity_method_used == AnalyticsMethod.LINEAR_REGRESSION
    assert result.data_points_used == 4


@pytest.mark.asyncio
async def test_predict_performance_includes_exam_prediction_when_exam_data_exists():
    now = datetime.now(timezone.utc)
    records = [
        _record(exam_marks_pct=Decimal("60"), session_date=now - timedelta(weeks=3)),
        _record(exam_marks_pct=Decimal("70"), session_date=now - timedelta(weeks=2)),
        _record(exam_marks_pct=Decimal("80"), session_date=now - timedelta(weeks=1)),
        _record(exam_marks_pct=Decimal("90"), session_date=now),
    ]
    service = ProductivityService()
    with _patch_find(records):
        result = await service.predict_performance(VALID_USER_ID, weeks_ahead=1)
    assert result.exam_method_used == AnalyticsMethod.LINEAR_REGRESSION
    assert result.predicted_exam_score is not None
    assert float(result.predicted_exam_score) == pytest.approx(100.0, abs=1.0)
    assert result.exam_confidence_score > 0.8


@pytest.mark.asyncio
async def test_get_summary_bundles_all_six_outputs():
    records = [_record(study_hours=2.0, focus_score=75.0)]
    service = ProductivityService()
    with _patch_find(records):
        summary = await service.get_summary(VALID_USER_ID)
    assert summary.user_id == VALID_USER_ID
    assert summary.productivity_score.data_points_used == 1
    assert summary.focus_score.method_used == AnalyticsMethod.RECORDED_AVERAGE
    assert isinstance(summary.weekly_trend.trend, list) and len(summary.weekly_trend.trend) == DEFAULT_WEEKS_BACK_FOR_TEST
    assert isinstance(summary.monthly_trend.trend, list)
    assert summary.completion_percentage.active_days >= 0
    assert summary.performance_prediction is not None
