"""
scripts/generate_synthetic_habits.py — Synthetic daily habit logs for the
habit-failure model.

WHY A SECOND GENERATOR
The goal generator produces goals; this produces daily biometric logs, which are
a different shape entirely — a per-day sequence per user rather than one row per
goal. The real database holds 63 habit logs from one user, which is nowhere near
enough to train or evaluate on.

WHAT "FAILURE" MEANS
Deliberately the same definition the application already uses, so the model's
label matches what the product shows. habit_analytics_service scores each day as
an equal-weighted composite over sleep, exercise, water and screen time, and
treats POSITIVE_THRESHOLD = 70 as a good day. A streak is consecutive good days.
A break is a logged day scoring below 70, or two consecutive days with no log —
the two-day rule mirrors _compute_streak, which keeps a streak active if today
or yesterday has an entry, so one forgotten log is not a failure. If the model
learned a different notion of failure than the dashboard displays, its
predictions would contradict the rest of the app.

DESIGN — process simulation, same reasoning as the goal generator
Behaviour is simulated day by day and failure emerges from it, rather than the
label being sampled from a formula over features. Three mechanisms drive it:

  · momentum      — a run of good days makes the next one more likely, and a
                    slip makes another slip more likely. This is what creates
                    streaks rather than independent coin flips.
  · day-of-week   — weekends erode exercise and screen time for most people.
  · disruption    — illness or an exam week, invisible before it starts, which
                    is the irreducible uncertainty no model can anticipate.

Stdlib only, deterministic under --seed.

Usage (from backend_api/):
    python3 scripts/generate_synthetic_habits.py
    python3 scripts/generate_synthetic_habits.py --users 200 --days 240
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

# ── Scoring, mirrored from services/habit_analytics_service.py ───────────────
# Duplicated rather than imported so this script stays runnable standalone; the
# values must be kept in step with that module.
POSITIVE_THRESHOLD = 70.0
SLEEP_HEALTHY_RANGE = (7.0, 9.0)
EXERCISE_TARGET_MINUTES = 30.0
WATER_TARGET_LITERS = 2.0
SCREEN_TIME_HEALTHY_MAX = 6.0

# ── Generative parameters ────────────────────────────────────────────────────
# Momentum: how strongly yesterday's outcome shifts today's effort. This is what
# makes streaks a real phenomenon in the data instead of a run of coincidences.
MOMENTUM_GOOD = 0.16      # effort bonus after a good day
MOMENTUM_BAD = 0.26       # effort penalty after a bad day — slips hurt more
MOMENTUM_MEMORY = 0.55    # how much of the running momentum carries to tomorrow

# Weekends: exercise and screen time slip for most people.
WEEKEND_EFFORT_PENALTY = 0.12

# Disruption — illness, exams, travel. Invisible at prediction time until it
# starts, which is exactly the point.
DISRUPTION_PROBABILITY_PER_DAY = 0.006
DISRUPTION_LENGTH_DAYS = (3, 12)
DISRUPTION_EFFORT_MULTIPLIER = 0.45

# Logging: people stop recording when things go badly, so a gap is informative
# rather than missing-at-random.
LOG_PROBABILITY_BASE = 0.72
LOG_PROBABILITY_DISCIPLINE_SLOPE = 0.25
LOG_PROBABILITY_BAD_DAY_PENALTY = 0.18

HORIZON_DAYS = 7  # predict a break within the next week

GROUND_TRUTH = {
    "positive_threshold": POSITIVE_THRESHOLD,
    "momentum_good": MOMENTUM_GOOD,
    "momentum_bad": MOMENTUM_BAD,
    "momentum_memory": MOMENTUM_MEMORY,
    "weekend_effort_penalty": WEEKEND_EFFORT_PENALTY,
    "disruption_probability_per_day": DISRUPTION_PROBABILITY_PER_DAY,
    "disruption_length_days": DISRUPTION_LENGTH_DAYS,
    "disruption_effort_multiplier": DISRUPTION_EFFORT_MULTIPLIER,
    "log_probability_base": LOG_PROBABILITY_BASE,
    "horizon_days": HORIZON_DAYS,
    "discipline_distribution": "Beta(2.6, 2.2)",
    "notes": (
        "A break is a logged day below POSITIVE_THRESHOLD, or two consecutive "
        "unlogged days — mirroring _compute_streak in habit_analytics_service. "
        "Failure emerges from the simulated process; it is not sampled from a formula."
    ),
}


# ── Scoring helpers, mirroring habit_analytics_service ───────────────────────
def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _sleep_score(hours):
    low, high = SLEEP_HEALTHY_RANGE
    if low <= hours <= high:
        return 100.0
    return _clamp(100.0 - abs(hours - (low if hours < low else high)) * 25.0)


def _exercise_score(minutes):
    return _clamp(minutes / EXERCISE_TARGET_MINUTES * 100.0)


def _water_score(liters):
    return _clamp(liters / WATER_TARGET_LITERS * 100.0)


def _screen_score(hours):
    if hours <= SCREEN_TIME_HEALTHY_MAX:
        return 100.0
    return _clamp(100.0 - (hours - SCREEN_TIME_HEALTHY_MAX) * 20.0)


def daily_score(sleep, exercise, water, screen):
    return round(
        (_sleep_score(sleep) + _exercise_score(exercise) + _water_score(water) + _screen_score(screen)) / 4.0,
        2,
    )


@dataclass
class Day:
    index: int
    weekday: int
    logged: bool
    score: float | None   # None when not logged
    good: bool            # the ground truth, whether or not it was logged
    sleep: float
    exercise: float
    water: float
    screen: float


def simulate_user(rng: random.Random, days: int, discipline: float) -> list[Day]:
    """One user's daily sequence. Effort walks with momentum, and the biometric
    values follow from it."""
    out: list[Day] = []
    momentum = 0.0
    disruption_left = 0

    for i in range(days):
        weekday = i % 7
        if disruption_left == 0 and rng.random() < DISRUPTION_PROBABILITY_PER_DAY:
            disruption_left = rng.randint(*DISRUPTION_LENGTH_DAYS)

        effort = 0.55 + 0.75 * discipline + momentum
        if weekday >= 5:
            effort -= WEEKEND_EFFORT_PENALTY
        if disruption_left > 0:
            effort *= DISRUPTION_EFFORT_MULTIPLIER
            disruption_left -= 1

        e = _clamp(effort, 0.05, 1.6)
        sleep = _clamp(rng.gauss(5.6 + 2.6 * e, 0.85), 3.0, 11.0)
        exercise = max(0.0, rng.gauss(EXERCISE_TARGET_MINUTES * e, 12.0))
        water = max(0.2, rng.gauss(WATER_TARGET_LITERS * e, 0.55))
        screen = _clamp(rng.gauss(10.5 - 5.0 * e, 1.8), 0.5, 16.0)

        score = daily_score(sleep, exercise, water, screen)
        good = score >= POSITIVE_THRESHOLD

        # Momentum updates from what actually happened, not from what was logged.
        momentum = MOMENTUM_MEMORY * momentum + (MOMENTUM_GOOD if good else -MOMENTUM_BAD)
        momentum = _clamp(momentum, -0.45, 0.30)

        p_log = LOG_PROBABILITY_BASE + LOG_PROBABILITY_DISCIPLINE_SLOPE * discipline
        if not good:
            p_log -= LOG_PROBABILITY_BAD_DAY_PENALTY
        logged = rng.random() < p_log

        out.append(Day(i, weekday, logged, score if logged else None, good,
                       sleep, exercise, water, screen))
    return out


def _streak_before(days: list[Day], t: int) -> int:
    """Consecutive good *logged* days ending at t. Uses only the record, since
    that is all the serving path can see."""
    n = 0
    for d in reversed(days[: t + 1]):
        if d.logged and d.score is not None and d.score >= POSITIVE_THRESHOLD:
            n += 1
        else:
            break
    return n


def build_rows(user_id: str, days: list[Day], warmup: int = 21) -> list[dict]:
    """One row per prediction day. Features use only days <= t; the label looks
    at t+1 .. t+HORIZON, which is the future and must never leak into features."""
    rows = []
    for t in range(warmup, len(days) - HORIZON_DAYS):
        window = days[: t + 1]
        last7 = window[-7:]
        last14 = window[-14:]
        last30 = window[-30:]

        logged7 = [d for d in last7 if d.logged and d.score is not None]
        logged14 = [d for d in last14 if d.logged and d.score is not None]
        logged30 = [d for d in last30 if d.logged and d.score is not None]

        def adherence(bucket):
            return (sum(1 for d in bucket if d.score >= POSITIVE_THRESHOLD) / len(bucket)) if bucket else 0.0

        scores7 = [d.score for d in logged7]
        prev7 = [d.score for d in window[-14:-7] if d.logged and d.score is not None]

        # days since the last break, from the record
        since_break = 0
        for d in reversed(window):
            if d.logged and d.score is not None and d.score >= POSITIVE_THRESHOLD:
                since_break += 1
            else:
                break

        # LABEL: does the streak break in the next HORIZON days?
        #
        # A break is a logged day scoring below threshold, or two consecutive
        # days with no log at all. The two-day rule mirrors _compute_streak in
        # habit_analytics_service, which treats a streak as still active if
        # today *or yesterday* has a log — ordinary habit-tracker semantics, so
        # one forgotten entry is not a failure. Counting every single missing
        # log as a break made 71% of days positive and the label was really
        # measuring logging diligence rather than habit failure.
        horizon = days[t + 1 : t + 1 + HORIZON_DAYS]
        breaks = False
        consecutive_unlogged = 0
        for d in horizon:
            if d.logged:
                consecutive_unlogged = 0
                if d.score is not None and d.score < POSITIVE_THRESHOLD:
                    breaks = True
                    break
            else:
                consecutive_unlogged += 1
                if consecutive_unlogged >= 2:
                    breaks = True
                    break

        rows.append({
            "user_id": user_id,
            "day_index": t,
            # ── features ──
            "current_streak": _streak_before(window, t),
            "adherence_7d": round(adherence(logged7), 4),
            "adherence_14d": round(adherence(logged14), 4),
            "adherence_30d": round(adherence(logged30), 4),
            "mean_score_7d": round(statistics.fmean(scores7), 2) if scores7 else 0.0,
            "score_trend": round(
                (statistics.fmean(scores7) - statistics.fmean(prev7)) if scores7 and prev7 else 0.0, 2),
            "score_volatility_7d": round(statistics.pstdev(scores7), 2) if len(scores7) > 1 else 0.0,
            "missed_logs_7d": sum(1 for d in last7 if not d.logged),
            "missed_logs_30d": sum(1 for d in last30 if not d.logged),
            "days_since_break": since_break,
            "mean_sleep_7d": round(statistics.fmean([d.sleep for d in logged7]), 2) if logged7 else 0.0,
            "mean_exercise_7d": round(statistics.fmean([d.exercise for d in logged7]), 1) if logged7 else 0.0,
            "mean_screen_7d": round(statistics.fmean([d.screen for d in logged7]), 2) if logged7 else 0.0,
            "is_weekend_next": 1 if (days[t + 1].weekday >= 5) else 0,
            # ── label ──
            "breaks_within_7d": int(breaks),
        })
    return rows


def generate(users: int, days: int, seed: int):
    rng = random.Random(seed)
    rows = []
    for u in range(users):
        discipline = rng.betavariate(2.6, 2.2)
        seq = simulate_user(rng, days, discipline)
        rows.extend(build_rows(f"habit-user-{u:04d}", seq))
    meta = {
        "seed": seed, "n_users": users, "days_per_user": days, "n_rows": len(rows),
        "break_rate": round(sum(r["breaks_within_7d"] for r in rows) / len(rows), 4),
        "ground_truth": GROUND_TRUTH,
    }
    return rows, meta


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic habit histories.")
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--seed", type=int, default=20260908)
    ap.add_argument("--out", default="data/synthetic")
    args = ap.parse_args()

    rows, meta = generate(args.users, args.days, args.seed)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    with (out / "habits.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    (out / "habits_ground_truth.json").write_text(json.dumps(meta, indent=2))

    n = len(rows); pos = sum(r["breaks_within_7d"] for r in rows)
    print(f"generated {n:,} prediction-days across {args.users} users ({args.days} days each)")
    print(f"  breaks within {HORIZON_DAYS}d : {pos:,} ({pos/n:.1%})")
    print(f"  base-rate baseline    : {max(pos, n-pos)/n:.1%} accuracy\n")

    print("  break rate by current streak length:")
    for lo, hi, lbl in [(0,0,"0 (already broken)"),(1,2,"1-2"),(3,6,"3-6"),(7,13,"7-13"),(14,999,"14+")]:
        sub = [r for r in rows if lo <= r["current_streak"] <= hi]
        if sub:
            print(f"    {lbl:<20}{len(sub):>7,} days   {sum(r['breaks_within_7d'] for r in sub)/len(sub):>6.1%}")

    print("\n  break rate by missed logs in last 7 days:")
    for m in range(0, 5):
        sub = [r for r in rows if r["missed_logs_7d"] == m]
        if sub:
            print(f"    {m} missed{'':<13}{len(sub):>7,} days   {sum(r['breaks_within_7d'] for r in sub)/len(sub):>6.1%}")

    print(f"\nwrote {out/'habits.csv'}")
    print(f"wrote {out/'habits_ground_truth.json'}")


if __name__ == "__main__":
    main()
