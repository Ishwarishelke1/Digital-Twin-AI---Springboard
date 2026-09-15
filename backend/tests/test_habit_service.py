"""
tests/test_habit_service.py — Unit tests for services/habit_service.py.
Same no-DB/mocked-I/O approach as tests/test_finance_service.py.

upsert_daily_log is the one function that bypasses the Beanie ODM and talks to the
raw motor collection directly (via find_one_and_update) — this is the exact operation
the new unique (user_id, log_date) index backs, so it gets the most attention here.
"""
from datetime import datetime, timezone
from decimal import Decimal
from bson.decimal128 import Decimal128
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from core.exceptions import NotFoundError
from models.enums import BurnoutRisk
from models.habit import HabitTracking
from models.user import User
from schemas.habit_schema import HabitCreateRequest, HabitUpdateRequest
import services.habit_service as habit_service

USER_ID = "507f1f77bcf86cd799439011"
LOG_ID = "507f1f77bcf86cd799439044"
GOAL_ID = "e02fdbdc-00db-419f-848e-e4d6df52b0ef"
OTHER_GOAL_ID = "a11b1d2b-2222-4c3d-9999-000000000000"


def _patch_document_init():
    return patch.object(HabitTracking, "get_motor_collection", return_value=MagicMock())


def _patch_goal_update():
    """Mocks the goal-progress write path.

    adjust_active_goal_progress now does the $inc via find_one_and_update (it needs
    the post-increment value to re-derive status), then issues a second update_one
    only when the status actually changed. The echoed goal below stays well short of
    its target, so status is unchanged and no second write fires — keeping these
    tests focused on progress movement.
    """
    collection = MagicMock()

    async def _echo(query, update, **kwargs):
        return {
            "active_goals": [
                {
                    "goal_id": query.get("active_goals.goal_id"),
                    "current_value": Decimal128("1"),
                    "target_value": Decimal128("100"),
                    "status": "ACTIVE",
                    "completed_at": None,
                }
            ]
        }

    collection.find_one_and_update = AsyncMock(side_effect=_echo)
    collection.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return patch.object(User, "get_motor_collection", return_value=collection), collection


