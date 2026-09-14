"""
schemas/feedback_schema.py — Request/response shapes for AI assistant chat feedback and
the app-wide satisfaction summary (Milestone 4).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AssistantFeedbackRequest(BaseModel):
    message_snippet: str = Field(..., min_length=1, max_length=300)
    feedback: str  # "HELPFUL" | "UNHELPFUL" | "IRRELEVANT" — validated against UserFeedback in the service


class SatisfactionSourceBreakdown(BaseModel):
    helpful: int
    unhelpful: int
    irrelevant: int
    total: int
    satisfaction_pct: float


class SatisfactionSummaryResponse(BaseModel):
    """GET /assistant/satisfaction-summary — app-wide, not per-user (see feedback_service
    docstring for why). satisfaction_pct = helpful / total * 100; IRRELEVANT counts as
    "not satisfied" in the denominator, same as UNHELPFUL — the raw breakdown is always
    included so that choice stays visible rather than hidden inside one number."""
    assistant_chat: SatisfactionSourceBreakdown
    recommendations: SatisfactionSourceBreakdown
    overall_satisfaction_pct: float
    total_responses: int
    generated_at: datetime
