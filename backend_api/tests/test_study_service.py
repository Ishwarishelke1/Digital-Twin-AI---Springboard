"""
tests/test_study_service.py — Unit tests for services/study_service.py.
Same no-DB/mocked-I/O approach as tests/test_finance_service.py.
"""
from datetime import datetime, timezone
from decimal import Decimal
from bson.decimal128 import Decimal128
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from core.exceptions import BusinessRuleError, NotFoundError
from models.enums import SessionType
from models.study import StudyActivity
from models.user import User
from schemas.study_schema import StudyCreateRequest, StudyUpdateRequest
import services.study_service as study_service

USER_ID = "507f1f77bcf86cd799439011"
SESSION_ID = "507f1f77bcf86cd799439033"
GOAL_ID = "e02fdbdc-00db-419f-848e-e4d6df52b0ef"
OTHER_GOAL_ID = "a11b1d2b-2222-4c3d-9999-000000000000"


def _fake_insert():
    async def insert(self):
        self.id = PydanticObjectId(SESSION_ID)
        return self
    return insert


def _patch_document_init():
    return patch.object(StudyActivity, "get_motor_collection", return_value=MagicMock())


def _patch_goal_update():
    """Mocks the goal-progress write path against User's raw Motor collection.

    The $inc now goes through find_one_and_update (adjust_active_goal_progress
    needs the post-increment value to re-derive status), followed by a second
    update_one only when status actually changed. The echoed goal below stays
    well short of its target, so no status write fires and these tests stay
    focused on progress movement.
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


# ─── log_study_session ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_study_session_normal_case():
    payload = StudyCreateRequest(subject="Mathematics", study_hours=Decimal("2.0"), session_type=SessionType.DEEP_WORK)
    with _patch_document_init(), \
         patch.object(StudyActivity, "insert", new=_fake_insert()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()):
        result = await study_service.log_study_session(USER_ID, payload)
    assert result.subject == "Mathematics"
    assert result.study_hours == Decimal("2.0")


@pytest.mark.asyncio
async def test_log_study_session_linked_goal_id_passed_through_as_str():
    payload = StudyCreateRequest(
        subject="Physics", study_hours=Decimal("1.5"), session_type=SessionType.REVIEW, linked_goal_id=GOAL_ID,
    )
    goal_patch, _ = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(StudyActivity, "insert", new=_fake_insert()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        result = await study_service.log_study_session(USER_ID, payload)
    assert result.linked_goal_id == GOAL_ID


@pytest.mark.asyncio
async def test_log_study_session_linked_to_goal_adds_flat_one_progress():
    """A session has no numeric field that maps unambiguously onto an arbitrary
    goal's free-text unit, so linking counts as a flat +1 regardless of study_hours."""
    payload = StudyCreateRequest(
        subject="Physics", study_hours=Decimal("3.0"), session_type=SessionType.REVIEW, linked_goal_id=GOAL_ID,
    )
    goal_patch, collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(StudyActivity, "insert", new=_fake_insert()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await study_service.log_study_session(USER_ID, payload)

    collection.find_one_and_update.assert_awaited_once()
    _, update_arg = collection.find_one_and_update.call_args.args
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("1")


@pytest.mark.asyncio
async def test_log_study_session_without_goal_does_not_touch_goals():
    payload = StudyCreateRequest(subject="Physics", study_hours=Decimal("1.0"), session_type=SessionType.REVIEW)
    goal_patch, collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(StudyActivity, "insert", new=_fake_insert()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await study_service.log_study_session(USER_ID, payload)
    collection.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_log_study_session_auto_computes_quiz_percentage():
    payload = StudyCreateRequest(
        subject="CS", study_hours=Decimal("3.0"), session_type=SessionType.PRACTICE_EXAM,
        quiz_marks=Decimal("18"), max_quiz_marks=Decimal("20"),
    )
    with _patch_document_init(), \
         patch.object(StudyActivity, "insert", new=_fake_insert()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()):
        result = await study_service.log_study_session(USER_ID, payload)
    assert result.quiz_marks_pct == Decimal("90.00")


# ─── update_session ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_session_normal_case():
    record = StudyActivity.model_construct(
        user_id=PydanticObjectId(USER_ID), subject="Mathematics", study_hours=Decimal("2.0"),
        session_type=SessionType.DEEP_WORK, attendance_pct=Decimal("100"),
        quiz_marks=None, max_quiz_marks=None, quiz_marks_pct=None,
        exam_marks=None, max_exam_marks=None, exam_marks_pct=None,
        focus_score=None, linked_goal_id=None,
        session_date=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(SESSION_ID)

    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(StudyActivity, "save", new=AsyncMock()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()):
        result = await study_service.update_session(
            USER_ID, SESSION_ID, StudyUpdateRequest(study_hours=Decimal("3.5"))
        )
    assert result.study_hours == Decimal("3.5")


@pytest.mark.asyncio
async def test_update_session_relinking_goal_moves_the_flat_progress():
    record = StudyActivity.model_construct(
        user_id=PydanticObjectId(USER_ID), subject="Mathematics", study_hours=Decimal("2.0"),
        session_type=SessionType.DEEP_WORK, attendance_pct=Decimal("100"),
        quiz_marks=None, max_quiz_marks=None, quiz_marks_pct=None,
        exam_marks=None, max_exam_marks=None, exam_marks_pct=None,
        focus_score=None, linked_goal_id=GOAL_ID,
        session_date=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(SESSION_ID)

    goal_patch, collection = _patch_goal_update()
    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(StudyActivity, "save", new=AsyncMock()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await study_service.update_session(
            USER_ID, SESSION_ID, StudyUpdateRequest(linked_goal_id=OTHER_GOAL_ID)
        )

    assert collection.find_one_and_update.await_count == 2
    first_filter, first_update = collection.find_one_and_update.await_args_list[0].args
    assert first_filter["active_goals.goal_id"] == GOAL_ID
    assert first_update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-1")
    second_filter, second_update = collection.find_one_and_update.await_args_list[1].args
    assert second_filter["active_goals.goal_id"] == OTHER_GOAL_ID
    assert second_update["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("1")


@pytest.mark.asyncio
async def test_update_session_editing_hours_without_changing_goal_link_leaves_progress_alone():
    """Only a change in linked_goal_id itself should move progress — editing an
    unrelated field on an already-linked session shouldn't add another +1."""
    record = StudyActivity.model_construct(
        user_id=PydanticObjectId(USER_ID), subject="Mathematics", study_hours=Decimal("2.0"),
        session_type=SessionType.DEEP_WORK, attendance_pct=Decimal("100"),
        quiz_marks=None, max_quiz_marks=None, quiz_marks_pct=None,
        exam_marks=None, max_exam_marks=None, exam_marks_pct=None,
        focus_score=None, linked_goal_id=GOAL_ID,
        session_date=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(SESSION_ID)

    goal_patch, collection = _patch_goal_update()
    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(StudyActivity, "save", new=AsyncMock()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await study_service.update_session(
            USER_ID, SESSION_ID, StudyUpdateRequest(study_hours=Decimal("4.0"))
        )
    collection.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_session_rejects_quiz_marks_without_max_on_merged_record():
    record = StudyActivity.model_construct(
        user_id=PydanticObjectId(USER_ID), subject="Mathematics", study_hours=Decimal("2.0"),
        session_type=SessionType.DEEP_WORK, attendance_pct=Decimal("100"),
        quiz_marks=None, max_quiz_marks=None, quiz_marks_pct=None,
        exam_marks=None, max_exam_marks=None, exam_marks_pct=None,
        focus_score=None, linked_goal_id=None,
        session_date=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(SESSION_ID)

    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=record)):
        with pytest.raises(BusinessRuleError):
            await study_service.update_session(
                USER_ID, SESSION_ID, StudyUpdateRequest(quiz_marks=Decimal("85"))
            )


@pytest.mark.asyncio
async def test_update_session_allows_quiz_marks_when_max_already_set_on_record():
    """Regression test: a PATCH that only sends {"quiz_marks": 85} must succeed
    when the existing record already has max_quiz_marks set from creation —
    the old StudyUpdateRequest-level validator rejected this legitimate case
    because it could only see the PATCH payload, not the existing record."""
    record = StudyActivity.model_construct(
        user_id=PydanticObjectId(USER_ID), subject="Mathematics", study_hours=Decimal("2.0"),
        session_type=SessionType.DEEP_WORK, attendance_pct=Decimal("100"),
        quiz_marks=None, max_quiz_marks=Decimal("100"), quiz_marks_pct=None,
        exam_marks=None, max_exam_marks=None, exam_marks_pct=None,
        focus_score=None, linked_goal_id=None,
        session_date=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(SESSION_ID)

    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(StudyActivity, "save", new=AsyncMock()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()):
        result = await study_service.update_session(
            USER_ID, SESSION_ID, StudyUpdateRequest(quiz_marks=Decimal("85"))
        )
    assert result.quiz_marks == Decimal("85")


@pytest.mark.asyncio
async def test_update_session_not_found_bad_id_format():
    with pytest.raises(NotFoundError):
        await study_service.update_session(USER_ID, "not-an-object-id", StudyUpdateRequest())


@pytest.mark.asyncio
async def test_update_session_not_found_valid_id_no_match():
    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await study_service.update_session(USER_ID, SESSION_ID, StudyUpdateRequest())


# ─── delete_session ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_session_normal_case():
    record = StudyActivity.model_construct(
        user_id=PydanticObjectId(USER_ID), subject="Physics", study_hours=Decimal("1.0"),
        session_type=SessionType.REVIEW,
    )
    record.id = PydanticObjectId(SESSION_ID)

    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(StudyActivity, "delete", new=AsyncMock()) as mock_delete, \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()):
        await study_service.delete_session(USER_ID, SESSION_ID)
    mock_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_session_reverses_linked_goal_progress():
    record = StudyActivity.model_construct(
        user_id=PydanticObjectId(USER_ID), subject="Physics", study_hours=Decimal("1.0"),
        session_type=SessionType.REVIEW, linked_goal_id=GOAL_ID,
    )
    record.id = PydanticObjectId(SESSION_ID)

    goal_patch, collection = _patch_goal_update()
    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(StudyActivity, "delete", new=AsyncMock()), \
         patch("services.study_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await study_service.delete_session(USER_ID, SESSION_ID)

    collection.find_one_and_update.assert_awaited_once()
    _, update_arg = collection.find_one_and_update.call_args.args
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-1")


@pytest.mark.asyncio
async def test_delete_session_not_found():
    with patch.object(StudyActivity, "find_one", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await study_service.delete_session(USER_ID, SESSION_ID)


# ─── list_sessions ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_sessions_pagination_math():
    query = MagicMock()
    query.to_list = AsyncMock(return_value=[])
    query.count = AsyncMock(return_value=41)

    with patch.object(StudyActivity, "find", return_value=query):
        result = await study_service.list_sessions(USER_ID, page=1, limit=20)
    assert result.total == 41
    assert result.total_pages == 3


@pytest.mark.asyncio
async def test_list_sessions_subject_filter_reaches_query():
    """subject_filter is matched case-insensitively (a user typing "physics"
    should still match a session logged as "Physics") — an exact anchored
    regex, not a substring match, so "Physics 101" doesn't match "Physics"."""
    captured = {}

    def fake_find(query_filter, **kwargs):
        captured["filter"] = query_filter
        query = MagicMock()
        query.to_list = AsyncMock(return_value=[])
        query.count = AsyncMock(return_value=0)
        return query

    with patch.object(StudyActivity, "find", side_effect=fake_find):
        await study_service.list_sessions(USER_ID, subject_filter="Physics")
    assert captured["filter"]["subject"] == {"$regex": "^Physics$", "$options": "i"}


# ─── get_subject_performance ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_subject_performance_maps_aggregation_results():
    raw_results = [
        {"_id": "Mathematics", "total_study_hours": 12.5, "average_attendance_pct": 95.0,
         "average_quiz_pct": 80.0, "average_exam_pct": None, "session_count": 5},
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=raw_results)

    with patch.object(StudyActivity, "aggregate", return_value=mock_cursor):
        items = await study_service.get_subject_performance(USER_ID)
    assert items[0].subject == "Mathematics"
    assert items[0].session_count == 5
    assert items[0].average_exam_pct == 0.0  # None -> 0, not a crash
