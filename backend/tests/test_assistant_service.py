"""
tests/test_assistant_service.py — Unit tests for services/ai_assistant_service.py.
No network calls — _call_gemini/_call_groq, get_settings and
build_assistant_context are mocked directly for the provider-fallback tests.
The context-block builders (_profile_and_goals_block, _finance_block, etc.)
are pure functions over already-fetched data, so they're tested directly with
constructed fake response objects, without needing a database.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.exceptions import AIProviderUnavailableError
from models.enums import GoalCategory, RiskTolerance
from models.user import Profile, User
from services import ai_assistant_service


def _user() -> User:
    return User.model_construct(
        email="assistant-test@example.com",
        password_hash="x",
        profile=Profile(name="Test User", age=25, risk_tolerance=RiskTolerance.MODERATE),
        active_goals=[],
    )


def _settings(gemini: str = None, groq: str = None):
    return SimpleNamespace(GEMINI_API_KEY=gemini, GROQ_API_KEY=groq)


@pytest.mark.asyncio
async def test_gemini_success_returns_gemini_reply():
    with patch.object(ai_assistant_service, "get_settings", return_value=_settings(gemini="k1", groq="k2")), \
         patch.object(ai_assistant_service, "build_assistant_context", new=AsyncMock(return_value="ctx")), \
         patch.object(ai_assistant_service, "_call_gemini", new=AsyncMock(return_value="hi from gemini")), \
         patch.object(ai_assistant_service, "_call_groq", new=AsyncMock(return_value="hi from groq")) as groq_mock:
        reply, provider = await ai_assistant_service.get_assistant_reply(_user(), "hello")

    assert reply == "hi from gemini"
    assert provider == "gemini"
    groq_mock.assert_not_called()


@pytest.mark.asyncio
async def test_gemini_failure_falls_back_to_groq():
    with patch.object(ai_assistant_service, "get_settings", return_value=_settings(gemini="k1", groq="k2")), \
         patch.object(ai_assistant_service, "build_assistant_context", new=AsyncMock(return_value="ctx")), \
         patch.object(ai_assistant_service, "_call_gemini", new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch.object(ai_assistant_service, "_call_groq", new=AsyncMock(return_value="hi from groq")):
        reply, provider = await ai_assistant_service.get_assistant_reply(_user(), "hello")

    assert reply == "hi from groq"
    assert provider == "groq"


@pytest.mark.asyncio
async def test_gemini_unconfigured_goes_straight_to_groq():
    with patch.object(ai_assistant_service, "get_settings", return_value=_settings(gemini=None, groq="k2")), \
         patch.object(ai_assistant_service, "build_assistant_context", new=AsyncMock(return_value="ctx")), \
         patch.object(ai_assistant_service, "_call_gemini", new=AsyncMock()) as gemini_mock, \
         patch.object(ai_assistant_service, "_call_groq", new=AsyncMock(return_value="hi from groq")):
        reply, provider = await ai_assistant_service.get_assistant_reply(_user(), "hello")

    assert reply == "hi from groq"
    assert provider == "groq"
    gemini_mock.assert_not_called()


@pytest.mark.asyncio
async def test_both_providers_fail_raises_ai_provider_unavailable():
    with patch.object(ai_assistant_service, "get_settings", return_value=_settings(gemini="k1", groq="k2")), \
         patch.object(ai_assistant_service, "build_assistant_context", new=AsyncMock(return_value="ctx")), \
         patch.object(ai_assistant_service, "_call_gemini", new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch.object(ai_assistant_service, "_call_groq", new=AsyncMock(side_effect=RuntimeError("boom too"))):
        with pytest.raises(AIProviderUnavailableError):
            await ai_assistant_service.get_assistant_reply(_user(), "hello")


@pytest.mark.asyncio
async def test_neither_provider_configured_raises_ai_provider_unavailable():
    with patch.object(ai_assistant_service, "get_settings", return_value=_settings(gemini=None, groq=None)), \
         patch.object(ai_assistant_service, "build_assistant_context", new=AsyncMock(return_value="ctx")):
        with pytest.raises(AIProviderUnavailableError):
            await ai_assistant_service.get_assistant_reply(_user(), "hello")


@pytest.mark.asyncio
async def test_history_is_included_in_the_prompt_and_trimmed():
    """Only the last MAX_HISTORY_TURNS turns should reach the model — bounded
    client-held multi-turn memory, per ChatRequest.history."""
    captured = {}

    async def _capture_gemini(prompt, api_key):
        captured["prompt"] = prompt
        return "ok"

    history = [{"sender": "user", "text": f"turn {i}"} for i in range(10)]
    with patch.object(ai_assistant_service, "get_settings", return_value=_settings(gemini="k1")), \
         patch.object(ai_assistant_service, "build_assistant_context", new=AsyncMock(return_value="ctx")), \
         patch.object(ai_assistant_service, "_call_gemini", new=_capture_gemini):
        await ai_assistant_service.get_assistant_reply(_user(), "hello", history=history)

    assert "turn 9" in captured["prompt"]
    assert "turn 0" not in captured["prompt"], "history must be trimmed to the last MAX_HISTORY_TURNS"


# ─── Context block builders (pure functions, no DB) ────────────────────────────

def test_profile_and_goals_block_includes_goal_and_twin_state():
    user = _user()
    user.active_goals = [
        type("G", (), {
            "title": "Emergency Fund", "category": GoalCategory.FINANCE,
            "current_value": 3000, "target_value": 15000, "unit": "USD",
            "completed_at": None,
        })()
    ]
    block = ai_assistant_service._profile_and_goals_block(user)
    assert "Test User" in block
    assert "Emergency Fund" in block
    assert "savings rate" in block


def test_finance_block_empty_says_no_transactions():
    block = ai_assistant_service._finance_block([], [])
    assert "no transactions" in block.lower()


def test_finance_block_summarizes_income_expense_and_categories():
    from models.enums import TransactionType
    cashflow = [
        SimpleNamespace(type=TransactionType.INCOME, total_amount=50000),
        SimpleNamespace(type=TransactionType.EXPENSE, total_amount=20000),
    ]
    categories = [SimpleNamespace(category="FOOD", total_amount=8000, percentage_of_total=40.0)]
    block = ai_assistant_service._finance_block(cashflow, categories)
    assert "50000" in block
    assert "FOOD" in block


def test_study_block_empty_says_no_sessions():
    block = ai_assistant_service._study_block([])
    assert "no study sessions" in block.lower()


def test_habits_block_empty_says_no_logs():
    summary = SimpleNamespace(
        consistency_score=SimpleNamespace(logged_days=0, consistency_score=0, window_days=30),
        habit_streak=SimpleNamespace(current_streak=0, longest_streak=0),
        positive_habits=SimpleNamespace(habits=[]),
        negative_habits=SimpleNamespace(habits=[]),
        missed_habits=SimpleNamespace(missed_days=0, window_days=30),
    )
    block = ai_assistant_service._habits_block(summary)
    assert "no habit logs" in block.lower()


def test_simulation_block_empty_says_none_run():
    block = ai_assistant_service._simulation_block([])
    assert "none run yet" in block.lower()
