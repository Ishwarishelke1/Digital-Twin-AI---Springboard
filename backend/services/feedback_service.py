"""
services/feedback_service.py — AI assistant chat feedback + app-wide satisfaction
summary (Milestone 4's "user satisfaction score" evaluation criterion).

Combines two feedback sources into one score:
  - AssistantFeedback (models/feedback.py) — thumbs-up/down on AI Assistant chat replies.
  - Recommendation.user_feedback (models/simulation.py) — already existed since Milestone 3
    (PATCH /simulation/recommendations/{id}/feedback) but was never aggregated anywhere.
Both use the same UserFeedback enum (models/enums.py), so they combine directly.
"""
from datetime import datetime, timezone

from beanie import PydanticObjectId

from core.exceptions import BusinessRuleError
from models.enums import UserFeedback
from models.feedback import AssistantFeedback
from models.simulation import Recommendation
from schemas.feedback_schema import SatisfactionSourceBreakdown, SatisfactionSummaryResponse


async def submit_assistant_feedback(user_id: str, message_snippet: str, feedback: str) -> AssistantFeedback:
    try:
        feedback_enum = UserFeedback(feedback.upper())
    except ValueError:
        raise BusinessRuleError(
            f"Invalid feedback value '{feedback}'. Must be one of: {[f.value for f in UserFeedback]}"
        )

    record = AssistantFeedback(
        user_id=PydanticObjectId(user_id),
        message_snippet=message_snippet[:300],
        feedback=feedback_enum,
    )
    await record.insert()
    return record


def _breakdown(feedback_values: list[UserFeedback]) -> SatisfactionSourceBreakdown:
    helpful = sum(1 for f in feedback_values if f == UserFeedback.HELPFUL)
    unhelpful = sum(1 for f in feedback_values if f == UserFeedback.UNHELPFUL)
    irrelevant = sum(1 for f in feedback_values if f == UserFeedback.IRRELEVANT)
    total = len(feedback_values)
    satisfaction_pct = round(helpful / total * 100, 2) if total else 0.0
    return SatisfactionSourceBreakdown(
        helpful=helpful, unhelpful=unhelpful, irrelevant=irrelevant, total=total,
        satisfaction_pct=satisfaction_pct,
    )


async def get_satisfaction_summary() -> SatisfactionSummaryResponse:
    """App-wide aggregate (not filtered by current_user) — "user satisfaction during
    testing and evaluation" describes the whole testing effort, not one person's own
    session. Expected volume during a testing phase is small (tens of responses), so
    this counts in plain Python rather than an aggregation pipeline."""
    chat_docs = await AssistantFeedback.find_all().to_list()
    rec_docs = await Recommendation.find(Recommendation.user_feedback != None).to_list()  # noqa: E711

    chat_breakdown = _breakdown([d.feedback for d in chat_docs])
    rec_breakdown = _breakdown([d.user_feedback for d in rec_docs])

    all_values = [d.feedback for d in chat_docs] + [d.user_feedback for d in rec_docs]
    overall = _breakdown(all_values)

    return SatisfactionSummaryResponse(
        assistant_chat=chat_breakdown,
        recommendations=rec_breakdown,
        overall_satisfaction_pct=overall.satisfaction_pct,
        total_responses=overall.total,
        generated_at=datetime.now(timezone.utc),
    )
