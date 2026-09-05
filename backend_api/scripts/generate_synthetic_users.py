"""
scripts/generate_synthetic_users.py — Synthetic goal histories for training and
evaluating the goal-completion model.

WHY THIS EXISTS
The production database has 5 real users and a handful of goals. Nothing is
trainable at that size, and — more importantly — nothing is *evaluable*: you
cannot hold out a test set, plot a calibration curve, or compare against a
baseline. This generator produces enough resolved goals to do all three.

DESIGN — process simulation, not label sampling
The naive approach samples a label straight from a logistic function of the
features. That bakes the answer in: the model then "discovers" the exact
relationship the generator was told to use, and the evaluation is circular.

Instead this simulates the underlying *process* — a user contributes toward a
goal day by day, at a rate driven by latent traits, and completion emerges from
whether the accumulated total reaches the target before the deadline. The
feature/label relationship is therefore a consequence of the simulation rather
than an assumption, which is what makes the resulting evaluation meaningful.

Features are snapshotted at a prediction point partway through each goal, using
only information available at that moment. The label is the eventual outcome.
That mirrors how the model is actually used: predicting mid-flight, not
explaining the past.

WHAT IS AND IS NOT ESTABLISHED
Training on this data demonstrates the pipeline is correct — that the model
recovers a signal that genuinely exists, is calibrated, and beats a baseline. It
does NOT establish that the model reflects real human behaviour. Only real
longitudinal data can do that. Say so in any writeup.

Stdlib only, deterministic under --seed.

Usage (from backend_api/):
    python3 scripts/generate_synthetic_users.py
    python3 scripts/generate_synthetic_users.py --users 200 --out data/synthetic
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Generative parameters ────────────────────────────────────────────────────
# Written down explicitly so the trained model can be checked against them:
# if it cannot recover these relationships, the pipeline is broken.

CATEGORIES = ["FINANCE", "STUDY", "HABIT", "FITNESS", "CAREER"]

# Per-category difficulty multiplier on the effort a user actually applies.
# FINANCE is easiest to sustain (a standing transfer needs no willpower);
# FITNESS and CAREER decay fastest.
CATEGORY_EFFORT = {
    "FINANCE": 1.10,
    "STUDY": 0.95,
    "HABIT": 0.90,
    "FITNESS": 0.80,
    "CAREER": 0.85,
}

# Each additional active goal dilutes effort — the "over-committed" effect the
# optimizer section of the design doc is about.
COMPETITION_PENALTY = 0.08   # per competing active goal
COMPETITION_FLOOR = 0.55     # dilution never drops effort below this fraction

# Adherence decays over a goal's life: enthusiasm fades. It decays toward a floor
# rather than to zero — people slow down, they rarely stop dead.
ADHERENCE_HALF_LIFE_DAYS = 75.0
ADHERENCE_FLOOR = 0.55

# Effort applied, as a multiple of the rate the goal requires, before competition,
# category and decay are applied. Centred so a median user (diligence ≈ 0.55) lands
# slightly under 1.0 — completion should be genuinely uncertain, not the default.
# Calibrated to produce a usable class balance: a dataset that is 98% one class
# teaches a classifier nothing and cannot be evaluated meaningfully.
EFFORT_INTERCEPT = 0.80
EFFORT_DILIGENCE_SLOPE = 1.00

# Logging behaviour. Low-diligence users log less often, so gaps in the record
# are themselves informative — missingness is NOT random, which the design doc
# flags as the most common source of silent corruption in habit analytics.
BASE_LOG_PROBABILITY = 0.55

GROUND_TRUTH = {
    "category_effort": CATEGORY_EFFORT,
    "competition_penalty_per_goal": COMPETITION_PENALTY,
    "competition_floor": COMPETITION_FLOOR,
    "adherence_half_life_days": ADHERENCE_HALF_LIFE_DAYS,
    "adherence_floor": ADHERENCE_FLOOR,
    "effort_intercept": EFFORT_INTERCEPT,
    "effort_diligence_slope": EFFORT_DILIGENCE_SLOPE,
    "base_log_probability": BASE_LOG_PROBABILITY,
    "diligence_distribution": "Beta(2.4, 2.0), mean ≈ 0.55",
    "notes": (
        "Completion emerges from day-by-day contribution accumulation reaching the "
        "target before the deadline. It is not sampled from a formula over features."
    ),
}


@dataclass
class Goal:
    goal_id: str
    user_id: str
    category: str
    target_value: float
    created_at: datetime
    target_date: datetime
    duration_days: int
    contributions: list[tuple[int, float]] = field(default_factory=list)  # (day_offset, amount)
    completed_day: int | None = None

    @property
    def total_contributed(self) -> float:
        return sum(a for _, a in self.contributions)


def _beta(rng: random.Random, alpha: float, beta: float) -> float:
    """Beta sample via two gammas — random.betavariate exists but this keeps the
    dependency on a single rng instance explicit for reproducibility."""
    return rng.betavariate(alpha, beta)


def simulate_goal(rng: random.Random, goal: Goal, diligence: float, competing: int) -> None:
    """Runs the contribution process day by day. Mutates the goal in place."""
    required_daily = goal.target_value / goal.duration_days

    competition = max(COMPETITION_FLOOR, 1.0 - COMPETITION_PENALTY * competing)
    category = CATEGORY_EFFORT[goal.category]

    cumulative = 0.0
    for day in range(goal.duration_days):
        # Adherence decays as a goal ages, but toward a floor rather than to zero —
        # enthusiasm fades, it does not usually vanish entirely.
        decay = ADHERENCE_FLOOR + (1.0 - ADHERENCE_FLOOR) * 0.5 ** (day / ADHERENCE_HALF_LIFE_DAYS)
        effort = (EFFORT_INTERCEPT + EFFORT_DILIGENCE_SLOPE * diligence) * competition * category * decay
        # Day-to-day noise; occasionally a burst, occasionally nothing.
        noise = rng.lognormvariate(0.0, 0.45)
        contributed = required_daily * effort * noise

        # Progress accrues whether or not the user records it. Logging affects the
        # *observed record*, not reality — conflating the two would erase exactly
        # the signal this generator is meant to contain, since the gap between what
        # happened and what was written down is what makes missingness informative.
        cumulative += contributed
        if rng.random() < (BASE_LOG_PROBABILITY + 0.40 * diligence):
            goal.contributions.append((day, round(contributed, 2)))

        if goal.completed_day is None and cumulative >= goal.target_value:
            goal.completed_day = day


def build_feature_row(goal: Goal, snapshot_day: int, user_prior_rate: float, competing: int) -> dict:
    """Features observable at snapshot_day, and the eventual outcome as the label.

    Nothing here may use information from after snapshot_day — that would be
    leakage, and would produce an evaluation that looks excellent and means
    nothing.
    """
    seen = [(d, a) for d, a in goal.contributions if d <= snapshot_day]
    contributed = sum(a for _, a in seen)
    days_elapsed = max(1, snapshot_day)
    days_remaining = max(0, goal.duration_days - snapshot_day)

    required_daily_original = goal.target_value / goal.duration_days
    observed_daily = contributed / days_elapsed
    remaining = max(0.0, goal.target_value - contributed)
    required_daily_remaining = remaining / days_remaining if days_remaining else float("inf")

    last_day = max((d for d, _ in seen), default=None)
    days_since_last = snapshot_day - last_day if last_day is not None else snapshot_day

    completed_by_deadline = (
        goal.completed_day is not None and goal.completed_day < goal.duration_days
    )

    return {
        "goal_id": goal.goal_id,
        "user_id": goal.user_id,
        "category": goal.category,
        # ── features ──
        "progress_ratio": round(contributed / goal.target_value, 4),
        "time_elapsed_ratio": round(snapshot_day / goal.duration_days, 4),
        "rate_ratio": round(observed_daily / required_daily_original, 4)
        if required_daily_original
        else 0.0,
        "required_rate_multiple": round(
            min(required_daily_remaining / required_daily_original, 20.0), 4
        )
        if required_daily_original and days_remaining
        else 20.0,
        "days_remaining": days_remaining,
        "duration_days": goal.duration_days,
        "log_target_value": round(math.log10(max(goal.target_value, 1.0)), 4),
        "competing_goals": competing,
        "contribution_count": len(seen),
        "days_since_last_contribution": days_since_last,
        "user_prior_completion_rate": round(user_prior_rate, 4),
        # ── label ──
        "completed_by_deadline": int(completed_by_deadline),
    }


def generate(users: int, seed: int) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    now = datetime.now(timezone.utc)

    completions_by_user: dict[str, list[int]] = {}

    for u in range(users):
        user_id = f"synthetic-user-{u:04d}"
        # Latent trait. This is the hierarchical structure the design doc's
        # Bayesian personalization section is about: one parameter per person,
        # drawn from a population distribution.
        diligence = _beta(rng, 2.4, 2.0)

        n_goals = rng.randint(3, 12)
        history: list[int] = []

        for g in range(n_goals):
            category = rng.choice(CATEGORIES)
            duration = rng.choice([30, 45, 60, 90, 120, 180])
            # Target magnitudes differ wildly by category; log-uniform is closer
            # to how people actually set them than uniform.
            target = {
                "FINANCE": lambda: rng.uniform(5_000, 200_000),
                "STUDY": lambda: rng.uniform(20, 300),
                "HABIT": lambda: rng.uniform(20, 180),
                "FITNESS": lambda: rng.uniform(10, 150),
                "CAREER": lambda: rng.uniform(5, 60),
            }[category]()

            competing = rng.randint(0, 5)
            created = now - timedelta(days=rng.randint(duration + 5, 400))

            goal = Goal(
                goal_id=f"{user_id}-goal-{g:02d}",
                user_id=user_id,
                category=category,
                target_value=round(target, 2),
                created_at=created,
                target_date=created + timedelta(days=duration),
                duration_days=duration,
            )
            simulate_goal(rng, goal, diligence, competing)

            # Predict partway through, not at the end. Varying the snapshot point
            # stops the model keying on a single fixed horizon.
            snapshot = int(duration * rng.uniform(0.25, 0.65))

            prior_rate = (sum(history) / len(history)) if history else 0.5
            row = build_feature_row(goal, snapshot, prior_rate, competing)
            rows.append(row)
            history.append(row["completed_by_deadline"])

        completions_by_user[user_id] = history

    meta = {
        "seed": seed,
        "n_users": users,
        "n_goals": len(rows),
        "completion_rate": round(sum(r["completed_by_deadline"] for r in rows) / len(rows), 4),
        "ground_truth": GROUND_TRUTH,
    }
    return rows, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic goal histories.")
    parser.add_argument("--users", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--out", default="data/synthetic")
    args = parser.parse_args()

    rows, meta = generate(args.users, args.seed)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "goals.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    meta_path = out_dir / "ground_truth.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    # ── summary ──────────────────────────────────────────────────────────────
    n = len(rows)
    pos = sum(r["completed_by_deadline"] for r in rows)
    print(f"generated {n} goals across {args.users} users  (seed {args.seed})")
    print(f"  completed by deadline : {pos} ({pos / n:.1%})")
    print(f"  base-rate baseline    : {max(pos, n - pos) / n:.1%} accuracy")
    print(f"                          ↑ any model must beat this to be worth anything\n")

    print("  completion rate by category:")
    for cat in CATEGORIES:
        sub = [r for r in rows if r["category"] == cat]
        if sub:
            rate = sum(r["completed_by_deadline"] for r in sub) / len(sub)
            print(f"    {cat:<10} {len(sub):>4} goals   {rate:>6.1%}")

    print("\n  completion rate by competing-goal count (dilution effect):")
    for c in range(6):
        sub = [r for r in rows if r["competing_goals"] == c]
        if sub:
            rate = sum(r["completed_by_deadline"] for r in sub) / len(sub)
            print(f"    {c} competing  {len(sub):>4} goals   {rate:>6.1%}")

    print(f"\nwrote {csv_path}")
    print(f"wrote {meta_path}")
    print("\nNOTE: this validates the pipeline, not the model's fidelity to real")
    print("behaviour. Only real longitudinal data can establish that.")


if __name__ == "__main__":
    main()
