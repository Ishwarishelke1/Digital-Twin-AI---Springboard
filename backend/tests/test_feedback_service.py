"""
tests/test_feedback_service.py — Unit tests for services/feedback_service.py.
No real DB/network — mirrors the mocking style of tests/test_finance_service.py.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from core.exceptions import BusinessRuleError
from models.enums import UserFeedback
from models.feedback import AssistantFeedback
import services.feedback_service as feedback_service

USER_ID = "507f1f77bcf86cd799439011"
RECORD_ID = "507f1f77bcf86cd799439033"


def _fake_insert():
    async def insert(self):
        self.id = PydanticObjectId(RECORD_ID)
        return self
    return insert


def _patch_document_init():
    return patch.object(AssistantFeedback, "get_motor_collection", return_value=MagicMock())


def _feedback_doc(value: UserFeedback):
    return MagicMock(feedback=value)


def _recommendation_doc(value: UserFeedback):
    return MagicMock(user_feedback=value)


# ─── submit_assistant_feedback ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_assistant_feedback_valid():
    with _patch_document_init(), patch.object(AssistantFeedback, "insert", new=_fake_insert()):
        result = await feedback_service.submit_assistant_feedback(USER_ID, "Great answer", "helpful")
    assert result.feedback == UserFeedback.HELPFUL
    assert str(result.id) == RECORD_ID
    assert result.message_snippet == "Great answer"


@pytest.mark.asyncio
async def test_submit_assistant_feedback_truncates_long_snippet():
    long_text = "x" * 500
    with _patch_document_init(), patch.object(AssistantFeedback, "insert", new=_fake_insert()):
        result = await feedback_service.submit_assistant_feedback(USER_ID, long_text, "unhelpful")
    assert len(result.message_snippet) == 300


@pytest.mark.asyncio
async def test_submit_assistant_feedback_rejects_invalid_value():
    with pytest.raises(BusinessRuleError):
        await feedback_service.submit_assistant_feedback(USER_ID, "text", "not_a_real_value")


# ─── get_satisfaction_summary ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_satisfaction_summary_combines_both_sources():
    chat_docs = [
        _feedback_doc(UserFeedback.HELPFUL),
        _feedback_doc(UserFeedback.HELPFUL),
        _feedback_doc(UserFeedback.UNHELPFUL),
    ]
    rec_docs = [
        _recommendation_doc(UserFeedback.HELPFUL),
        _recommendation_doc(UserFeedback.IRRELEVANT),
    ]

    chat_query = MagicMock()
    chat_query.to_list = AsyncMock(return_value=chat_docs)
    rec_query = MagicMock()
    rec_query.to_list = AsyncMock(return_value=rec_docs)

    with patch.object(AssistantFeedback, "find_all", return_value=chat_query), \
         patch("services.feedback_service.Recommendation.find", return_value=rec_query):
        summary = await feedback_service.get_satisfaction_summary()

    assert summary.assistant_chat.helpful == 2
    assert summary.assistant_chat.unhelpful == 1
    assert summary.assistant_chat.total == 3
    assert summary.assistant_chat.satisfaction_pct == pytest.approx(66.67, abs=0.01)

    assert summary.recommendations.helpful == 1
    assert summary.recommendations.irrelevant == 1
    assert summary.recommendations.total == 2

    assert summary.total_responses == 5
    # 3 helpful out of 5 total
    assert summary.overall_satisfaction_pct == pytest.approx(60.0, abs=0.01)


@pytest.mark.asyncio
async def test_satisfaction_summary_handles_no_data_without_crashing():
    empty_query = MagicMock()
    empty_query.to_list = AsyncMock(return_value=[])

    with patch.object(AssistantFeedback, "find_all", return_value=empty_query), \
         patch("services.feedback_service.Recommendation.find", return_value=empty_query):
        summary = await feedback_service.get_satisfaction_summary()

    assert summary.total_responses == 0
    assert summary.overall_satisfaction_pct == 0.0
    assert summary.assistant_chat.total == 0
    assert summary.recommendations.total == 0
