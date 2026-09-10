"""
services/ai_assistant_service.py — Grounded AI assistant with provider fallback.
Gemini is the primary provider; Groq (an OpenAI-compatible API, called via the
`openai` client pointed at Groq's base_url — no OpenAI account involved) is the
fallback if Gemini is unconfigured or a call to it fails.

Grounding: rather than recomputing digital_twin_state live (what
user_service.get_twin_context does for GET /users/me, which is expensive — several
analytics-engine calls — and appropriate there but wasteful on every chat turn),
this reads the already-loaded User document's cached profile/active_goals/
digital_twin_state directly. GET /users/me already keeps that snapshot reasonably
fresh (the frontend calls it on every app load), so no extra recompute is needed
here — matches the "engines compose, don't reimplement" convention without paying
for a live recompute per message.
"""
import logging

from core.config import get_settings
from core.exceptions import AIProviderUnavailableError
from models.user import User

logger = logging.getLogger("digital_twin_ai.ai_assistant")

SYSTEM_PREAMBLE = (
    "You are the Digital Twin AI assistant — a friendly, concise personal finance, "
    "study, and habit coach. Answer the user's question directly using the context "
    "below when relevant. Keep replies short (a few sentences, plain text, no "
    "markdown headers) and actionable. If the context doesn't cover what they're "
    "asking, say so plainly rather than guessing."
)


def _build_context(user: User) -> str:
    profile = user.profile
    twin = user.digital_twin_state
    goals = user.active_goals[:5]  # cap — keep the prompt small

    goal_lines = "\n".join(
        f"- {g.title} ({g.category.value}): {g.current_value}/{g.target_value} {g.unit}"
        for g in goals
    ) or "- No active goals set."

    return (
        f"User: {profile.name}, age {profile.age}, risk tolerance {profile.risk_tolerance.value}.\n"
        f"Digital twin snapshot: savings rate {twin.savings_rate_pct}%, "
        f"emergency fund {twin.emergency_fund_months} months, "
        f"study consistency {twin.study_consistency_score}%, "
        f"habit completion {twin.habit_completion_rate}%, "
        f"lifestyle score {twin.lifestyle_score}/100, "
        f"productivity score {twin.productivity_score}/100.\n"
        f"Active goals:\n{goal_lines}"
    )


async def _call_gemini(prompt: str, api_key: str) -> str:
    import asyncio

    import google.generativeai as genai

    def _generate() -> str:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return (response.text or "").strip()

    # The google-generativeai client is synchronous — run it off the event loop
    # rather than blocking every other request while it waits on the network.
    return await asyncio.to_thread(_generate)


async def _call_groq(prompt: str, api_key: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    response = await client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        # gpt-oss is a reasoning model and spends its reasoning tokens out of this
        # same budget before emitting any of the reply. At 500 a question needing
        # any thought came back as an empty string with finish_reason="stop" —
        # silent, and indistinguishable from an outage at the call site.
        max_tokens=2000,
    )
    return (response.choices[0].message.content or "").strip()


async def get_assistant_reply(user: User, message: str) -> tuple[str, str]:
    """Returns (reply, provider_used). Tries Gemini first, falls back to Groq,
    raises AIProviderUnavailableError if both fail or neither is configured."""
    settings = get_settings()
    prompt = f"{SYSTEM_PREAMBLE}\n\n{_build_context(user)}\n\nUser question: {message}"

    if settings.GEMINI_API_KEY:
        try:
            reply = await _call_gemini(prompt, settings.GEMINI_API_KEY)
            if reply:
                return reply, "gemini"
        except Exception:
            logger.exception("Gemini call failed; falling back to Groq.")
    else:
        logger.info("GEMINI_API_KEY not configured; skipping to Groq fallback.")

    if settings.GROQ_API_KEY:
        try:
            reply = await _call_groq(prompt, settings.GROQ_API_KEY)
            if reply:
                return reply, "groq"
        except Exception:
            logger.exception("Groq fallback call also failed.")
    else:
        logger.info("GROQ_API_KEY not configured; no fallback available.")

    raise AIProviderUnavailableError()
