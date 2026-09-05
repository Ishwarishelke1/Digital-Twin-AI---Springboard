"""
tests/test_goal_progress_service.py — Covers the shared goal-progress helper.

Worth testing specifically because this is a money-adjacent path with a known
failure mode: raw Motor writes need explicit Decimal128 conversion (Beanie's ODM
layer does it automatically, `collection.update_one` does not). CLAUDE.md records
that forgetting it is a real, previously-hit bug — so the Decimal128 assertion
below is the point of this file, not incidental detail.

Follows the zero-DB pattern in conftest.py: get_motor_collection is mocked, so no
connection is ever attempted.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId
from bson.decimal128 import Decimal128

from services.goal_progress_service import adjust_active_goal_progress

USER_ID = "507f1f77bcf86cd799439011"
GOAL_ID = "goal-abc-123"


def _mock_collection(matched_count: int = 1):
    collection = MagicMock()
    collection.update_one = AsyncMock(return_value=MagicMock(matched_count=matched_count))
    return collection


@pytest.mark.asyncio
async def test_zero_delta_is_a_noop():
    """A no-op must not issue a write at all — not a $inc of 0."""
    collection = _mock_collection()
    with patch("services.goal_progress_service.User.get_motor_collection", return_value=collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("0"))
    collection.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_positive_delta_increments_with_decimal128():
    """The $inc value must be a Decimal128, not a raw Decimal/float — a raw
    Motor write does no BSON coercion, so a plain Decimal raises at encode time
    and a float silently loses precision on money."""
    collection = _mock_collection()
    with patch("services.goal_progress_service.User.get_motor_collection", return_value=collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("1250.75"))

    collection.update_one.assert_awaited_once()
    query, update = collection.update_one.await_args.args

    assert query["_id"] == PydanticObjectId(USER_ID)
    assert query["active_goals.goal_id"] == GOAL_ID

    inc_value = update["$inc"]["active_goals.$.current_value"]
    assert isinstance(inc_value, Decimal128), "raw Motor writes must convert to Decimal128"
    assert inc_value.to_decimal() == Decimal("1250.75")


@pytest.mark.asyncio
async def test_negative_delta_decrements():
    """Deleting a linked transaction reverses its contribution."""
    collection = _mock_collection()
    with patch("services.goal_progress_service.User.get_motor_collection", return_value=collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("-400.00"))

    _, update = collection.update_one.await_args.args
    assert update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-400.00")


@pytest.mark.asyncio
async def test_uses_positional_inc_not_read_modify_write():
    """Must target the matched array element via the positional `$` operator.
    A read-modify-write .save() of the whole document would clobber a concurrent
    edit to a *different* goal made by another in-flight request."""
    collection = _mock_collection()
    with patch("services.goal_progress_service.User.get_motor_collection", return_value=collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("10"))

    _, update = collection.update_one.await_args.args
    assert list(update.keys()) == ["$inc"]
    assert "active_goals.$.current_value" in update["$inc"]


@pytest.mark.asyncio
async def test_missing_goal_logs_warning_and_does_not_raise(caplog):
    """An unmatched goal_id must degrade quietly: the linked record's own write
    has already succeeded, so raising here would fail a request whose primary
    effect already landed."""
    collection = _mock_collection(matched_count=0)
    with patch("services.goal_progress_service.User.get_motor_collection", return_value=collection):
        with caplog.at_level("WARNING"):
            await adjust_active_goal_progress(USER_ID, "nonexistent-goal", Decimal("50"))

    assert "nonexistent-goal" in caplog.text
