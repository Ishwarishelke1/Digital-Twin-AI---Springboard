"""
schemas/assistant_schema.py — Request/response shapes for the AI assistant
chat endpoint (Milestone 4).
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """One prior turn, echoed back by the client for bounded multi-turn memory.
    Transcripts are deliberately not persisted server-side (see
    api/v1/assistant.py's module docstring) — the client holds history and
    resends the tail of it on each request; ai_assistant_service.py trims to
    the last MAX_HISTORY_TURNS regardless of how many are sent."""
    sender: Literal["user", "ai"]
    text: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: Optional[list[ChatTurn]] = Field(
        default=None,
        max_length=20,
        description="Recent prior turns for conversational continuity, oldest first.",
    )


class ChatResponse(BaseModel):
    reply: str
    provider_used: str
