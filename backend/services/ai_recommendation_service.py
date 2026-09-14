"""
services/ai_recommendation_service.py — LLM-written recommendations for the
Habits and Study pages, grounded in the user's own figures.

WHAT REPLACED WHAT
Both pages previously built their advice from string templates over threshold
comparisons: a metric scored under 70 produced "Exercise: avg 14.33 minutes.
Target is 30+ minutes/day." Deterministic and honest, but it could only restate
the number it had just measured — it could not relate two metrics to each other,
notice that the habit gap and the study slump began the same week, or say what to
do differently. That is what an LLM is actually good for here.

GROUNDING, NOT DATABASE ACCESS
The model is never given query access. Every call is handed a compact snapshot
built by the existing analytics engines — the same numbers the page itself
renders — and is told to work only from those. This matters for two reasons: an
LLM improvising SQL/Mongo against a user's records is both a security problem and
an accuracy one, and grounding on the engines guarantees the advice cannot
contradict the charts sitting next to it.

GENERATION IS EXPLICIT
Loading a page never calls a provider. A page load reads the stored set and
nothing else; a model runs only when the user asks for one. That makes the cost
of this feature something the user chooses to spend rather than something a
refresh spends for them, and it means a slow provider can never delay a page.

A stored set is returned even once it goes stale — expired by TTL, or written
against figures that have since moved — flagged rather than discarded. Advice
written last week about data that has changed is still worth reading, as long as
the reader is told which it is. Withholding it would leave an empty panel and no
way to tell an unused feature from a broken one.

FAILURE IS NOT SILENT
If no provider is configured, or every provider call fails, this falls back to the
old rule-based lines and says so via `provider="rules"`. The frontend labels the
panel accordingly. What it must never do is emit generic filler that reads like
personalised advice.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from beanie import PydanticObjectId

from core.config import get_settings
from models.ai_recommendation import AIRecommendation
from models.enums import RecommendationDomain
from models.user import User

logger = logging.getLogger("digital_twin_ai.ai_recommendations")

# How long a set survives when the underlying figures have not moved. Short
# enough that a stalled user eventually gets re-prompted, long enough that
# ordinary navigation costs nothing.
CACHE_TTL = timedelta(hours=12)

MAX_ITEMS = 5
MIN_ITEMS = 3

GROQ_MODEL = "openai/gpt-oss-20b"

# gpt-oss is a reasoning model: its internal reasoning tokens are billed against
# max_tokens before a single character of the answer is emitted. At 600 this
# returned an empty string with finish_reason="stop" — not an error, not a refusal,
# just nothing, which is indistinguishable from a provider outage at the call site.
# A real run of this prompt spends ~440 completion tokens, so the ceiling has to
# clear the reasoning as well as the reply.
GROQ_MAX_TOKENS = 2000

SYSTEM_PREAMBLE = (
    "You are a personal analytics coach inside a self-tracking app. You are given a "
    "snapshot of one user's real, measured data.\n\n"
    "Write {min_items}-{max_items} recommendations. Rules:\n"
    "- Use ONLY the figures in the snapshot. Never invent a number, a date, a subject "
    "or a habit that is not there.\n"
    "- Cite the actual figure in the recommendation so the user can see where it came from.\n"
    "- Prefer connecting two facts over restating one. The user can already see each "
    "number on its own; what they cannot see is the relationship between them.\n"
    "- Lead with the most consequential thing, not the easiest.\n"
    "- One sentence each, second person, no markdown, no numbering, no preamble.\n"
    "- If the snapshot is too thin to say anything specific, say that plainly instead "
    "of padding with generic advice.\n\n"
    'Reply with a JSON array of strings and nothing else, e.g. ["...", "..."]'
)


# ─── Grounding snapshots ─────────────────────────────────────────────────────
# Plain dicts, deliberately small. Every value here is already computed and
# already rendered on the page the recommendations appear on.

def build_habit_snapshot(summary, goals: list) -> dict:
    """From habit_analytics_service's summary response."""
    return {
        "window_days": summary.consistency_score.window_days,
        "days_logged": summary.consistency_score.logged_days,
        "consistency_pct": summary.consistency_score.consistency_score,
        "current_streak_days": summary.habit_streak.current_streak,
        "longest_streak_days": summary.habit_streak.longest_streak,
        "streak_active": summary.habit_streak.streak_active,
        "days_missed": summary.missed_habits.missed_days,
        "on_target": [
            {"habit": h.habit, "average": h.average_value, "unit": h.unit, "target": h.detail}
            for h in summary.positive_habits.habits
        ],
        "off_target": [
            {"habit": h.habit, "average": h.average_value, "unit": h.unit, "target": h.detail}
            for h in summary.negative_habits.habits
        ],
        "goals": [
            {"title": g.title, "progress": f"{g.current_value}/{g.target_value} {g.unit}"}
            for g in goals[:3]
        ],
    }


