"""
api/v1/study.py — Study data collection endpoints.
POST /api/v1/study/sessions                      → log a study session
GET  /api/v1/study/sessions                      → paginated session history
GET  /api/v1/study/analytics/subject-performance → aggregated performance by subject
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query, status

from api.dependencies import CurrentUser
from models.enums import SessionType
from schemas.study_schema import (
    StudyCreateRequest,
    StudyUpdateRequest,
    StudyRecordResponse,
    PaginatedStudyResponse,
    SubjectPerformanceSummary,
)
import services.study_service as study_service

logger = logging.getLogger("digital_twin_ai.study_router")
router = APIRouter(prefix="/study", tags=["Study Tracking"])


@router.post(
    "/sessions",
    response_model=StudyRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a new study session",
)
async def log_session(
    payload: StudyCreateRequest,
    current_user: CurrentUser,
) -> StudyRecordResponse:
    """
    Persists a study activity record.
    Percentage scores (quiz_marks_pct, exam_marks_pct) are auto-computed
    by the StudyActivity model_validator, mirroring the TS pre-validate middleware.
    """
    return await study_service.log_study_session(str(current_user.id), payload)


@router.patch(
    "/sessions/{session_id}",
    response_model=StudyRecordResponse,
    summary="Update a study session",
)
async def update_session(
    session_id: str,
    payload: StudyUpdateRequest,
    current_user: CurrentUser,
) -> StudyRecordResponse:
    """Updates an existing study session."""
    return await study_service.update_session(str(current_user.id), session_id, payload)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a study session",
)
async def delete_session(
    session_id: str,
    current_user: CurrentUser,
) -> None:
    """Deletes a study session."""
    await study_service.delete_session(str(current_user.id), session_id)


@router.get(
    "/sessions",
    response_model=PaginatedStudyResponse,
    summary="Get paginated study session history",
)
async def list_sessions(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    subject: Optional[str] = Query(default=None, description="Filter by subject name"),
    session_type: Optional[SessionType] = Query(default=None, description="Filter by session type"),
) -> PaginatedStudyResponse:
    """
    Returns paginated study records for the authenticated user.
    Leverages idx_study_user_date ESR index (user_id + session_date DESC).
    """
    return await study_service.list_sessions(
        user_id=str(current_user.id),
        page=page,
        limit=limit,
        subject_filter=subject,
        session_type_filter=session_type,
    )


@router.get(
    "/analytics/subject-performance",
    response_model=list[SubjectPerformanceSummary],
    summary="Aggregated academic performance per subject",
)
async def subject_performance(
    current_user: CurrentUser,
    months_back: Optional[int] = Query(default=None, ge=1, le=24, description="Filter to last N months"),
) -> list[SubjectPerformanceSummary]:
    """
    MongoDB aggregation pipeline grouping study hours and performance metrics by subject.
    Python port of getSubjectPerformanceSummary() from study_repository.ts.
    """
    start_date = None
    if months_back:
        start_date = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    return await study_service.get_subject_performance(str(current_user.id), start_date)
