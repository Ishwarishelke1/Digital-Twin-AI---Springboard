"""
tests/test_ai_recommendation_service.py — Covers the parts of the recommendation
path that fail quietly rather than loudly.

Two things here are worth guarding. The reply parser, because a model that wraps
its JSON in prose or a code fence must not take the panel down — and, more
importantly, a reply it cannot understand must yield nothing so the caller falls
back, never a half-parsed fragment rendered as advice. And the cache key, because
it is the only thing standing between an LLM call and every page load.

Zero DB, per conftest: the Mongo read/write are mocked individually.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

import services.ai_recommendation_service as svc
from models.enums import RecommendationDomain

USER = SimpleNamespace(id=PydanticObjectId())


# ─── reply parsing ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ('["a", "b"]', ["a", "b"]),
    ('```json\n["a", "b"]\n```', ["a", "b"]),
    ('```\n["a"]\n```', ["a"]),
    ('Here you go:\n["a", "b"]\nHope that helps!', ["a", "b"]),
    ('  ["a"]  ', ["a"]),
    # A model told to return an array sometimes wraps it in an object anyway.
    # Recovering the array is the right outcome, not a leniency bug.
    ('{"items": ["a", "b"]}', ["a", "b"]),
])
def test_parse_items_handles_the_shapes_models_actually_return(raw, expected):
    assert svc._parse_items(raw) == expected


@pytest.mark.parametrize("raw", [
    "",                      # the empty reply a reasoning model gives when it runs out of tokens
    "   ",
    "Sorry, I can't help with that.",
    '["a", ',                # truncated mid-array
    "null",
])
def test_parse_items_returns_nothing_it_cannot_fully_parse(raw):
    """Nothing is the signal to fall back. A partial parse rendered as advice
    would be worse than the deterministic lines it replaced."""
    assert svc._parse_items(raw) == []


def test_parse_items_drops_blanks_and_caps_the_count():
    raw = '["a", "", "   ", "b", "c", "d", "e", "f", "g"]'
    items = svc._parse_items(raw)
    assert "" not in items and all(i.strip() for i in items)
    assert len(items) == svc.MAX_ITEMS


def test_parse_items_keeps_numbers_a_model_emits_unquoted():
    assert svc._parse_items('["a", 42]') == ["a", "42"]


# ─── cache key ───────────────────────────────────────────────────────────────

def test_hash_is_stable_across_key_order():
    """The snapshot is built fresh per request, so dict ordering must not decide
    whether the cache hits — otherwise every load looks like changed data."""
    assert svc._hash_snapshot({"a": 1, "b": 2}) == svc._hash_snapshot({"b": 2, "a": 1})


def test_hash_moves_when_any_figure_moves():
    assert svc._hash_snapshot({"days_logged": 15}) != svc._hash_snapshot({"days_logged": 16})


def test_hash_survives_values_json_cannot_encode():
    """Snapshots carry datetimes and Decimals straight off the engines."""
    snapshot = {"when": datetime(2026, 9, 8, tzinfo=timezone.utc)}
    assert len(svc._hash_snapshot(snapshot)) == 64


# ─── cache freshness ─────────────────────────────────────────────────────────

def _record(context_hash="abc", age=timedelta(minutes=5)):
    return SimpleNamespace(
        items=["cached line"], provider="groq", context_hash=context_hash,
        generated_at=datetime.now(timezone.utc) - age,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("record,wanted,found,stale", [
    (_record(), "abc", True, False),
    (_record(context_hash="moved"), "abc", True, True),                  # figures changed
    (_record(age=svc.CACHE_TTL + timedelta(minutes=1)), "abc", True, True),  # aged out
    (None, "abc", False, False),                                         # nothing stored
])
async def test_cached_reports_staleness_rather_than_hiding_a_set(record, wanted, found, stale):
    """A stale set is still returned. Withholding it leaves an empty panel that a
    user cannot read as either 'not generated yet' or 'broken'."""
    with patch.object(svc.AIRecommendation, "find_one", new=AsyncMock(return_value=record)):
        result, is_stale = await svc._cached(USER.id, RecommendationDomain.HABITS, wanted)
    assert (result is not None) == found
    assert is_stale == stale


@pytest.mark.asyncio
async def test_cache_accepts_a_naive_generated_at():
    """Documents written before tz-aware defaults would otherwise raise on the
    subtraction and take the endpoint down rather than just reading as stale."""
    record = _record()
    record.generated_at = datetime.utcnow()
    with patch.object(svc.AIRecommendation, "find_one", new=AsyncMock(return_value=record)):
        result, is_stale = await svc._cached(USER.id, RecommendationDomain.HABITS, "abc")
    assert result is not None and is_stale is False


# ─── orchestration ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_page_load_never_reaches_a_provider():
    """The whole point of the explicit-generation change: opening a page must not
    spend a model call, however stale the stored set is."""
    with patch.object(svc, "_cached", new=AsyncMock(return_value=(_record(), False))), \
         patch.object(svc, "_generate", new=AsyncMock()) as generate:
        result = await svc.get_recommendations(
            USER, RecommendationDomain.HABITS, {"x": 1}, ["rule line"]
        )

    generate.assert_not_awaited()
    assert result.items == ["cached line"] and result.cached is True


@pytest.mark.asyncio
async def test_a_stale_set_is_served_on_load_and_flagged():
    with patch.object(svc, "_cached", new=AsyncMock(return_value=(_record(), True))), \
         patch.object(svc, "_generate", new=AsyncMock()) as generate:
        result = await svc.get_recommendations(
            USER, RecommendationDomain.HABITS, {"x": 1}, ["rule line"]
        )

    generate.assert_not_awaited()
    assert result.items == ["cached line"] and result.stale is True


@pytest.mark.asyncio
async def test_nothing_generated_yet_falls_back_to_rules_without_calling_out():
    with patch.object(svc, "_cached", new=AsyncMock(return_value=(None, False))), \
         patch.object(svc, "_generate", new=AsyncMock()) as generate:
        result = await svc.get_recommendations(
            USER, RecommendationDomain.STUDY, {"x": 1}, ["rule line"]
        )

    generate.assert_not_awaited()
    assert result.items == ["rule line"]
    assert result.provider == "rules", "fallback must never be reported as model output"
    assert result.cached is False and result.stale is False


@pytest.mark.asyncio
async def test_generate_calls_a_provider_and_stores_the_result():
    now = datetime.now(timezone.utc)
    with patch.object(svc, "_cached", new=AsyncMock(return_value=(None, False))), \
         patch.object(svc, "_generate", new=AsyncMock(return_value=(["ai line"], "groq"))), \
         patch.object(svc, "_store", new=AsyncMock(return_value=now)) as store:
        result = await svc.get_recommendations(
            USER, RecommendationDomain.STUDY, {"x": 1}, ["rule line"], generate=True
        )

    store.assert_awaited_once()
    assert result.items == ["ai line"] and result.provider == "groq"
    assert result.generated_at == now and result.cached is False and result.stale is False


@pytest.mark.asyncio
async def test_generate_bypasses_a_fresh_cache():
    with patch.object(svc, "_cached", new=AsyncMock(return_value=(_record(), False))), \
         patch.object(svc, "_generate", new=AsyncMock(return_value=(["fresh"], "groq"))), \
         patch.object(svc, "_store", new=AsyncMock(return_value=datetime.now(timezone.utc))):
        result = await svc.get_recommendations(
            USER, RecommendationDomain.HABITS, {"x": 1}, [], generate=True
        )

    assert result.items == ["fresh"] and result.cached is False


@pytest.mark.asyncio
async def test_a_failed_generation_keeps_the_previous_set():
    """A provider outage must not blank out advice the user already had, and must
    not be written over a good stored set."""
    with patch.object(svc, "_cached", new=AsyncMock(return_value=(_record(), False))), \
         patch.object(svc, "_generate", new=AsyncMock(return_value=([], ""))), \
         patch.object(svc, "_store", new=AsyncMock()) as store:
        result = await svc.get_recommendations(
            USER, RecommendationDomain.HABITS, {"x": 1}, ["rule line"], generate=True
        )

    store.assert_not_awaited()
    assert result.items == ["cached line"] and result.provider == "groq"


@pytest.mark.asyncio
async def test_a_failed_first_generation_falls_back_to_rules():
    with patch.object(svc, "_cached", new=AsyncMock(return_value=(None, False))), \
         patch.object(svc, "_generate", new=AsyncMock(return_value=([], ""))), \
         patch.object(svc, "_store", new=AsyncMock()) as store:
        result = await svc.get_recommendations(
            USER, RecommendationDomain.STUDY, {"x": 1}, ["rule line"], generate=True
        )

    store.assert_not_awaited()
    assert result.items == ["rule line"] and result.provider == "rules"


@pytest.mark.asyncio
async def test_a_provider_exception_does_not_escape():
    """A provider outage must degrade, not 500 the page."""
    settings = SimpleNamespace(GROQ_API_KEY="k", GEMINI_API_KEY=None)
    with patch.object(svc, "get_settings", return_value=settings), \
         patch.object(svc, "_call_groq", new=AsyncMock(side_effect=RuntimeError("upstream down"))):
        items, provider = await svc._generate({"x": 1}, "habits")
    assert items == [] and provider == ""


@pytest.mark.asyncio
async def test_gemini_is_tried_when_groq_returns_nothing_usable():
    settings = SimpleNamespace(GROQ_API_KEY="k", GEMINI_API_KEY="g")
    with patch.object(svc, "get_settings", return_value=settings), \
         patch.object(svc, "_call_groq", new=AsyncMock(return_value="not json at all")), \
         patch.object(svc, "_call_gemini", new=AsyncMock(return_value='["from gemini"]')):
        items, provider = await svc._generate({"x": 1}, "habits")
    assert items == ["from gemini"] and provider == "gemini"


# ─── deterministic fallback builders ─────────────────────────────────────────

def test_rule_based_habit_items_lead_with_problems():
    summary = SimpleNamespace(
        habit_streak=SimpleNamespace(current_streak=1, longest_streak=12),
        missed_habits=SimpleNamespace(missed_days=15, window_days=30),
        negative_habits=SimpleNamespace(habits=[
            SimpleNamespace(habit="screen_time", average_value=8.87, unit="hours",
                            detail="Target is 6 hours/day or less."),
        ]),
        positive_habits=SimpleNamespace(habits=[
            SimpleNamespace(habit="sleep", average_value=7.63, unit="hours", detail="x"),
        ]),
    )
    items = svc.rule_based_habit_items(summary)

    assert items[0] == "Current streak: 1 day (longest: 12)."
    assert "Missed logging on 15 of the last 30 days." in items
    negative_at = next(i for i, t in enumerate(items) if t.startswith("Screen time"))
    positive_at = next(i for i, t in enumerate(items) if t.startswith("Sleep"))
    assert negative_at < positive_at, "problems come before things already going well"


def test_rule_based_habit_items_omit_the_missed_line_at_zero():
    summary = SimpleNamespace(
        habit_streak=SimpleNamespace(current_streak=3, longest_streak=3),
        missed_habits=SimpleNamespace(missed_days=0, window_days=30),
        negative_habits=SimpleNamespace(habits=[]),
        positive_habits=SimpleNamespace(habits=[]),
    )
    items = svc.rule_based_habit_items(summary)
    assert items == ["Current streak: 3 days (longest: 3)."]
