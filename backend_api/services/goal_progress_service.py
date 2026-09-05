"""
services/goal_progress_service.py — Shared helper for atomically adjusting an
ActiveGoal's current_value when a finance/study/habit record links to it, and for
deriving the goal's status from that value.

A leaf module (only depends on models.user) so finance_service/study_service/
habit_service can all import it without circularity — user_service.py already
imports finance_service, so finance_service importing user_service back would
create a cycle.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from beanie import PydanticObjectId
from bson.decimal128 import Decimal128

from models.enums import GoalStatus
from models.user import User

logger = logging.getLogger("digital_twin_ai.goal_progress_service")


def _as_decimal(value) -> Decimal:
    """Raw Motor reads hand back Decimal128 for DecimalAnnotation fields; Beanie's
    ODM layer would decode them, a raw collection read does not."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


def derive_status(current_value, target_value) -> GoalStatus:
    """Single source of truth for status derivation.

    Previously this logic lived only in user_service.update_active_goal, which is
    the *manual edit* path — so a goal that reached its target through the normal
    mechanism (a linked savings deposit, study session or habit log, all of which
    route through adjust_active_goal_progress below) never flipped to COMPLETED.
    It stayed ACTIVE indefinitely with current_value >= target_value, and the
    Goals page's Active/Completed split showed it as still in progress.
    """
    return (
        GoalStatus.COMPLETED
        if _as_decimal(current_value) >= _as_decimal(target_value)
        else GoalStatus.ACTIVE
    )


def completion_fields(
    new_status: GoalStatus, previous_status: GoalStatus, existing_completed_at: Optional[datetime]
) -> dict:
    """Fields to write alongside a status change.

    `completed_at` is stamped once on the first ACTIVE → COMPLETED transition and
    never cleared afterwards — see the field's comment in models/user.py for why
    status is reversible but this is not.
    """
    fields: dict = {"status": new_status.value}
    if (
        new_status is GoalStatus.COMPLETED
        and previous_status is not GoalStatus.COMPLETED
        and existing_completed_at is None
    ):
        fields["completed_at"] = datetime.now(timezone.utc)
    return fields


async def adjust_active_goal_progress(user_id: str, goal_id: str, delta: Decimal) -> None:
    """Atomically increments (or, for a negative delta, decrements) one active
    goal's current_value via $inc — never a read-modify-write whole-document
    .save(), which could silently drop a concurrent edit to a *different* goal
    made by another in-flight request (same pattern/rationale as
    user_service.update_active_goal's positional-$ atomic update).

    Then re-derives status from the resulting value, writing it only when it
    actually changed (the common case is no change, so this second write is rare).
    """
    if delta == 0:
        return

    collection = User.get_motor_collection()

    # find_one_and_update returns the post-increment document, so the new
    # current_value is known without a second read racing against another writer.
    doc = await collection.find_one_and_update(
        {"_id": PydanticObjectId(user_id), "active_goals.goal_id": goal_id},
        {"$inc": {"active_goals.$.current_value": Decimal128(str(delta))}},
        projection={"active_goals": 1},
        return_document=True,  # pymongo.ReturnDocument.AFTER
    )

    if doc is None:
        logger.warning(
            "Linked goal %s not found for user %s; skipping goal progress update.", goal_id, user_id
        )
        return

    goal = next((g for g in doc.get("active_goals", []) if g.get("goal_id") == goal_id), None)
    if goal is None:
        return

    previous_status = GoalStatus(goal.get("status", GoalStatus.ACTIVE.value))
    new_status = derive_status(goal.get("current_value", 0), goal.get("target_value", 0))
    if new_status is previous_status:
        return

    fields = completion_fields(new_status, previous_status, goal.get("completed_at"))
    await collection.update_one(
        {"_id": PydanticObjectId(user_id), "active_goals.goal_id": goal_id},
        {"$set": {f"active_goals.$.{k}": v for k, v in fields.items()}},
    )
    logger.info(
        "Goal %s for user %s transitioned %s → %s.",
        goal_id, user_id, previous_status.value, new_status.value,
    )
