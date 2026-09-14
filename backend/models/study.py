"""
models/study.py — Beanie ODM Document mirroring backend/database/schemas/academic_schema.ts.
Collection: `study_activities`
Pre-save middleware (quiz/exam % calculation) is replicated in the service layer.
DO NOT alter field names — they map directly to existing MongoDB documents.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from beanie import Document, DecimalAnnotation, PydanticObjectId
from pydantic import Field, model_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from models.enums import SessionType


class StudyActivity(Document):
    user_id: PydanticObjectId
    subject: str = Field(..., max_length=100)
    study_hours: DecimalAnnotation = Field(..., ge=Decimal("0.1"), le=Decimal("24.0"))
    session_type: SessionType

    # Optional mark fields
    quiz_marks: Optional[DecimalAnnotation] = None
    max_quiz_marks: Optional[DecimalAnnotation] = None
    quiz_marks_pct: Optional[DecimalAnnotation] = None        # Auto-computed (mirrors pre-validate middleware)

    exam_marks: Optional[DecimalAnnotation] = None
    max_exam_marks: Optional[DecimalAnnotation] = None
    exam_marks_pct: Optional[DecimalAnnotation] = None        # Auto-computed (mirrors pre-validate middleware)

    focus_score: Optional[int] = Field(default=None, ge=0, le=100)
    # str, not PydanticObjectId: active_goals.goal_id is a UUID string (models/user.py),
    # not a Mongo ObjectId — this field must match that type to actually be usable.
    linked_goal_id: Optional[str] = None

    session_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def compute_percentage_scores(self) -> "StudyActivity":
        """
        Replicates the StudyActivitySchema.pre('validate') middleware from academic_schema.ts.
        Automatically computes quiz_marks_pct and exam_marks_pct when raw marks are provided,
        and clears the percentage when they are removed.

        The clear matters on update: a percentage left behind after its marks were
        cleared would keep feeding the subject-performance averages, so a score the
        user deleted would go on counting.
        """
        if self.quiz_marks is not None and self.max_quiz_marks is not None and self.max_quiz_marks > 0:
            self.quiz_marks_pct = round((self.quiz_marks / self.max_quiz_marks) * 100, 2)
        elif self.quiz_marks is None:
            self.quiz_marks_pct = None

        if self.exam_marks is not None and self.max_exam_marks is not None and self.max_exam_marks > 0:
            self.exam_marks_pct = round((self.exam_marks / self.max_exam_marks) * 100, 2)
        elif self.exam_marks is None:
            self.exam_marks_pct = None

        return self

    class Settings:
        name = "study_activities"   # ← Exact collection name from TS layer
        # Already live on the database (created out-of-band); declared here so a
        # fresh database gets them too. Names/keys match the live indexes exactly.
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("session_date", DESCENDING)],
                name="idx_study_user_date",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("subject", ASCENDING), ("session_date", DESCENDING)],
                name="idx_study_user_subj_date",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("session_type", ASCENDING), ("session_date", DESCENDING)],
                name="idx_study_user_type_date",
            ),
        ]

    class Config:
        populate_by_name = True