def build_study_snapshot(productivity, subjects: list, goals: list) -> dict:
    """From productivity_service's summary plus study_service's per-subject rollup."""
    return {
        "productivity_score": productivity.productivity_score.productivity_score,
        "focus_score": productivity.focus_score.focus_score,
        "focus_source": productivity.focus_score.method_used.value,
        "days_studied_pct": productivity.completion_percentage.completion_percentage,
        "window_days": productivity.completion_percentage.window_days,
        "subjects": [
            {
                "subject": s.subject,
                "hours": float(s.total_study_hours),
                "sessions": s.session_count,
                "avg_exam_pct": s.average_exam_pct,
                "avg_quiz_pct": s.average_quiz_pct,
                "days_since_studied": (
                    (datetime.now(timezone.utc) - s.last_session_date).days
                    if s.last_session_date else None
                ),
            }
            for s in subjects[:8]
        ],
        "goals": [
            {"title": g.title, "progress": f"{g.current_value}/{g.target_value} {g.unit}"}
            for g in goals[:3]
        ],
    }


def _hash_snapshot(snapshot: dict) -> str:
    """Digest of the exact figures shown to the model. Stable key ordering, so an
    unchanged snapshot always hashes the same and reuses the cached set."""
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, default=str).encode()
    ).hexdigest()


# ─── Provider calls ──────────────────────────────────────────────────────────

async def _call_groq(prompt: str, api_key: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=GROQ_MAX_TOKENS,
        temperature=0.4,  # low: this is analysis of fixed figures, not brainstorming
    )
    return (response.choices[0].message.content or "").strip()


async def _call_gemini(prompt: str, api_key: str) -> str:
    import google.generativeai as genai

    def _generate() -> str:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        return (model.generate_content(prompt).text or "").strip()

    # The google-generativeai client is synchronous — keep it off the event loop.
    return await asyncio.to_thread(_generate)


def _parse_items(raw: str) -> list[str]:
    """Pulls the JSON array out of a reply. Models wrap arrays in prose or fences
    often enough that a bare json.loads is not a safe parser here; a failed parse
    must return nothing so the caller falls back rather than rendering debris."""
    if not raw:
        return []

    candidate = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()

    if not candidate.startswith("["):
        bracketed = re.search(r"\[.*\]", candidate, re.DOTALL)
        candidate = bracketed.group(0) if bracketed else ""

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse recommendation JSON from provider reply.")
        return []

    if not isinstance(parsed, list):
        return []

    items = [str(i).strip() for i in parsed if isinstance(i, (str, int, float)) and str(i).strip()]
    return items[:MAX_ITEMS]


async def _generate(snapshot: dict, domain_label: str) -> tuple[list[str], str]:
    """Returns (items, provider). Empty list means every provider failed."""
    settings = get_settings()
    prompt = (
        SYSTEM_PREAMBLE.format(min_items=MIN_ITEMS, max_items=MAX_ITEMS)
        + f"\n\nDomain: {domain_label}\nSnapshot:\n{json.dumps(snapshot, indent=1, default=str)}"
    )

    # Groq first here, unlike the chat assistant: these are short structured
    # replies on a free tier that tolerates them, and it keeps the page fast.
    providers = [("groq", settings.GROQ_API_KEY, _call_groq),
                 ("gemini", settings.GEMINI_API_KEY, _call_gemini)]

    for name, key, call in providers:
        if not key:
            logger.info("%s not configured for recommendations; skipping.", name)
            continue
        try:
            items = _parse_items(await call(prompt, key))
            if items:
                return items, name
            logger.warning("%s returned no usable recommendations.", name)
        except Exception:
            logger.exception("%s recommendation call failed.", name)

    return [], ""


# ─── Cache + orchestration ───────────────────────────────────────────────────

async def _cached(user_id: PydanticObjectId, domain: RecommendationDomain,
                  context_hash: str) -> tuple[Optional[AIRecommendation], bool]:
    """Returns (record, is_stale). A stale record is still handed back — the
    caller decides whether to show it — because the alternative is an empty panel
    that looks broken. Stale means one of two things: the figures the set was
    written from have since moved, or it has simply aged past the TTL."""
    record = await AIRecommendation.find_one(
        AIRecommendation.user_id == user_id, AIRecommendation.domain == domain
    )
    if not record:
        return None, False

    if record.context_hash != context_hash:
        return record, True

    generated = record.generated_at
    if generated.tzinfo is None:  # documents written before tz-aware defaults
        generated = generated.replace(tzinfo=timezone.utc)
    expired = datetime.now(timezone.utc) - generated > CACHE_TTL

    return record, expired


