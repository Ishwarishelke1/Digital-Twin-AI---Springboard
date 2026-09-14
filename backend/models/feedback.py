"""
models/feedback.py — AI Assistant chat feedback (Milestone 4 satisfaction scoring).
Collection: `assistant_feedback`.

Only the feedback event + a short snippet of the reply being rated is persisted — full
chat history/transcripts are deliberately not stored (see api/v1/assistant.py's docstring).
Combined with the existing Recommendation.user_feedback (models/simulation.py) in
services/feedback_service.py to produce one app-wide satisfaction score.
"""
from __future__ import annotations

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from models.enums import UserFeedback


class AssistantFeedback(Document):
    user_id: PydanticObjectId
    message_snippet: str = Field(..., max_length=300)
    feedback: UserFeedback
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "assistant_feedback"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="idx_assistant_feedback_user_date",
            ),
        ]

    class Config:
        populate_by_name = True