def _raw_mongo_result(**overrides):
    base = {
        "_id": PydanticObjectId(LOG_ID),
        "user_id": PydanticObjectId(USER_ID),
        "sleep_hours": Decimal("7.5"),
        "exercise_minutes": 30,
        "water_intake_liters": Decimal("2.0"),
        "screen_time_hours": Decimal("5.0"),
        "mood_rating": 4,
        "meditation_minutes": None,
        "productivity_score_computed": None,
        "lifestyle_score_computed": None,
        "burnout_risk_cluster": BurnoutRisk.UNKNOWN,
        "log_date": datetime(2026, 8, 18, tzinfo=timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


# ─── upsert_daily_log ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_daily_log_returns_the_upserted_record():
    payload = HabitCreateRequest(
        sleep_hours=Decimal("7.5"), exercise_minutes=30,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"), mood_rating=4,
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.find_one_and_update = AsyncMock(return_value=_raw_mongo_result())

    with _patch_document_init(), \
         patch.object(HabitTracking, "get_motor_collection", return_value=mock_collection), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()):
        result = await habit_service.upsert_daily_log(USER_ID, payload)

    assert result.sleep_hours == Decimal("7.5")
    assert result.exercise_minutes == 30


@pytest.mark.asyncio
async def test_upsert_daily_log_uses_upsert_true_and_a_user_plus_date_filter():
    """The exact filter shape (user_id, log_date) is what the new unique index enforces —
    if this filter ever drifted, the index would stop preventing duplicates correctly."""
    payload = HabitCreateRequest(
        sleep_hours=Decimal("6.0"), exercise_minutes=0,
        water_intake_liters=Decimal("1.5"), screen_time_hours=Decimal("8.0"),
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.find_one_and_update = AsyncMock(return_value=_raw_mongo_result())

    with _patch_document_init(), \
         patch.object(HabitTracking, "get_motor_collection", return_value=mock_collection), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()):
        await habit_service.upsert_daily_log(USER_ID, payload)

    call_args = mock_collection.find_one_and_update.call_args
    query_filter = call_args[0][0]
    assert set(query_filter.keys()) == {"user_id", "log_date"}
    assert call_args[1]["upsert"] is True


@pytest.mark.asyncio
async def test_upsert_daily_log_normalizes_log_date_to_midnight_utc():
    payload = HabitCreateRequest(
        sleep_hours=Decimal("7.0"), exercise_minutes=15,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("6.0"),
        log_date=datetime(2026, 8, 18, 14, 37, 22, tzinfo=timezone.utc),
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.find_one_and_update = AsyncMock(return_value=_raw_mongo_result())

    with _patch_document_init(), \
         patch.object(HabitTracking, "get_motor_collection", return_value=mock_collection), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()):
        await habit_service.upsert_daily_log(USER_ID, payload)

    query_filter = mock_collection.find_one_and_update.call_args[0][0]
    assert query_filter["log_date"] == datetime(2026, 8, 18, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_upsert_daily_log_first_time_linked_to_goal_adds_flat_one_progress():
    """A habit log has no numeric field that maps unambiguously onto an arbitrary
    goal's free-text unit, so linking counts as a flat +1 per day logged."""
    payload = HabitCreateRequest(
        sleep_hours=Decimal("7.5"), exercise_minutes=30,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        linked_goal_id=GOAL_ID,
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)  # no existing log today
    mock_collection.find_one_and_update = AsyncMock(return_value=_raw_mongo_result(linked_goal_id=GOAL_ID))

    goal_patch, goal_collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(HabitTracking, "get_motor_collection", return_value=mock_collection), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await habit_service.upsert_daily_log(USER_ID, payload)

    goal_collection.find_one_and_update.assert_awaited_once()
    _, update_arg = goal_collection.find_one_and_update.call_args.args
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("1")


@pytest.mark.asyncio
async def test_upsert_daily_log_relinking_on_same_day_relog_moves_progress():
    """Logging again for a day already logged (upsert = update) that changes
    which goal it's linked to must move the +1, not add a second one."""
    payload = HabitCreateRequest(
        sleep_hours=Decimal("7.5"), exercise_minutes=30,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        linked_goal_id=OTHER_GOAL_ID,
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=_raw_mongo_result(linked_goal_id=GOAL_ID))
    mock_collection.find_one_and_update = AsyncMock(
        return_value=_raw_mongo_result(linked_goal_id=OTHER_GOAL_ID)
    )

    goal_patch, goal_collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(HabitTracking, "get_motor_collection", return_value=mock_collection), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await habit_service.upsert_daily_log(USER_ID, payload)

    assert goal_collection.find_one_and_update.await_count == 2
    first_filter, first_update = goal_collection.find_one_and_update.await_args_list[0].args
    assert first_filter["active_goals.goal_id"] == GOAL_ID
    assert first_update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-1")
    second_filter, second_update = goal_collection.find_one_and_update.await_args_list[1].args
    assert second_filter["active_goals.goal_id"] == OTHER_GOAL_ID
    assert second_update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("1")


@pytest.mark.asyncio
async def test_upsert_daily_log_relog_same_goal_link_leaves_progress_alone():
    payload = HabitCreateRequest(
        sleep_hours=Decimal("8.0"), exercise_minutes=45,
        water_intake_liters=Decimal("2.5"), screen_time_hours=Decimal("4.0"),
        linked_goal_id=GOAL_ID,
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=_raw_mongo_result(linked_goal_id=GOAL_ID))
    mock_collection.find_one_and_update = AsyncMock(return_value=_raw_mongo_result(linked_goal_id=GOAL_ID))

    goal_patch, goal_collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(HabitTracking, "get_motor_collection", return_value=mock_collection), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await habit_service.upsert_daily_log(USER_ID, payload)

    goal_collection.find_one_and_update.assert_not_awaited()


# ─── update_log ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_log_normal_case():
    record = HabitTracking.model_construct(
        user_id=PydanticObjectId(USER_ID), sleep_hours=Decimal("7.0"), exercise_minutes=20,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        mood_rating=3, meditation_minutes=None,
        productivity_score_computed=None, lifestyle_score_computed=None,
        burnout_risk_cluster=BurnoutRisk.UNKNOWN, linked_goal_id=None,
        log_date=datetime(2026, 8, 18, tzinfo=timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(LOG_ID)

    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(HabitTracking, "save", new=AsyncMock()), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()):
        result = await habit_service.update_log(
            USER_ID, LOG_ID, HabitUpdateRequest(sleep_hours=Decimal("8.0"))
        )
    assert result.sleep_hours == Decimal("8.0")


@pytest.mark.asyncio
async def test_update_log_does_not_touch_log_date():
    """HabitUpdateRequest has no log_date field at all — the unique
    (user_id, log_date) index means editing it belongs to delete + re-log,
    not an in-place PATCH."""
    original_date = datetime(2026, 8, 18, tzinfo=timezone.utc)
    record = HabitTracking.model_construct(
        user_id=PydanticObjectId(USER_ID), sleep_hours=Decimal("7.0"), exercise_minutes=20,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        mood_rating=3, meditation_minutes=None,
        productivity_score_computed=None, lifestyle_score_computed=None,
        burnout_risk_cluster=BurnoutRisk.UNKNOWN, linked_goal_id=None,
        log_date=original_date, created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(LOG_ID)

    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(HabitTracking, "save", new=AsyncMock()), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()):
        result = await habit_service.update_log(
            USER_ID, LOG_ID, HabitUpdateRequest(mood_rating=5)
        )
    assert result.log_date == original_date


@pytest.mark.asyncio
async def test_update_log_relinking_goal_moves_the_flat_progress():
    record = HabitTracking.model_construct(
        user_id=PydanticObjectId(USER_ID), sleep_hours=Decimal("7.0"), exercise_minutes=20,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        mood_rating=3, meditation_minutes=None,
        productivity_score_computed=None, lifestyle_score_computed=None,
        burnout_risk_cluster=BurnoutRisk.UNKNOWN, linked_goal_id=GOAL_ID,
        log_date=datetime(2026, 8, 18, tzinfo=timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(LOG_ID)

    goal_patch, collection = _patch_goal_update()
    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(HabitTracking, "save", new=AsyncMock()), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await habit_service.update_log(
            USER_ID, LOG_ID, HabitUpdateRequest(linked_goal_id=OTHER_GOAL_ID)
        )

    assert collection.find_one_and_update.await_count == 2
    first_filter, first_update = collection.find_one_and_update.await_args_list[0].args
    assert first_filter["active_goals.goal_id"] == GOAL_ID
    assert first_update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-1")
    second_filter, second_update = collection.find_one_and_update.await_args_list[1].args
    assert second_filter["active_goals.goal_id"] == OTHER_GOAL_ID
    assert second_update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("1")


@pytest.mark.asyncio
async def test_update_log_editing_unrelated_field_leaves_progress_alone():
    record = HabitTracking.model_construct(
        user_id=PydanticObjectId(USER_ID), sleep_hours=Decimal("7.0"), exercise_minutes=20,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        mood_rating=3, meditation_minutes=None,
        productivity_score_computed=None, lifestyle_score_computed=None,
        burnout_risk_cluster=BurnoutRisk.UNKNOWN, linked_goal_id=GOAL_ID,
        log_date=datetime(2026, 8, 18, tzinfo=timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(LOG_ID)

    goal_patch, collection = _patch_goal_update()
    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(HabitTracking, "save", new=AsyncMock()), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await habit_service.update_log(
            USER_ID, LOG_ID, HabitUpdateRequest(mood_rating=5)
        )
    collection.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_log_not_found_bad_id_format():
    with pytest.raises(NotFoundError):
        await habit_service.update_log(USER_ID, "not-an-object-id", HabitUpdateRequest())


@pytest.mark.asyncio
async def test_update_log_not_found_valid_id_no_match():
    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await habit_service.update_log(USER_ID, LOG_ID, HabitUpdateRequest())


# ─── delete_daily_log ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_daily_log_normal_case():
    record = HabitTracking.model_construct(
        user_id=PydanticObjectId(USER_ID), sleep_hours=Decimal("7.0"), exercise_minutes=20,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        log_date=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(LOG_ID)

    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(HabitTracking, "delete", new=AsyncMock()) as mock_delete, \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()):
        await habit_service.delete_daily_log(USER_ID, LOG_ID)
    mock_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_daily_log_reverses_linked_goal_progress():
    record = HabitTracking.model_construct(
        user_id=PydanticObjectId(USER_ID), sleep_hours=Decimal("7.0"), exercise_minutes=20,
        water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
        log_date=datetime.now(timezone.utc), linked_goal_id=GOAL_ID,
    )
    record.id = PydanticObjectId(LOG_ID)

    goal_patch, goal_collection = _patch_goal_update()
    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(HabitTracking, "delete", new=AsyncMock()), \
         patch("services.habit_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await habit_service.delete_daily_log(USER_ID, LOG_ID)

    goal_collection.find_one_and_update.assert_awaited_once()
    _, update_arg = goal_collection.find_one_and_update.call_args.args
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-1")


@pytest.mark.asyncio
async def test_delete_daily_log_not_found_bad_id_format():
    with pytest.raises(NotFoundError):
        await habit_service.delete_daily_log(USER_ID, "not-an-object-id")


@pytest.mark.asyncio
async def test_delete_daily_log_not_found_valid_id_no_match():
    with patch.object(HabitTracking, "find_one", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await habit_service.delete_daily_log(USER_ID, LOG_ID)


# ─── list_logs ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_logs_pagination_math():
    query = MagicMock()
    query.to_list = AsyncMock(return_value=[])
    query.count = AsyncMock(return_value=61)

    with patch.object(HabitTracking, "find", return_value=query):
        result = await habit_service.list_logs(USER_ID, page=1, limit=30)
    assert result.total == 61
    assert result.total_pages == 3


# ─── extract_kmeans_feature_space ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_kmeans_feature_space_row_shape():
    record = HabitTracking.model_construct(
        user_id=PydanticObjectId(USER_ID), sleep_hours=Decimal("7.0"), exercise_minutes=25,
        water_intake_liters=Decimal("2.2"), screen_time_hours=Decimal("4.5"),
        log_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    record.id = PydanticObjectId(LOG_ID)

    query = MagicMock()
    query.to_list = AsyncMock(return_value=[record])

    with patch.object(HabitTracking, "find", return_value=query):
        rows = await habit_service.extract_kmeans_feature_space(USER_ID, days=30)

    assert len(rows) == 1
    assert rows[0].log_id == LOG_ID
    assert rows[0].sleep_hours == 7.0
    assert rows[0].log_date == "2026-08-10"
