"""
tests/test_goal_progress_service.py — Covers the shared goal-progress helper.

Worth testing specifically for two reasons:

1. This is a money-adjacent path with a known failure mode: raw Motor writes need
   explicit Decimal128 conversion (Beanie's ODM layer does it automatically,
   `collection.find_one_and_update` does not). CLAUDE.md records that forgetting
   it is a real, previously-hit bug.
2. Status derivation used to live only in user_service.update_active_goal — the
   *manual edit* path — so a goal that reached its target through the normal
   mechanism (a linked savings deposit, study session or habit log, all of which
   route through here) never flipped to COMPLETED. The transition tests below
   guard that regression.

Follows the zero-DB pattern in conftest.py: get_motor_collection is mocked, so no
connection is ever attempted.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId
from bson.decimal128 import Decimal128

from models.enums import GoalStatus
from services.goal_progress_service import (
    adjust_active_goal_progress,
    completion_fields,
    derive_status,
)

USER_ID = "507f1f77bcf86cd799439011"
GOAL_ID = "goal-abc-123"


def _mock_collection(current="1", target="100", status="ACTIVE", completed_at=None, found=True):
    """Mocks the two-step write: find_one_and_update returns the post-$inc goal,
    update_one applies a status change only when one is warranted."""
    collection = MagicMock()

    async def _echo(query, update, **kwargs):
        if not found:
            return None
        return {
            "active_goals": [
                {
                    "goal_id": query.get("active_goals.goal_id"),
                    "current_value": Decimal128(current),
                    "target_value": Decimal128(target),
                    "status": status,
                    "completed_at": completed_at,
                }
            ]
        }

    collection.find_one_and_update = AsyncMock(side_effect=_echo)
    collection.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return collection


def _patch(collection):
    return patch(
        "services.goal_progress_service.User.get_motor_collection", return_value=collection
    )


# ─── the $inc write ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zero_delta_is_a_noop():
    """A no-op must not issue a write at all — not a $inc of 0."""
    collection = _mock_collection()
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("0"))
    collection.find_one_and_update.assert_not_called()
    collection.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_positive_delta_increments_with_decimal128():
    """The $inc value must be a Decimal128, not a raw Decimal/float — a raw Motor
    write does no BSON coercion, so a plain Decimal raises at encode time and a
    float silently loses precision on money."""
    collection = _mock_collection()
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("1250.75"))

    query, update = collection.find_one_and_update.await_args.args
    assert query["_id"] == PydanticObjectId(USER_ID)
    assert query["active_goals.goal_id"] == GOAL_ID

    inc_value = update["$inc"]["active_goals.$.current_value"]
    assert isinstance(inc_value, Decimal128), "raw Motor writes must convert to Decimal128"
    assert inc_value.to_decimal() == Decimal("1250.75")


@pytest.mark.asyncio
async def test_negative_delta_decrements():
    """Deleting a linked transaction reverses its contribution."""
    collection = _mock_collection()
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("-400.00"))

    _, update = collection.find_one_and_update.await_args.args
    assert update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-400.00")


@pytest.mark.asyncio
async def test_uses_positional_inc_not_read_modify_write():
    """Must target the matched array element via the positional `$` operator. A
    read-modify-write .save() of the whole document would clobber a concurrent
    edit to a *different* goal made by another in-flight request."""
    collection = _mock_collection()
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("10"))

    _, update = collection.find_one_and_update.await_args.args
    assert list(update.keys()) == ["$inc"]
    assert "active_goals.$.current_value" in update["$inc"]


@pytest.mark.asyncio
async def test_missing_goal_logs_warning_and_does_not_raise(caplog):
    """An unmatched goal_id must degrade quietly: the linked record's own write
    has already succeeded, so raising here would fail a request whose primary
    effect already landed."""
    collection = _mock_collection(found=False)
    with _patch(collection):
        with caplog.at_level("WARNING"):
            await adjust_active_goal_progress(USER_ID, "nonexistent-goal", Decimal("50"))

    assert "nonexistent-goal" in caplog.text
    collection.update_one.assert_not_called()


# ─── status transition (the regression this path previously had) ─────────────────

@pytest.mark.asyncio
async def test_reaching_target_via_linked_record_marks_completed():
    """The bug this guards: progress applied through a linked transaction/session
    used to leave status ACTIVE forever, because only the manual-edit path in
    user_service re-derived it."""
    collection = _mock_collection(current="100", target="100", status="ACTIVE")
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("40"))

    collection.update_one.assert_awaited_once()
    _, update = collection.update_one.await_args.args
    assert update["$set"]["active_goals.$.status"] == GoalStatus.COMPLETED.value
    assert "active_goals.$.completed_at" in update["$set"]


@pytest.mark.asyncio
async def test_no_status_write_when_status_unchanged():
    """The common case — progress moves but doesn't cross the target — must not
    issue a second write."""
    collection = _mock_collection(current="40", target="100", status="ACTIVE")
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("10"))
    collection.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_dropping_below_target_reopens_without_clearing_completed_at():
    """Status is reversible; completed_at is not. The goal was met once, and a
    later reversal (e.g. deleting the linked transaction) is a separate fact —
    clearing the timestamp would destroy the training label."""
    collection = _mock_collection(
        current="50", target="100", status="COMPLETED", completed_at="2026-01-01T00:00:00Z"
    )
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("-60"))

    _, update = collection.update_one.await_args.args
    assert update["$set"]["active_goals.$.status"] == GoalStatus.ACTIVE.value
    assert "active_goals.$.completed_at" not in update["$set"]


@pytest.mark.asyncio
async def test_completed_at_not_overwritten_on_recompletion():
    """Re-crossing the target after a dip keeps the original completion date."""
    collection = _mock_collection(
        current="100", target="100", status="ACTIVE", completed_at="2026-01-01T00:00:00Z"
    )
    with _patch(collection):
        await adjust_active_goal_progress(USER_ID, GOAL_ID, Decimal("60"))

    _, update = collection.update_one.await_args.args
    assert update["$set"]["active_goals.$.status"] == GoalStatus.COMPLETED.value
    assert "active_goals.$.completed_at" not in update["$set"]


# ─── pure helpers ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "current,target,expected",
    [
        (Decimal("99"), Decimal("100"), GoalStatus.ACTIVE),
        (Decimal("100"), Decimal("100"), GoalStatus.COMPLETED),
        (Decimal("101"), Decimal("100"), GoalStatus.COMPLETED),
        (Decimal128("100"), Decimal128("100"), GoalStatus.COMPLETED),
    ],
)
def test_derive_status(current, target, expected):
    """Handles both Decimal and the Decimal128 a raw Motor read hands back."""
    assert derive_status(current, target) is expected


def test_completion_fields_stamps_once():
    first = completion_fields(GoalStatus.COMPLETED, GoalStatus.ACTIVE, None)
    assert "completed_at" in first

    already = completion_fields(GoalStatus.COMPLETED, GoalStatus.COMPLETED, "2026-01-01")
    assert "completed_at" not in already
