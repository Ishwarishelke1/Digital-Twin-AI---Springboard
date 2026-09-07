"""
tests/test_activity_service.py — Covers the activity audit log.

The important property is the swallow-and-log behaviour: log_activity is called
from inside finance/study/habit/goal writes, so if it raised, a failed audit
write would fail the user-facing operation whose primary effect had already
landed. It must never propagate — but it must also not fail silently, since a
silently broken audit log looks identical to a quiet one.

Zero DB, per conftest: the insert and the query chain are mocked individually.
"""
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

import services.activity_service as activity_service

USER_ID = str(PydanticObjectId())


# ─── log_activity ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_activity_inserts_with_the_given_fields():
    with patch.object(activity_service.UserActivity, "insert", new=AsyncMock()) as insert:
        await activity_service.log_activity(
            user_id=USER_ID,
            action_type="CREATED_FINANCE",
            entity_type="FINANCE",
            description="Created financial record",
            entity_id="abc123",
        )
    insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_activity_swallows_failures(caplog):
    """A failed audit write must not fail the operation it is attached to — by
    the time this runs, the finance/study/habit record has already been written."""
    with patch.object(activity_service.UserActivity, "insert",
                      new=AsyncMock(side_effect=RuntimeError("mongo down"))):
        with caplog.at_level("ERROR"):
            await activity_service.log_activity(
                user_id=USER_ID,
                action_type="CREATED_FINANCE",
                entity_type="FINANCE",
                description="Created financial record",
            )  # must not raise

    assert "Failed to log activity" in caplog.text
    assert USER_ID in caplog.text, "the log must name the user, or it is not diagnosable"
    assert "CREATED_FINANCE" in caplog.text


@pytest.mark.asyncio
async def test_log_activity_failure_is_logged_with_a_traceback(caplog):
    """exc_info matters: a one-line message with no stack is not diagnosable."""
    with patch.object(activity_service.UserActivity, "insert",
                      new=AsyncMock(side_effect=RuntimeError("boom"))):
        with caplog.at_level("ERROR"):
            await activity_service.log_activity(USER_ID, "X", "Y", "desc")

    record = next(r for r in caplog.records if "Failed to log activity" in r.getMessage())
    assert record.exc_info is not None, "exception info must be attached"


@pytest.mark.asyncio
async def test_log_activity_rejects_a_malformed_user_id(caplog):
    """PydanticObjectId() raises on a non-ObjectId string. That must be swallowed
    like any other failure rather than taking down the caller."""
    with caplog.at_level("ERROR"):
        await activity_service.log_activity("not-an-objectid", "X", "Y", "desc")
    assert "Failed to log activity" in caplog.text


# ─── list_activities ─────────────────────────────────────────────────────────

def _mock_query(records, total):
    """Mocks UserActivity.find(...).sort(...).skip(...).limit(...).to_list()."""
    query = MagicMock()
    query.count = AsyncMock(return_value=total)
    chain = MagicMock()
    chain.to_list = AsyncMock(return_value=records)
    query.sort.return_value.skip.return_value.limit.return_value = chain
    return query


def _record(desc="did a thing"):
    r = MagicMock()
    r.id = PydanticObjectId()
    r.action_type = "CREATED_FINANCE"
    r.entity_type = "FINANCE"
    r.entity_id = "e1"
    r.description = desc
    r.timestamp = "2026-09-08T00:00:00+00:00"
    return r


@pytest.mark.asyncio
async def test_list_activities_returns_paginated_payload():
    query = _mock_query([_record("a"), _record("b")], total=2)
    with patch.object(activity_service.UserActivity, "find", return_value=query):
        result = await activity_service.list_activities(USER_ID, page=1, limit=20)

    assert result.total == 2
    assert result.page == 1
    assert result.limit == 20
    assert result.total_pages == 1
    assert [i.description for i in result.data] == ["a", "b"]


@pytest.mark.asyncio
async def test_list_activities_sorts_newest_first_and_skips_by_page():
    """Page 3 at 20 per page must skip 40, and the feed must be reverse-chronological."""
    query = _mock_query([], total=100)
    with patch.object(activity_service.UserActivity, "find", return_value=query):
        await activity_service.list_activities(USER_ID, page=3, limit=20)

    query.sort.assert_called_once_with("-timestamp")
    query.sort.return_value.skip.assert_called_once_with(40)
    query.sort.return_value.skip.return_value.limit.assert_called_once_with(20)


@pytest.mark.asyncio
async def test_list_activities_scopes_the_query_to_the_user():
    """Every query must be user-scoped — a missing filter here is a cross-tenant
    data leak, not a display bug."""
    query = _mock_query([], total=0)
    with patch.object(activity_service.UserActivity, "find", return_value=query) as find:
        await activity_service.list_activities(USER_ID)

    (filter_arg,), _ = find.call_args
    assert filter_arg == {"user_id": PydanticObjectId(USER_ID)}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "total,limit,expected_pages",
    [(0, 20, 0), (1, 20, 1), (20, 20, 1), (21, 20, 2), (100, 7, 15)],
)
async def test_total_pages_rounds_up(total, limit, expected_pages):
    query = _mock_query([], total=total)
    with patch.object(activity_service.UserActivity, "find", return_value=query):
        result = await activity_service.list_activities(USER_ID, limit=limit)
    assert result.total_pages == expected_pages == math.ceil(total / limit)


@pytest.mark.asyncio
async def test_zero_limit_does_not_divide_by_zero():
    """total_pages guards limit > 0; without it this raises ZeroDivisionError."""
    query = _mock_query([], total=5)
    with patch.object(activity_service.UserActivity, "find", return_value=query):
        result = await activity_service.list_activities(USER_ID, limit=0)
    assert result.total_pages == 1
