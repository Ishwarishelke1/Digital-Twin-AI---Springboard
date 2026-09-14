"""
services/ai_assistant_service.py — Grounded AI assistant with provider fallback.
Gemini is the primary provider; Groq (an OpenAI-compatible API, called via the
`openai` client pointed at Groq's base_url — no OpenAI account involved) is the
fallback if Gemini is unconfigured or a call to it fails.

Grounding: `build_assistant_context` composes the *public* async methods of
every analytics engine (finance, study, habit, forecast, simulation, plus the
live digital-twin recompute) via asyncio.gather — same "engines compose, they
don't reimplement" convention as trend_prediction_service/simulation_service
(see CLAUDE.md). Earlier this read only the User document's cached
profile/active_goals/digital_twin_state — accurate for profile and goals, but
blind to finance, study, habits, forecasts and what-if history, and stale
whenever digital_twin_state hadn't been refreshed by a recent GET /users/me.
That meant the assistant could not answer "how much did I spend on food" or
"what did my savings what-if say" at all, and for a brand-new user it answered
from zeros even after they'd logged real data elsewhere in the app. Composing
the engines directly costs several DB round-trips per chat turn, gathered in
parallel — a deliberate cost, since a wrong or blind answer costs more than the
extra latency; /assistant/chat is already rate-limited to 15/min for exactly
this kind of cost reasoning.

Every domain's contribution is a compact SUMMARY (totals/averages/top-N/
recent-N), never a raw dump — the "prompt must stay small" constraint the
original [:5]-goals cap existed for. A domain with no data says so explicitly
("No transactions logged yet.") rather than being omitted, so the model can
tell the user honestly that it doesn't know instead of inventing a figure —
same refusal principle goal_completion_service documents for its own gates.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from core.config import get_settings
from core.exceptions import AIProviderUnavailableError
from models.user import User

logger = logging.getLogger("digital_twin_ai.ai_assistant")

SYSTEM_PREAMBLE = (
    "You are the Digital Twin AI assistant — a friendly, concise personal finance, "
    "study, and habit coach. Answer the user's question directly using the context "
    "below when relevant. Keep replies short (a few sentences, plain text, no "
    "markdown headers) and actionable. If the context doesn't cover what they're "
    "asking, say so plainly rather than guessing. If a section below says there is "
    "no data yet, tell the user that honestly instead of making up a number."
)

CONTEXT_LOOKBACK_DAYS = 90  # recent-history window for finance/study aggregates
MAX_HISTORY_TURNS = 6       # bounded multi-turn memory sent back to the model


def _profile_and_goals_block(user: User) -> str:
    profile = user.profile
    twin = user.digital_twin_state
    goals = user.active_goals

    goal_lines = "\n".join(
        f"- {g.title} ({g.category.value}): {g.current_value}/{g.target_value} {g.unit}"
        + (" [completed]" if g.completed_at else "")
        for g in goals
    ) or "- No active goals set."

    return (
        f"User: {profile.name}, age {profile.age}, risk tolerance {profile.risk_tolerance.value}.\n"
        f"Digital twin snapshot (live): savings rate {twin.savings_rate_pct}%, "
        f"emergency fund {twin.emergency_fund_months} months, "
        f"study consistency {twin.study_consistency_score}%, "
        f"habit completion {twin.habit_completion_rate}%, "
        f"lifestyle score {twin.lifestyle_score}/100, "
        f"productivity score {twin.productivity_score}/100.\n"
        f"Active goals ({len(goals)} total):\n{goal_lines}"
    )


def _finance_block(cashflow, category_breakdown) -> str:
    from models.enums import TransactionType

    if not cashflow:
        return "Finance (last 90 days): no transactions logged yet."

    income = sum(float(i.total_amount) for i in cashflow if i.type == TransactionType.INCOME)
    expense = sum(float(i.total_amount) for i in cashflow if i.type == TransactionType.EXPENSE)
    top_categories = sorted(category_breakdown, key=lambda c: c.total_amount, reverse=True)[:5]
    cat_lines = "\n".join(
        f"  - {c.category}: {c.total_amount} ({c.percentage_of_total:.1f}% of spending)"
        for c in top_categories
    ) or "  - No categorized spending yet."

    return (
        f"Finance (last 90 days): total income {income:.2f}, total expenses {expense:.2f}, "
        f"net {income - expense:.2f}.\n"
        f"Top spending categories:\n{cat_lines}"
    )


def _study_block(subjects) -> str:
    if not subjects:
        return "Study: no study sessions logged yet."
    top = sorted(subjects, key=lambda s: s.total_study_hours, reverse=True)[:5]
    lines = "\n".join(
        f"  - {s.subject}: {s.total_study_hours}h across {s.session_count} session(s)"
        + (f", avg quiz {s.average_quiz_pct:.1f}%" if s.average_quiz_pct is not None else "")
        + (f", avg exam {s.average_exam_pct:.1f}%" if s.average_exam_pct is not None else "")
        for s in top
    )
    return f"Study, by subject:\n{lines}"


def _habits_block(summary) -> str:
    cs = summary.consistency_score
    streak = summary.habit_streak
    if cs.logged_days == 0:
        return "Habits: no habit logs yet."
    positive = ", ".join(h.habit for h in summary.positive_habits.habits[:3]) or "none flagged"
    negative = ", ".join(h.habit for h in summary.negative_habits.habits[:3]) or "none flagged"
    return (
        f"Habits: consistency {cs.consistency_score:.1f}% ({cs.logged_days}/{cs.window_days} days logged), "
        f"current streak {streak.current_streak} day(s) (longest {streak.longest_streak}), "
        f"missed {summary.missed_habits.missed_days} day(s) in the last {summary.missed_habits.window_days}.\n"
        f"Positive patterns: {positive}. Negative patterns: {negative}."
    )


def _forecast_block(savings_forecast, income_forecast) -> str:
    if savings_forecast.method_used.value == "insufficient_data":
        return "Forecasts: not enough history yet to project savings or income."
    next_savings = savings_forecast.projections[0].projected_amount if savings_forecast.projections else None
    next_income = income_forecast.projections[0].projected_amount if income_forecast.projections else None
    return (
        f"Forecast (method: {savings_forecast.method_used.value}): "
        f"next month's projected savings {next_savings}, projected income {next_income}."
    )


def _simulation_block(history) -> str:
    if not history:
        return "What-if simulations: none run yet."
    lines = "\n".join(
        f"  - {h.domain.value}: \"{h.top_scenario_name}\" ({h.created_at.date()})"
        for h in history[:5]
    )
    return f"Recent what-if simulations:\n{lines}"


async def build_assistant_context(user: User) -> str:
    """Gathers a live, compact digest across every data domain the user owns —
    profile, finance, study, habits, forecasts, and what-if simulation history —
    via the existing public engine methods, in parallel. Exported (not private)
    so tests can assert on the composed context directly, without spending an
    LLM call to check grounding."""
    import services.finance_service as finance_service
    import services.study_service as study_service
    import services.simulation_service as simulation_service_module
    import services.user_service as user_service
    from services.forecast_service import forecast_service
    from services.habit_analytics_service import habit_analytics_service

    user_id = str(user.id)
    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=CONTEXT_LOOKBACK_DAYS)

    (
        fresh_user,
        cashflow,
        category_breakdown,
        subjects,
        habit_summary,
        savings_forecast,
        income_forecast,
        sim_history,
    ) = await asyncio.gather(
        user_service.get_twin_context(user_id),
        finance_service.get_monthly_cashflow(user_id, lookback_start, now),
        finance_service.get_category_breakdown(user_id, lookback_start, now),
        study_service.get_subject_performance(user_id, start_date=lookback_start),
        habit_analytics_service.get_summary(user_id),
        forecast_service.forecast_monthly_savings(user_id, months_ahead=1),
        forecast_service.project_income(user_id, months_ahead=1),
        simulation_service_module.simulation_service.get_simulation_history(user_id, limit=5),
        return_exceptions=True,
    )

    # Any one engine failing (e.g. a transient DB hiccup) must not take down the
    # whole chat turn — degrade that section to "unavailable" and keep going.
    def _ok(value, fallback):
        return fallback if isinstance(value, Exception) else value

    if isinstance(fresh_user, Exception):
        logger.warning("get_twin_context failed while building assistant context: %s", fresh_user)
        fresh_user = user

    blocks = [
        _profile_and_goals_block(fresh_user),
        _finance_block(_ok(cashflow, []), _ok(category_breakdown, [])),
        _study_block(_ok(subjects, [])),
        "Habits: analytics unavailable right now." if isinstance(habit_summary, Exception) else _habits_block(habit_summary),
        "Forecasts: unavailable right now." if isinstance(savings_forecast, Exception) or isinstance(income_forecast, Exception)
            else _forecast_block(savings_forecast, income_forecast),
        _simulation_block(_ok(sim_history, [])),
    ]
    return "\n\n".join(blocks)


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


def _format_history(history: list[dict] | None) -> str:
    """Bounded, client-held multi-turn memory — transcripts are deliberately not
    persisted server-side (see api/v1/assistant.py's module docstring), so this
    is the only place conversational continuity comes from: the last few turns
    the caller sends back on each request."""
    if not history:
        return ""
    trimmed = history[-MAX_HISTORY_TURNS:]
    lines = "\n".join(
        f"{'User' if turn.get('sender') == 'user' else 'Assistant'}: {turn.get('text', '')}"
        for turn in trimmed
        if turn.get("text")
    )
    return f"\n\nPrevious conversation:\n{lines}" if lines else ""


async def get_assistant_reply(
    user: User, message: str, history: list[dict] | None = None
) -> tuple[str, str]:
    """Returns (reply, provider_used). Tries Gemini first, falls back to Groq,
    raises AIProviderUnavailableError if both fail or neither is configured."""
    settings = get_settings()
    context = await build_assistant_context(user)
    prompt = (
        f"{SYSTEM_PREAMBLE}\n\n{context}{_format_history(history)}\n\nUser question: {message}"
    )

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
