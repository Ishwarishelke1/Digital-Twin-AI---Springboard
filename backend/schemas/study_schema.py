"""
schemas/study_schema.py — Pydantic request/response schemas for study activity endpoints.
Field names mirror backend/database/schemas/academic_schema.ts exactly.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from models.enums import SessionType


class StudyCreateRequest(BaseModel):
    """POST /api/v1/study/sessions"""
    subject: str = Field(..., max_length=100)
    study_hours: Decimal = Field(..., ge=Decimal("0.1"), le=Decimal("24.0"))
    session_type: SessionType

    quiz_marks: Optional[Decimal] = None
    max_quiz_marks: Optional[Decimal] = None

    exam_marks: Optional[Decimal] = None
    max_exam_marks: Optional[Decimal] = None

    focus_score: Optional[int] = Field(default=None, ge=0, le=100)
    linked_goal_id: Optional[str] = None
    session_date: Optional[datetime] = None

    @model_validator(mode="after")
    def max_marks_required_when_marks_given(self) -> "StudyCreateRequest":
        """Mirrors: required: function() { return this.quiz_marks !== undefined; }"""
        if self.quiz_marks is not None and self.max_quiz_marks is None:
            raise ValueError("max_quiz_marks is required when quiz_marks is provided.")
        if self.exam_marks is not None and self.max_exam_marks is None:
            raise ValueError("max_exam_marks is required when exam_marks is provided.")
        return self

class StudyUpdateRequest(BaseModel):
    """PATCH /api/v1/study/sessions/{id}"""
    subject: Optional[str] = Field(default=None, max_length=100)
    study_hours: Optional[Decimal] = Field(default=None, ge=Decimal("0.1"), le=Decimal("24.0"))
    session_type: Optional[SessionType] = None

    quiz_marks: Optional[Decimal] = None
    max_quiz_marks: Optional[Decimal] = None

    exam_marks: Optional[Decimal] = None
    max_exam_marks: Optional[Decimal] = None

    focus_score: Optional[int] = Field(default=None, ge=0, le=100)
    linked_goal_id: Optional[str] = None
    session_date: Optional[datetime] = None

    # No "max required when marks given" validator here, unlike StudyCreateRequest —
    # this is a PATCH payload, not the full record. A request that only sends
    # {"quiz_marks": 85} is valid as long as the *existing* record already has
    # max_quiz_marks set (from creation); this schema can't see that, only the
    # merged record can, so that check happens in study_service.update_session
    # instead. Validating it here rejected legitimate partial updates.


class StudyRecordResponse(BaseModel):
    id: str
    user_id: str
    subject: str
    study_hours: Decimal
    session_type: SessionType
    quiz_marks: Optional[Decimal]
    max_quiz_marks: Optional[Decimal]
    quiz_marks_pct: Optional[Decimal]       # Auto-computed
    exam_marks: Optional[Decimal]
    max_exam_marks: Optional[Decimal]
    exam_marks_pct: Optional[Decimal]       # Auto-computed
    focus_score: Optional[int]
    linked_goal_id: Optional[str]
    session_date: datetime
    created_at: datetime


class PaginatedStudyResponse(BaseModel):
    data: list[StudyRecordResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class SubjectPerformanceSummary(BaseModel):
    """Aggregated subject-level summary for dashboard & ML pipelines."""
    subject: str
    total_study_hours: Decimal
    average_quiz_pct: Optional[float] = None
    average_exam_pct: Optional[float] = None
    session_count: int
    last_session_date: Optional[datetime] = None
