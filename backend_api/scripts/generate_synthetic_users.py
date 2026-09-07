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
EFFORT_INTERCEPT = 0.95
EFFORT_DILIGENCE_SLOPE = 1.15

# Disruption — a stretch where progress largely stops. This is the main source of
# irreducible uncertainty: it is invisible at the prediction snapshot when it has
# not started yet, so no model can anticipate it. Without it the simulation is
# more predictable than real life and the model becomes overconfident.
DISRUPTION_PROBABILITY = 0.45
DISRUPTION_LENGTH_DAYS = (10, 45)
DISRUPTION_EFFORT_MULTIPLIER = 0.15

# Goal duration span. Wide and continuous so the model sees the range real goals
# actually occupy.
MIN_DURATION_DAYS = 14
MAX_DURATION_DAYS = 400

# Where in a goal's life the prediction is taken.
SNAPSHOT_WINDOW = (0.05, 0.95)

# Some goals are simply abandoned, or tracked entirely outside the app, and carry
# no linked contributions at all. Without these, contribution_count and
# days_since_last_contribution never reach the values real goals show and the
# serving guard rejects them.
ABANDONED_GOAL_PROBABILITY = 0.18

# Progress updated directly on the goal rather than through a linked transaction.
# current_value still moves; the contribution log stays empty. Common in the real
# data, and absent from training it made the model read every manually-tracked
# goal as abandoned.
MANUAL_TRACKING_PROBABILITY = 0.30

# Deadline sprint. Effort rises as the deadline nears — people cram before an
# exam and top up a fund before a due date. Without this the model only ever saw
# effort decay, so any goal needing to catch up late was scored as near-hopeless:
# a course 76% through and needing to double its rate came out at 4%, when a late
# push is an ordinary thing people actually do.
SPRINT_STRENGTH = 0.7

# Contribution cadence — the fraction of days on which a contribution happens.
# A savings deposit or study session is a discrete event, not a daily drip, so
# most days carry none. More diligent users contribute more often, which keeps a
# sparse record informative.
CONTRIBUTION_CADENCE_BASE = 0.06
CONTRIBUTION_CADENCE_SLOPE = 0.22

