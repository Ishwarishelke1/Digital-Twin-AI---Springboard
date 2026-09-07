"""
tests/test_habit_generator.py — Guards the habit-failure data generator.

Same reasoning as the goal generator's tests: a defect here silently invalidates
every downstream metric, and the leakage check is the load-bearing one.

The label-definition test matters particularly. An earlier version counted every
single unlogged day as a break, which pushed 71% of days positive — at which
point the model was really learning logging diligence rather than habit failure.
"""
import importlib.util
import random
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "generate_synthetic_habits",
    Path(__file__).resolve().parent.parent / "scripts" / "generate_synthetic_habits.py",
)
gen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gen
_spec.loader.exec_module(gen)


def _day(i, logged=True, score=90.0, weekday=None):
    return gen.Day(
        index=i, weekday=weekday if weekday is not None else i % 7,
        logged=logged, score=score if logged else None,
        good=(score >= gen.POSITIVE_THRESHOLD), sleep=8.0, exercise=35.0, water=2.2, screen=4.0,
    )


# ─── leakage ─────────────────────────────────────────────────────────────────

def test_features_ignore_days_after_the_prediction_point():
    """Features at day t must not move when the future changes — only the label may."""
    base = [_day(i) for i in range(60)]
    rows_a = gen.build_rows("u", base, warmup=21)
    row_a = next(r for r in rows_a if r["day_index"] == 30)

    tampered = [_day(i) for i in range(60)]
    for i in range(31, 60):                      # wreck everything after day 30
        tampered[i] = _day(i, logged=False)
    row_b = next(r for r in gen.build_rows("u", tampered, warmup=21) if r["day_index"] == 30)

    for k in row_a:
        if k == "breaks_within_7d":
            continue
        assert row_a[k] == row_b[k], f"{k} changed when only future days changed — leakage"


def test_label_does_respond_to_the_future():
    """The complement of the leakage test: the label is *supposed* to see ahead."""
    good = [_day(i) for i in range(60)]
    row = next(r for r in gen.build_rows("u", good, warmup=21) if r["day_index"] == 30)
    assert row["breaks_within_7d"] == 0

    bad = [_day(i) for i in range(60)]
    bad[33] = _day(33, score=40.0)               # a clearly bad day inside the horizon
    row = next(r for r in gen.build_rows("u", bad, warmup=21) if r["day_index"] == 30)
    assert row["breaks_within_7d"] == 1


# ─── the break definition ────────────────────────────────────────────────────

def test_one_missed_log_is_not_a_break():
    """Mirrors _compute_streak in habit_analytics_service, which keeps a streak
    active if today or yesterday has an entry. Treating a single gap as failure
    made 71% of days positive and measured diligence, not habit failure."""
    days = [_day(i) for i in range(60)]
    days[34] = _day(34, logged=False)
    row = next(r for r in gen.build_rows("u", days, warmup=21) if r["day_index"] == 30)
    assert row["breaks_within_7d"] == 0


def test_two_consecutive_missed_logs_is_a_break():
    days = [_day(i) for i in range(60)]
    days[34] = _day(34, logged=False)
    days[35] = _day(35, logged=False)
    row = next(r for r in gen.build_rows("u", days, warmup=21) if r["day_index"] == 30)
    assert row["breaks_within_7d"] == 1


def test_score_below_threshold_is_a_break():
    days = [_day(i) for i in range(60)]
    days[32] = _day(32, score=gen.POSITIVE_THRESHOLD - 0.1)
    row = next(r for r in gen.build_rows("u", days, warmup=21) if r["day_index"] == 30)
    assert row["breaks_within_7d"] == 1


def test_scoring_matches_the_apps_definition():
    """A day meeting every target scores 100; the model's notion of a good day
    must match what the dashboard shows."""
    assert gen.daily_score(8.0, 30.0, 2.0, 4.0) == 100.0
    assert gen.daily_score(4.0, 0.0, 0.3, 14.0) < gen.POSITIVE_THRESHOLD


# ─── determinism, balance, signal ────────────────────────────────────────────

def test_same_seed_reproduces_identical_data():
    a, _ = gen.generate(users=6, days=90, seed=11)
    b, _ = gen.generate(users=6, days=90, seed=11)
    assert a == b


def test_class_balance_is_usable():
    _, meta = gen.generate(users=40, days=150, seed=3)
    assert 0.10 <= meta["break_rate"] <= 0.60, meta["break_rate"]


def test_longer_streaks_break_less():
    """Momentum is encoded in the generator; if it does not show up in the data,
    downstream importance results prove nothing."""
    rows, _ = gen.generate(users=60, days=180, seed=5)
    short = [r for r in rows if r["current_streak"] <= 2]
    long_ = [r for r in rows if r["current_streak"] >= 10]
    short_rate = sum(r["breaks_within_7d"] for r in short) / len(short)
    long_rate = sum(r["breaks_within_7d"] for r in long_) / len(long_)
    assert long_rate < short_rate - 0.10, (short_rate, long_rate)


def test_missing_logs_predict_breaks():
    """Informative missingness: people stop recording when things go badly."""
    rows, _ = gen.generate(users=60, days=180, seed=7)
    clean = [r for r in rows if r["missed_logs_7d"] == 0]
    gappy = [r for r in rows if r["missed_logs_7d"] >= 3]
    clean_rate = sum(r["breaks_within_7d"] for r in clean) / len(clean)
    gappy_rate = sum(r["breaks_within_7d"] for r in gappy) / len(gappy)
    assert gappy_rate > clean_rate + 0.15, (clean_rate, gappy_rate)


@pytest.mark.parametrize("field", ["adherence_7d", "adherence_14d", "adherence_30d"])
def test_adherence_is_a_proportion(field):
    rows, _ = gen.generate(users=20, days=120, seed=9)
    assert all(0.0 <= r[field] <= 1.0 for r in rows)