async def _store(user_id: PydanticObjectId, domain: RecommendationDomain,
                 items: list[str], provider: str, context_hash: str) -> datetime:
    now = datetime.now(timezone.utc)
    await AIRecommendation.get_motor_collection().update_one(
        {"user_id": user_id, "domain": domain.value},
        {"$set": {"items": items, "provider": provider,
                  "context_hash": context_hash, "generated_at": now}},
        upsert=True,
    )
    return now


@dataclass
class RecommendationResult:
    items: list[str]
    provider: str          # "groq" / "gemini" / "rules"
    generated_at: datetime
    cached: bool
    stale: bool


async def get_recommendations(
    user: User,
    domain: RecommendationDomain,
    snapshot: dict,
    fallback_items: list[str],
    generate: bool = False,
) -> RecommendationResult:
    """Reads the stored set. Reaches a provider only when `generate` is true.

    `fallback_items` are the deterministic rule-based lines. They stand in when
    nothing has been generated yet, and when a requested generation fails — always
    reported as provider="rules", so the UI never presents them as model output.
    """
    context_hash = _hash_snapshot(snapshot)
    user_id = user.id
    record, is_stale = await _cached(user_id, domain, context_hash)

    if not generate:
        if record:
            return RecommendationResult(
                items=record.items, provider=record.provider,
                generated_at=record.generated_at, cached=True, stale=is_stale,
            )
        # Nothing generated yet. The threshold lines cost nothing and say
        # something true, which beats an empty panel the user cannot read as
        # either "not used yet" or "broken".
        return RecommendationResult(
            items=fallback_items, provider="rules",
            generated_at=datetime.now(timezone.utc), cached=False, stale=False,
        )

    items, provider = await _generate(snapshot, domain.value.lower())

    if not items:
        # Deliberately not stored: a provider failure must not overwrite a good
        # set, nor persist as though it were one.
        return RecommendationResult(
            items=record.items if record else fallback_items,
            provider=record.provider if record else "rules",
            generated_at=record.generated_at if record else datetime.now(timezone.utc),
            cached=bool(record), stale=is_stale if record else False,
        )

    generated_at = await _store(user_id, domain, items, provider, context_hash)
    return RecommendationResult(
        items=items, provider=provider, generated_at=generated_at,
        cached=False, stale=False,
    )


# ─── Deterministic fallback ──────────────────────────────────────────────────
# The rule-based lines the two pages used to build client-side. They now live
# here so there is one source of truth: whatever the API returns is what renders,
# whether a model wrote it or these did.

def rule_based_habit_items(summary) -> list[str]:
    streak = summary.habit_streak
    items = [
        f"Current streak: {streak.current_streak} "
        f"day{'' if streak.current_streak == 1 else 's'} (longest: {streak.longest_streak})."
    ]

    if summary.missed_habits.missed_days > 0:
        items.append(
            f"Missed logging on {summary.missed_habits.missed_days} of the last "
            f"{summary.missed_habits.window_days} days."
        )

    items += [
        f"{h.habit.replace('_', ' ').capitalize()}: avg {h.average_value} {h.unit}. {h.detail}"
        for h in summary.negative_habits.habits
    ]
    items += [
        f"{h.habit.replace('_', ' ').capitalize()} is on track — avg {h.average_value} {h.unit}."
        for h in summary.positive_habits.habits
    ]
    return items[:6]


def rule_based_study_items(productivity, subjects: list) -> list[str]:
    focus = productivity.focus_score
    items = [
        f"Current productivity score: {round(productivity.productivity_score.productivity_score)}%.",
        (
            f"Focus score: {round(focus.focus_score)}% (based on logged focus ratings)."
            if focus.method_used.value == "recorded_average"
            else "Focus score: not enough data — rate a session's focus to see this."
        ),
        f"Studied {round(productivity.completion_percentage.completion_percentage)}% of days "
        f"in the last {productivity.completion_percentage.window_days} days.",
    ]

    if subjects:
        busiest = max(subjects, key=lambda s: float(s.total_study_hours))
        items.append(
            f"{busiest.subject} takes the most of your time — "
            f"{float(busiest.total_study_hours):.1f} hours across {busiest.session_count} sessions."
        )

    return items[:6]
