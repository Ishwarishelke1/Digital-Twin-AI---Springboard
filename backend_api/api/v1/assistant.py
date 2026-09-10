"""
api/v1/assistant.py — AI assistant chat + feedback endpoints (Milestone 4).
POST /api/v1/assistant/chat                  → grounded reply from Gemini, falling back to Groq.
POST /api/v1/assistant/chat/feedback         → thumbs-up/down on a chat reply.
GET  /api/v1/assistant/satisfaction-summary  → app-wide satisfaction score (chat + recommendation feedback).

Full chat history/transcripts are deliberately not persisted — only the feedback event
and a short snippet of the specific reply being rated (see models/feedback.py).
"""
import logging

from fastapi import APIRouter, Request

from api.dependencies import CurrentUser
from core.rate_limit import limiter
from schemas.assistant_schema import ChatRequest, ChatResponse
from schemas.feedback_schema import AssistantFeedbackRequest, SatisfactionSummaryResponse
from services.ai_assistant_service import get_assistant_reply
import services.feedback_service as feedback_service

logger = logging.getLogger("digital_twin_ai.assistant_router")
router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


@router.post("/chat", response_model=ChatResponse, summary="Send a message to the AI assistant")
@limiter.limit("15/minute")
async def chat(request: Request, body: ChatRequest, current_user: CurrentUser) -> ChatResponse:
    """Grounds the reply in the user's live profile, goals, finance, study,
    habits, forecasts and what-if history (services/ai_assistant_service.py's
    build_assistant_context), tries Gemini first, falls back to Groq on
    failure. Rate-limited since LLM calls cost money/quota, same reasoning as
    the auth-route limits."""
    history = [turn.model_dump() for turn in body.history] if body.history else None
    reply, provider_used = await get_assistant_reply(current_user, body.message, history)
    return ChatResponse(reply=reply, provider_used=provider_used)


@router.post("/chat/feedback", status_code=201, summary="Record feedback on an assistant reply")
async def submit_chat_feedback(body: AssistantFeedbackRequest, current_user: CurrentUser):
    record = await feedback_service.submit_assistant_feedback(
        str(current_user.id), body.message_snippet, body.feedback
    )
    return {"id": str(record.id), "feedback": record.feedback}


@router.get(
    "/satisfaction-summary",
    response_model=SatisfactionSummaryResponse,
    summary="App-wide user satisfaction score (chat + recommendation feedback)",
)
async def satisfaction_summary(current_user: CurrentUser) -> SatisfactionSummaryResponse:
    """Aggregates AssistantFeedback and Recommendation.user_feedback into one score —
    app-wide, not scoped to current_user, since this represents the whole testing/
    evaluation effort rather than one person's own session."""
    return await feedback_service.get_satisfaction_summary()
