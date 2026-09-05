"""
tests/test_synthetic_generator.py — Guards the synthetic data generator.

The generator underpins every model evaluation, so a defect here silently
invalidates every number produced downstream. The leakage test is the important
one: if features could see past the prediction snapshot, the model would score
brilliantly and mean nothing.

No DB, no network — the generator is pure stdlib.
"""
import importlib.util
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "generate_synthetic_users",
    Path(__file__).resolve().parent.parent / "scripts" / "generate_synthetic_users.py",
)
gen = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass resolves type hints via sys.modules[cls.__module__],
# which raises if the module is not there yet.
sys.modules[_spec.name] = gen
_spec.loader.exec_module(gen)


def _goal(duration=90, target=1000.0):
    now = datetime.now(timezone.utc)
    return gen.Goal(
        goal_id="g1",
        user_id="u1",
        category="STUDY",
        target_value=target,
        created_at=now,
        target_date=now + timedelta(days=duration),
        duration_days=duration,
    )


# ─── leakage ─────────────────────────────────────────────────────────────────

def test_features_ignore_contributions_after_the_snapshot():
    """The central correctness property. Features are computed at a prediction
    point partway through a goal; anything after that point is the future and
    must not influence them. If this fails, every downstream metric is worthless
    regardless of how good it looks."""
    goal = _goal()
    goal.contributions = [(5, 100.0), (10, 100.0), (20, 100.0)]
    before = gen.build_feature_row(goal, snapshot_day=15, user_prior_rate=0.5, competing=1)

    # Add a large contribution *after* the snapshot, and another far later.
    goal.contributions += [(16, 5000.0), (80, 9999.0)]
    after = gen.build_feature_row(goal, snapshot_day=15, user_prior_rate=0.5, competing=1)

    feature_keys = [k for k in before if k != "completed_by_deadline"]
    for key in feature_keys:
        assert before[key] == after[key], f"{key} changed when future data was added — leakage"


def test_label_reflects_the_full_horizon_not_the_snapshot():
    """The label is the eventual outcome, so it *should* respond to post-snapshot
    reality — the opposite of the features. This is what makes the task
    predictive rather than descriptive."""
    goal = _goal()
    goal.contributions = [(5, 10.0)]
    goal.completed_day = None
    assert gen.build_feature_row(goal, 15, 0.5, 1)["completed_by_deadline"] == 0

    goal.completed_day = 70  # completed later, before the 90-day deadline
    assert gen.build_feature_row(goal, 15, 0.5, 1)["completed_by_deadline"] == 1


def test_completion_after_the_deadline_is_not_a_success():
    goal = _goal(duration=90)
    goal.completed_day = 95
    assert gen.build_feature_row(goal, 40, 0.5, 1)["completed_by_deadline"] == 0


# ─── the record/reality distinction ──────────────────────────────────────────

def test_progress_accrues_even_when_not_logged():
    """Contributions happen whether or not the user records them. An earlier
    draft only accumulated logged days, which erased the informative-missingness
    signal — the gap between what happened and what was written down."""
    rng = random.Random(1)
    goal = _goal(duration=60)
    original = gen.BASE_LOG_PROBABILITY
    try:
        gen.BASE_LOG_PROBABILITY = -10.0  # nothing is ever logged
        gen.simulate_goal(rng, goal, diligence=0.99, competing=0)
    finally:
        gen.BASE_LOG_PROBABILITY = original

    assert goal.contributions == [], "nothing should have been logged"
    assert goal.completed_day is not None, "progress must accrue despite zero logging"


# ─── determinism and balance ─────────────────────────────────────────────────

def test_same_seed_reproduces_identical_data():
    a, _ = gen.generate(users=12, seed=99)
    b, _ = gen.generate(users=12, seed=99)
    assert a == b


def test_different_seeds_differ():
    a, _ = gen.generate(users=12, seed=1)
    b, _ = gen.generate(users=12, seed=2)
    assert a != b


def test_class_balance_is_usable():
    """A near-degenerate dataset cannot train or evaluate a classifier. The first
    draft of the generator produced 2% completion, which is why this exists."""
    rows, meta = gen.generate(users=60, seed=7)
    rate = meta["completion_rate"]
    assert 0.20 <= rate <= 0.70, f"completion rate {rate:.1%} is not a usable balance"


# ─── ground truth is present in the data ─────────────────────────────────────

def test_goal_dilution_effect_is_present():
    """The generator encodes a per-competing-goal penalty. If it does not show up
    in the data, parameter recovery downstream proves nothing."""
    rows, _ = gen.generate(users=120, seed=11)
    low = [r for r in rows if r["competing_goals"] <= 1]
    high = [r for r in rows if r["competing_goals"] >= 4]
    low_rate = sum(r["completed_by_deadline"] for r in low) / len(low)
    high_rate = sum(r["completed_by_deadline"] for r in high) / len(high)
    assert low_rate > high_rate + 0.15, (
        f"dilution not visible: {low_rate:.1%} with few competing goals vs "
        f"{high_rate:.1%} with many"
    )


def test_category_effort_ordering_is_present():
    rows, _ = gen.generate(users=150, seed=13)
    rates = {}
    for cat in gen.CATEGORIES:
        sub = [r for r in rows if r["category"] == cat]
        rates[cat] = sum(r["completed_by_deadline"] for r in sub) / len(sub)
    # FINANCE has the highest effort multiplier, FITNESS the lowest.
    assert rates["FINANCE"] > rates["FITNESS"], rates


@pytest.mark.parametrize("field", ["progress_ratio", "time_elapsed_ratio", "rate_ratio"])
def test_features_are_non_negative(field):
    rows, _ = gen.generate(users=30, seed=5)
    assert all(r[field] >= 0 for r in rows)