GROUND_TRUTH = {
    "category_effort": CATEGORY_EFFORT,
    "competition_penalty_per_goal": COMPETITION_PENALTY,
    "competition_floor": COMPETITION_FLOOR,
    "adherence_half_life_days": ADHERENCE_HALF_LIFE_DAYS,
    "adherence_floor": ADHERENCE_FLOOR,
    "effort_intercept": EFFORT_INTERCEPT,
    "effort_diligence_slope": EFFORT_DILIGENCE_SLOPE,
    "min_duration_days": MIN_DURATION_DAYS,
    "max_duration_days": MAX_DURATION_DAYS,
    "snapshot_window": SNAPSHOT_WINDOW,
    "abandoned_goal_probability": ABANDONED_GOAL_PROBABILITY,
    "sprint_strength": SPRINT_STRENGTH,
    "contribution_cadence_base": CONTRIBUTION_CADENCE_BASE,
    "contribution_cadence_slope": CONTRIBUTION_CADENCE_SLOPE,
    "disruption_probability": DISRUPTION_PROBABILITY,
    "disruption_length_days": DISRUPTION_LENGTH_DAYS,
    "disruption_effort_multiplier": DISRUPTION_EFFORT_MULTIPLIER,
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
    # Cumulative progress at the end of each day — this is the goal's
    # current_value. Tracked separately from `contributions` because the two can
    # legitimately diverge: a user may update progress directly without linking a
    # transaction, in which case current_value moves while the contribution log
    # stays empty. Training on data where they were always identical taught the
    # model that no contributions means no progress, so real goals tracked
    # manually were scored at 0%.
    cumulative_by_day: list[float] = field(default_factory=list)
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

    # Disruption: illness, exam weeks, a job change. Without this the process is
    # far too predictable — daily noise averages out over months, so the early
    # contribution rate almost determines the outcome and the model becomes
    # near-certain (it was returning 100% on real goals). A disruption the
    # snapshot cannot foresee is irreducible uncertainty, which is what real life
    # has and what stops the model claiming more confidence than is warranted.
    disruption_start, disruption_end = None, None
    if rng.random() < DISRUPTION_PROBABILITY:
        disruption_start = rng.randint(0, max(1, goal.duration_days - 1))
        disruption_end = disruption_start + rng.randint(*DISRUPTION_LENGTH_DAYS)

    # Contributions are discrete events, and the event IS the record — a goal's
    # current_value only moves when a linked transaction or session is logged, so
    # there is no such thing as unrecorded progress here. An earlier version
    # modelled daily accrual with partial logging, which meant training
    # progress_ratio reflected a fraction of true progress while the served
    # feature reflected all of it: a severe train/serve mismatch that inverted the
    # predictions. Cadence still varies with diligence, so a sparse record remains
    # informative — it just means fewer contributions, not hidden ones.
    if rng.random() < ABANDONED_GOAL_PROBABILITY:
        goal.cumulative_by_day = [0.0] * goal.duration_days
        return  # never acted on: no contributions, no progress, never completed

    manually_tracked = rng.random() < MANUAL_TRACKING_PROBABILITY
    cadence = CONTRIBUTION_CADENCE_BASE + CONTRIBUTION_CADENCE_SLOPE * diligence
    expected_events = max(goal.duration_days * cadence, 1.0)
    base_amount = goal.target_value / expected_events

    cumulative = 0.0
    for day in range(goal.duration_days):
        disrupted = disruption_start is not None and disruption_start <= day < disruption_end
        # Adherence decays as a goal ages, but toward a floor rather than to zero —
        # enthusiasm fades, it does not usually vanish entirely.
        decay = ADHERENCE_FLOOR + (1.0 - ADHERENCE_FLOOR) * 0.5 ** (day / ADHERENCE_HALF_LIFE_DAYS)
        effort = (EFFORT_INTERCEPT + EFFORT_DILIGENCE_SLOPE * diligence) * competition * category * decay
        if disrupted:
            effort *= DISRUPTION_EFFORT_MULTIPLIER
        # Late push: grows quadratically toward the deadline.
        effort *= 1.0 + SPRINT_STRENGTH * (day / goal.duration_days) ** 2

        # Does a contribution happen today at all?
        if rng.random() >= cadence * (DISRUPTION_EFFORT_MULTIPLIER if disrupted else 1.0):
            goal.cumulative_by_day.append(cumulative)
            continue

        amount = base_amount * effort * rng.lognormvariate(0.0, 0.35)
        goal.contributions.append((day, round(amount, 2)))
        cumulative += amount

        if goal.completed_day is None and cumulative >= goal.target_value:
            goal.completed_day = day
        goal.cumulative_by_day.append(cumulative)

    if manually_tracked:
        # Progress happened and is reflected in current_value; it simply was not
        # recorded as linked transactions.
        goal.contributions = []


def build_feature_row(goal: Goal, snapshot_day: int, user_prior_rate: float, competing: int) -> dict:
    """Features observable at snapshot_day, and the eventual outcome as the label.

    Nothing here may use information from after snapshot_day — that would be
    leakage, and would produce an evaluation that looks excellent and means
    nothing.
    """
    seen = [(d, a) for d, a in goal.contributions if d <= snapshot_day]
    # progress == current_value, which exists whether or not contributions were
    # linked; contribution_count / days_since_last come from the log alone.
    idx = min(snapshot_day, len(goal.cumulative_by_day) - 1)
    contributed = goal.cumulative_by_day[idx] if goal.cumulative_by_day else 0.0
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
            # Sampled continuously across a wide span rather than from a handful
            # of round values. Real goals run from a fortnight to well over a
            # year; training on six fixed durations left duration_days covering
            # [30, 180], so the serving guard rejected a real 330-day goal.
            duration = rng.randint(MIN_DURATION_DAYS, MAX_DURATION_DAYS)
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
            # Far enough back that the goal has fully resolved by now, with varied
            # recency. Was a fixed 400-day ceiling, which is empty once duration
            # approaches it.
            created = now - timedelta(days=rng.randint(duration + 5, duration + 200))

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

            # Predict partway through, not at the end. The snapshot spans nearly
            # the whole goal life: a user opens the page whenever they like, so a
            # narrow window (this was 0.25-0.65) leaves the model unable to score
            # a goal three-quarters of the way through — which is exactly when
            # someone most wants to know.
            snapshot = max(1, int(duration * rng.uniform(*SNAPSHOT_WINDOW)))

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
