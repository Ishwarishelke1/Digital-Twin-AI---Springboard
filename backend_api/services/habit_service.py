"""
services/habit_service.py — Business logic layer for daily habit tracking.
Python equivalent of HabitTrackingRepository from habit_repository.ts.
The key design: `upsert_daily_log` replicates upsertDailyHabitLog() which relies on
the unique compound index (user_id, log_date) to enforce 1 entry per calendar day.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from beanie import PydanticObjectId
from bson import Decimal128
from pymongo.errors import DuplicateKeyError

from core.exceptions import ConflictError, NotFoundError
from models.habit import HabitTracking
from models.enums import BurnoutRisk, SleepBand
from schemas.habit_schema import (
    HabitCreateRequest,
    HabitRecordResponse,
    PaginatedHabitResponse,
    KMeansFeatureRow,
)
import services.activity_service as activity_service
from services.goal_progress_service import adjust_active_goal_progress
from services.habit_analytics_service import SLEEP_HEALTHY_RANGE

logger = logging.getLogger("digital_twin_ai.habit_service")

# Same reasoning as study_service.GOAL_PROGRESS_PER_LINK — a habit log has no
# numeric field that maps unambiguously onto an arbitrary goal's free-text
# unit, so linking counts as a flat +1 per day logged rather than guessing a
# unit-specific formula.
GOAL_PROGRESS_PER_LINK = Decimal("1")


def _midnight_utc(dt: Optional[datetime] = None) -> datetime:
    """Returns the given datetime (or now) normalized to 00:00:00.000 UTC."""
    base = dt or datetime.now(timezone.utc)
    return base.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=timezone.utc,
    )


def _to_response(record: HabitTracking) -> HabitRecordResponse:
    return HabitRecordResponse(
        id=str(record.id),
        user_id=str(record.user_id),
        sleep_hours=record.sleep_hours,
        exercise_minutes=record.exercise_minutes,
        water_intake_liters=record.water_intake_liters,
        screen_time_hours=record.screen_time_hours,
        mood_rating=record.mood_rating,
        meditation_minutes=record.meditation_minutes,
        productivity_score_computed=record.productivity_score_computed,
        lifestyle_score_computed=record.lifestyle_score_computed,
        burnout_risk_cluster=record.burnout_risk_cluster,
        linked_goal_id=record.linked_goal_id,
        log_date=record.log_date,
        created_at=record.created_at,
    )


async def upsert_daily_log(
    user_id: str, payload: HabitCreateRequest
) -> HabitRecordResponse:
    """
    Creates or updates today's habit check-in.
    Mirrors upsertDailyHabitLog() from habit_repository.ts using findOneAndUpdate + upsert=True.
    The unique compound index (user_id, log_date) in MongoDB is the final guard.
    log_date is always normalized to midnight UTC before persistence.
    """
    uid = PydanticObjectId(user_id)
    log_date = _midnight_utc(payload.log_date)

    from bson.decimal128 import Decimal128
    from pymongo import ReturnDocument

    update_fields = {
        "user_id": uid,
        "sleep_hours": Decimal128(payload.sleep_hours),
        "exercise_minutes": payload.exercise_minutes,
        "water_intake_liters": Decimal128(payload.water_intake_liters),
        "screen_time_hours": Decimal128(payload.screen_time_hours),
        "mood_rating": payload.mood_rating,
        "meditation_minutes": payload.meditation_minutes,
        "linked_goal_id": payload.linked_goal_id,
        "log_date": log_date,
    }

    collection = HabitTracking.get_motor_collection()

    # Captured before the upsert so a same-day re-log (upsert = update, not
    # create) can tell whether linked_goal_id actually changed — this is an
    # upsert, so "create" and "update" are the same code path here.
    existing = await collection.find_one({"user_id": uid, "log_date": log_date})
    old_linked_goal_id = existing.get("linked_goal_id") if existing else None

    try:
        result = await collection.find_one_and_update(
            {"user_id": uid, "log_date": log_date},
            {
                "$set": update_fields,
                "$setOnInsert": {
                    "created_at": datetime.now(timezone.utc),
                    "burnout_risk_cluster": BurnoutRisk.UNKNOWN,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        raise ConflictError(
            "A habit log already exists for this user on this date."
        )

    record = HabitTracking(**result)

    # Re-link (or unlink) moves the flat +1 contribution from the old goal to
    # the new one — never both, never neither.
    if record.linked_goal_id != old_linked_goal_id:
        if old_linked_goal_id:
            await adjust_active_goal_progress(user_id, old_linked_goal_id, -GOAL_PROGRESS_PER_LINK)
        if record.linked_goal_id:
            await adjust_active_goal_progress(user_id, record.linked_goal_id, GOAL_PROGRESS_PER_LINK)

    logger.info(
        "Habit log upserted for user %s on %s",
        user_id,
        log_date.date(),
    )

    await activity_service.log_activity(
        user_id=user_id,
        action_type="UPSERTED_HABIT",
        entity_type="HABIT",
        entity_id=str(record.id),
        description=f"Upserted habit log for {log_date.date()}",
    )

    return _to_response(record)


async def delete_daily_log(user_id: str, log_id: str) -> None:
    uid = PydanticObjectId(user_id)

    try:
        lid = PydanticObjectId(log_id)
    except Exception:
        raise NotFoundError("Habit log", log_id)

    record = await HabitTracking.find_one(
        {"_id": lid, "user_id": uid}
    )

    if not record:
        raise NotFoundError("Habit log", log_id)

    linked_goal_id = record.linked_goal_id

    await record.delete()

    if linked_goal_id:
        await adjust_active_goal_progress(user_id, linked_goal_id, -GOAL_PROGRESS_PER_LINK)

    await activity_service.log_activity(
        user_id=user_id,
        action_type="DELETED_HABIT",
        entity_type="HABIT",
        entity_id=str(record.id),
        description=f"Deleted habit log for {record.log_date.date()}",
    )


def _sleep_band_filter(band: SleepBand) -> dict:
    """Mongo range for one sleep bucket. `low`/`high` come from the analytics
    engine's own healthy range rather than being restated here — a second copy of
    those numbers would let the history table call a night healthy that the
    lifestyle score calls short."""
    low, high = SLEEP_HEALTHY_RANGE
    if band is SleepBand.BELOW:
        return {"$lt": Decimal128(str(low))}
    if band is SleepBand.ABOVE:
        return {"$gt": Decimal128(str(high))}
    return {"$gte": Decimal128(str(low)), "$lte": Decimal128(str(high))}


async def list_logs(
    user_id: str,
    page: int = 1,
    limit: int = 30,
    mood_rating: Optional[int] = None,
    sleep_band: Optional[SleepBand] = None,
) -> PaginatedHabitResponse:
    """
    Paginated habit history. Uses idx_habit_user_date_desc ESR index.
    """
    uid = PydanticObjectId(user_id)
    skip = (page - 1) * limit

    query_filter: dict = {"user_id": uid}
    if mood_rating is not None:
        query_filter["mood_rating"] = mood_rating
    if sleep_band is not None:
        # sleep_hours is stored as Decimal128, so the bounds must be too — a float
        # bound silently matches nothing against a Decimal128 field.
        query_filter["sleep_hours"] = _sleep_band_filter(sleep_band)

    records = await HabitTracking.find(
        query_filter,
        sort=[("log_date", -1)],
        skip=skip,
        limit=limit,
    ).to_list()

    total = await HabitTracking.find(query_filter).count()

    return PaginatedHabitResponse(
        data=[_to_response(r) for r in records],
        total=total,
        page=page,
        limit=limit,
        total_pages=max(1, -(-total // limit)),
    )


async def extract_kmeans_feature_space(
    user_id: str,
    days: int = 30,
) -> list[KMeansFeatureRow]:
    """
    Python port of extractKMeansFeatureSpace() from habit_repository.ts.
    Returns the 4D biometric feature matrix for K-Means burnout clustering.
    """
    uid = PydanticObjectId(user_id)

    from datetime import timedelta

    start_date = _midnight_utc() - timedelta(days=days)

    records = await HabitTracking.find(
        {
            "user_id": uid,
            "log_date": {"$gte": start_date},
        },
        sort=[("log_date", 1)],
    ).to_list()

    return [
        KMeansFeatureRow(
            log_id=str(r.id),
            user_id=str(r.user_id),
            sleep_hours=float(r.sleep_hours),
            exercise_minutes=r.exercise_minutes,
            water_intake_liters=float(r.water_intake_liters),
            screen_time_hours=float(r.screen_time_hours),
            log_date=r.log_date.strftime("%Y-%m-%d"),
        )
        for r in records
    ]