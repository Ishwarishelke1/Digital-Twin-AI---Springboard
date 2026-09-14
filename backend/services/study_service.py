"""
services/study_service.py — Business logic layer for academic activity tracking.
Python equivalent of StudyActivityRepository from study_repository.ts.
Auto-percentage computation is handled at model validation (model_validator in StudyActivity).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from beanie import PydanticObjectId

from core.exceptions import BusinessRuleError, NotFoundError
from models.study import StudyActivity
from models.enums import SessionType
from schemas.study_schema import (
    StudyCreateRequest,
    StudyUpdateRequest,
    StudyRecordResponse,
    PaginatedStudyResponse,
    SubjectPerformanceSummary,
)
import services.activity_service as activity_service
from services.goal_progress_service import adjust_active_goal_progress

logger = logging.getLogger("digital_twin_ai.study_service")

# A study session has no numeric field that maps unambiguously onto an
# arbitrary goal's free-text `unit` (a goal could be tracked in "percent",
# "sessions", "hours" — anything the user typed when creating it). Rather than
# guess a unit-specific formula (the same mistake finance_service.py's earlier
# version made assuming every amount meant "money saved"), linking a session
# to a goal counts as flat +1 progress per session — "N of target sessions
# logged" is a safe, universal interpretation regardless of what the goal's
# unit actually is.
GOAL_PROGRESS_PER_LINK = Decimal("1")


def _to_response(record: StudyActivity) -> StudyRecordResponse:
    return StudyRecordResponse(
        id=str(record.id),
        user_id=str(record.user_id),
        subject=record.subject,
        study_hours=record.study_hours,
        session_type=record.session_type,
        quiz_marks=record.quiz_marks,
        max_quiz_marks=record.max_quiz_marks,
        quiz_marks_pct=record.quiz_marks_pct,
        exam_marks=record.exam_marks,
        max_exam_marks=record.max_exam_marks,
        exam_marks_pct=record.exam_marks_pct,
        focus_score=record.focus_score,
        linked_goal_id=record.linked_goal_id,
        session_date=record.session_date,
        created_at=record.created_at,
    )


async def log_study_session(
    user_id: str, payload: StudyCreateRequest
) -> StudyRecordResponse:
    """
    Creates a new study activity record.
    The StudyActivity model's model_validator auto-computes quiz_marks_pct and exam_marks_pct,
    mirroring the TypeScript StudyActivitySchema.pre('validate') middleware.
    """
    record = StudyActivity(
        user_id=PydanticObjectId(user_id),
        subject=payload.subject,
        study_hours=payload.study_hours,
        session_type=payload.session_type,
        quiz_marks=payload.quiz_marks,
        max_quiz_marks=payload.max_quiz_marks,
        exam_marks=payload.exam_marks,
        max_exam_marks=payload.max_exam_marks,
        focus_score=payload.focus_score,
        linked_goal_id=payload.linked_goal_id,
        session_date=payload.session_date or datetime.now(timezone.utc),
    )
    await record.insert()

    if record.linked_goal_id:
        await adjust_active_goal_progress(user_id, record.linked_goal_id, GOAL_PROGRESS_PER_LINK)

    logger.info("Study session logged: %s for user %s", record.subject, user_id)
    await activity_service.log_activity(
        user_id=user_id,
        action_type="CREATED_STUDY",
        entity_type="STUDY",
        entity_id=str(record.id),
        description=f"Logged {record.study_hours}h study session for {record.subject}"
    )
    return _to_response(record)

async def update_session(
    user_id: str, session_id: str, payload: StudyUpdateRequest
) -> StudyRecordResponse:
    uid = PydanticObjectId(user_id)
    try:
        sid = PydanticObjectId(session_id)
    except Exception:
        raise NotFoundError("Session", session_id)

    record = await StudyActivity.find_one({"_id": sid, "user_id": uid})
    if not record:
        raise NotFoundError("Session", session_id)

    old_linked_goal_id = record.linked_goal_id

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return _to_response(record)

    for key, value in update_data.items():
        setattr(record, key, value)

    # Re-link (or unlink) moves the flat +1 contribution from the old goal to
    # the new one — never both, never neither.
    if record.linked_goal_id != old_linked_goal_id:
        if old_linked_goal_id:
            await adjust_active_goal_progress(user_id, old_linked_goal_id, -GOAL_PROGRESS_PER_LINK)
        if record.linked_goal_id:
            await adjust_active_goal_progress(user_id, record.linked_goal_id, GOAL_PROGRESS_PER_LINK)

    # Validated here, not on StudyUpdateRequest itself — a PATCH payload alone
    # can't tell whether a max is "missing" or just not part of this particular
    # update (already set from creation); only the merged record can.
    if record.quiz_marks is not None and record.max_quiz_marks is None:
        raise BusinessRuleError("max_quiz_marks is required when quiz_marks is set.")
    if record.exam_marks is not None and record.max_exam_marks is None:
        raise BusinessRuleError("max_exam_marks is required when exam_marks is set.")

    # Re-trigger percentage computation
    record = record.compute_percentage_scores()

    await record.save()
    
    await activity_service.log_activity(
        user_id=user_id,
        action_type="UPDATED_STUDY",
        entity_type="STUDY",
        entity_id=str(record.id),
        description=f"Updated study session for {record.subject}"
    )
    
    return _to_response(record)

async def delete_session(user_id: str, session_id: str) -> None:
    uid = PydanticObjectId(user_id)
    try:
        sid = PydanticObjectId(session_id)
    except Exception:
        raise NotFoundError("Session", session_id)

    record = await StudyActivity.find_one({"_id": sid, "user_id": uid})
    if not record:
        raise NotFoundError("Session", session_id)

    linked_goal_id = record.linked_goal_id

    await record.delete()

    if linked_goal_id:
        await adjust_active_goal_progress(user_id, linked_goal_id, -GOAL_PROGRESS_PER_LINK)

    await activity_service.log_activity(
        user_id=user_id,
        action_type="DELETED_STUDY",
        entity_type="STUDY",
        entity_id=str(record.id),
        description=f"Deleted study session for {record.subject}"
    )


async def list_sessions(
    user_id: str,
    page: int = 1,
    limit: int = 20,
    subject_filter: Optional[str] = None,
    session_type_filter: Optional[SessionType] = None,
) -> PaginatedStudyResponse:
    """
    Paginated study history. Uses idx_study_user_date ESR index (user_id + session_date desc).
    """
    uid = PydanticObjectId(user_id)
    query_filter: dict = {"user_id": uid}
    if subject_filter:
        query_filter["subject"] = {
            "$regex": f"^{re.escape(subject_filter)}$",
            "$options": "i",
    }
    if session_type_filter:
        query_filter["session_type"] = session_type_filter

    skip = (page - 1) * limit
    records = await StudyActivity.find(
        query_filter,
        sort=[("session_date", -1)],
        skip=skip,
        limit=limit,
    ).to_list()

    total = await StudyActivity.find(query_filter).count()

    return PaginatedStudyResponse(
        data=[_to_response(r) for r in records],
        total=total,
        page=page,
        limit=limit,
        total_pages=max(1, -(-total // limit)),
    )


def _optional_pct(value) -> Optional[float]:
    """$avg returns None when no session in the group recorded the field. That stays
    None rather than becoming 0.0: a subject where nobody has sat an exam and a
    subject where everybody scored zero are different facts, and a caller that sees
    0.0 for both cannot tell them apart."""
    return None if value is None else round(float(str(value)), 2)


async def get_subject_performance(
    user_id: str,
    start_date: Optional[datetime] = None,
) -> list[SubjectPerformanceSummary]:
    """
    MongoDB aggregation pipeline — Python port of getSubjectPerformanceSummary()
    from study_repository.ts.
    """
    uid = PydanticObjectId(user_id)
    match_stage: dict = {"user_id": uid}
    if start_date:
        match_stage["session_date"] = {"$gte": start_date}

    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": "$subject",
            "total_study_hours":    {"$sum": "$study_hours"},
            "average_quiz_pct":     {"$avg": "$quiz_marks_pct"},
            "average_exam_pct":     {"$avg": "$exam_marks_pct"},
            "last_session_date":    {"$max": "$session_date"},
            "session_count":        {"$sum": 1},
        }},
        {"$sort": {"total_study_hours": -1}},
    ]

    results = await StudyActivity.aggregate(pipeline).to_list()
    return [
        SubjectPerformanceSummary(
            subject=r["_id"],
            total_study_hours=Decimal(str(r.get("total_study_hours") or 0)),
            average_quiz_pct=_optional_pct(r.get("average_quiz_pct")),
            average_exam_pct=_optional_pct(r.get("average_exam_pct")),
            session_count=r["session_count"],
            last_session_date=r.get("last_session_date"),
        )
        for r in results
    ]
