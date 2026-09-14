"""
tests/test_goal_completion_service.py — Covers the prediction serving path.

The contribution-source test guards a real defect: _contribution_stats counted
only FinancialRecord, so an actively-worked STUDY or HABIT goal reported
contribution_count = 0 — which the model reads as manually-tracked or abandoned.
Finance goals were unaffected, so it stayed invisible until a study goal was
tested end to end.

Zero DB: the three collection queries are mocked individually, per conftest.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from beanie import PydanticObjectId

import services.goal_completion_service as gcs
from models.enums import TransactionType

USER_ID = PydanticObjectId()
GOAL_ID = "goal-1"
NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


class _Rec:
    """Stands in for a record from any of the three collections."""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _find_returning(*batches):
    """Patches the three model .find() calls in call order: finance, study, habit."""
    calls = [AsyncMock(return_value=list(b)) for b in batches]
    def make(batch_mock):
        m = AsyncMock()
        m.to_list = batch_mock
        return lambda *a, **k: m
    return calls, make


@pytest.mark.asyncio
async def test_counts_finance_study_and_habit_contributions():
    """All three sources call adjust_active_goal_progress, so all three must count."""
    finance = [_Rec(type=TransactionType.SAVINGS_DEPOSIT, transaction_date=NOW - timedelta(days=9))]
    study = [_Rec(session_date=NOW - timedelta(days=4)), _Rec(session_date=NOW - timedelta(days=2))]
    habit = [_Rec(log_date=NOW - timedelta(days=1))]

    calls, make = _find_returning(finance, study, habit)
    with patch.object(gcs.FinancialRecord, "find", make(calls[0])), \
         patch.object(gcs.StudyActivity, "find", make(calls[1])), \
         patch.object(gcs.HabitTracking, "find", make(calls[2])):
        n, days_since = await gcs._contribution_stats(USER_ID, GOAL_ID, NOW)

    assert n == 4, "finance + study + habit contributions must all be counted"
    assert days_since == 1, "recency must come from the most recent of any source"


@pytest.mark.asyncio
async def test_expenses_linked_to_a_goal_are_not_progress():
    """Only SAVINGS_DEPOSIT and INVESTMENT move a goal forward — an expense
    linked to a goal is spending, not progress toward it."""
    finance = [
        _Rec(type=TransactionType.EXPENSE, transaction_date=NOW),
        _Rec(type=TransactionType.INCOME, transaction_date=NOW),
        _Rec(type=TransactionType.INVESTMENT, transaction_date=NOW - timedelta(days=3)),
    ]
    calls, make = _find_returning(finance, [], [])
    with patch.object(gcs.FinancialRecord, "find", make(calls[0])), \
         patch.object(gcs.StudyActivity, "find", make(calls[1])), \
         patch.object(gcs.HabitTracking, "find", make(calls[2])):
        n, days_since = await gcs._contribution_stats(USER_ID, GOAL_ID, NOW)

    assert n == 1
    assert days_since == 3


@pytest.mark.asyncio
async def test_no_contributions_reports_none_not_zero_days():
    """None is distinct from 0: 'never contributed' is not 'contributed today'."""
    calls, make = _find_returning([], [], [])
    with patch.object(gcs.FinancialRecord, "find", make(calls[0])), \
         patch.object(gcs.StudyActivity, "find", make(calls[1])), \
         patch.object(gcs.HabitTracking, "find", make(calls[2])):
        n, days_since = await gcs._contribution_stats(USER_ID, GOAL_ID, NOW)

    assert n == 0
    assert days_since is None


@pytest.mark.asyncio
async def test_naive_datetimes_do_not_raise():
    """Mongo can hand back naive datetimes; comparing them against an aware `now`
    raises TypeError if not normalised."""
    finance = [_Rec(type=TransactionType.SAVINGS_DEPOSIT,
                    transaction_date=datetime(2026, 9, 1))]  # no tzinfo
    calls, make = _find_returning(finance, [], [])
    with patch.object(gcs.FinancialRecord, "find", make(calls[0])), \
         patch.object(gcs.StudyActivity, "find", make(calls[1])), \
         patch.object(gcs.HabitTracking, "find", make(calls[2])):
        n, days_since = await gcs._contribution_stats(USER_ID, GOAL_ID, NOW)

    assert n == 1
    assert days_since == 7
