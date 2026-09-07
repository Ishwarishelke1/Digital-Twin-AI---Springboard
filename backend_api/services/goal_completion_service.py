"""
services/goal_completion_service.py — Serves goal-completion probabilities.

Loads the artifact written by scripts/train_goal_model.py, builds the same
feature vector from a *real* goal, and returns a calibrated probability.

TWO THINGS THIS DELIBERATELY REFUSES TO DO

1. Predict without enough history. A goal created yesterday with no
   contributions has no signal; returning "34%" for it would be inventing a
   number. Below the thresholds here the service returns a reason instead,
   which the UI shows in place of a figure. This is the design document's
   refusal principle applied concretely: "I don't have enough information" is a
   first-class answer, not an error.

2. Hide its provenance. The model is trained on synthetic data, so every
   response carries trained_on="synthetic". The frontend surfaces that. A
   probability whose origin is invisible invites more trust than it has earned.

The service degrades to None if the artifact is missing rather than raising —
the app must start and run without a trained model present.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from beanie import PydanticObjectId

from models.enums import TransactionType
from models.finance import FinancialRecord
from models.habit import HabitTracking
from models.study import StudyActivity
from models.user import ActiveGoal, User

logger = logging.getLogger("digital_twin_ai.goal_completion")

_ARTIFACT_PATH = Path(__file__).resolve().parent.parent / "models_store" / "goal_completion.joblib"
_artifact = None
_load_attempted = False

# Sufficiency thresholds. Below any of these the goal has too little history for
# a prediction to mean anything.
MIN_DAYS_ELAPSED = 3
MIN_DURATION_DAYS = 7

CATEGORY_COLUMNS = ["cat_CAREER", "cat_FINANCE", "cat_FITNESS", "cat_HABIT", "cat_STUDY"]


@dataclass
class GoalPrediction:
    goal_id: str
    probability: Optional[float]
    reason: Optional[str]          # populated when probability is None
    trained_on: str
    model_ece: Optional[float]

    def as_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "probability": self.probability,
            "reason": self.reason,
            "trained_on": self.trained_on,
            "model_ece": self.model_ece,
        }


def _load():
    """Lazy, cached, and non-fatal — a missing artifact must not break startup."""
    global _artifact, _load_attempted
    if _load_attempted:
        return _artifact
    _load_attempted = True
    try:
        import joblib

        _artifact = joblib.load(_ARTIFACT_PATH)
        logger.info("Loaded goal-completion model (trained_on=%s).", _artifact.get("trained_on"))
    except FileNotFoundError:
        logger.info("No goal-completion model at %s; predictions disabled.", _ARTIFACT_PATH)
        _artifact = None
    except Exception:
        logger.exception("Failed to load goal-completion model; predictions disabled.")
        _artifact = None
    return _artifact


def _f(value) -> float:
    return float(value) if isinstance(value, Decimal) else float(value or 0.0)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _contribution_stats(user_id: PydanticObjectId, goal_id: str, now: datetime):
    """Count and recency of linked contributions, across all three sources.

    A goal's progress can come from a finance transaction, a study session or a
    habit log — all three call goal_progress_service.adjust_active_goal_progress
    when they carry a linked_goal_id. Counting only financial records (as this
    did originally) reported contribution_count = 0 for an actively-worked study
    or habit goal, which the model reads as a manually-tracked or abandoned goal.
    Finance goals were unaffected, so the defect was invisible until a STUDY goal
    was tested.
    """
    finance = await FinancialRecord.find(
        FinancialRecord.user_id == user_id,
        FinancialRecord.linked_goal_id == goal_id,
    ).to_list()
    # Only deposits and investments move a goal forward — GOAL_PROGRESS_TYPES in
    # finance_service. An expense linked to a goal is not progress toward it.
    dates = [
        _aware(r.transaction_date)
        for r in finance
        if r.type in (TransactionType.SAVINGS_DEPOSIT, TransactionType.INVESTMENT)
    ]

    study = await StudyActivity.find(
        StudyActivity.user_id == user_id,
        StudyActivity.linked_goal_id == goal_id,
    ).to_list()
    dates += [_aware(r.session_date) for r in study]

    habits = await HabitTracking.find(
        HabitTracking.user_id == user_id,
        HabitTracking.linked_goal_id == goal_id,
    ).to_list()
    dates += [_aware(r.log_date) for r in habits]

    if not dates:
        return 0, None
    return len(dates), (now - max(dates)).days


def _prior_completion_rate(user: User, exclude_goal_id: str) -> float:
    others = [g for g in user.active_goals if g.goal_id != exclude_goal_id]
    if not others:
        return 0.5  # population prior — no personal evidence yet
    completed = sum(1 for g in others if g.completed_at is not None)
    return completed / len(others)


async def predict_for_goal(user: User, goal: ActiveGoal) -> GoalPrediction:
    artifact = _load()
    if artifact is None:
        return GoalPrediction(goal.goal_id, None, "No trained model available.", "none", None)

    trained_on = artifact.get("trained_on", "unknown")
    ece = (artifact.get("metrics") or {}).get("ece")

    if goal.completed_at is not None:
        return GoalPrediction(goal.goal_id, None, "Already completed.", trained_on, ece)

    now = datetime.now(timezone.utc)
    created = goal.created_at or now
    target_date = goal.target_date
    for dt_name, dt in (("created", created), ("target", target_date)):
        if dt.tzinfo is None:
            if dt_name == "created":
                created = dt.replace(tzinfo=timezone.utc)
            else:
                target_date = dt.replace(tzinfo=timezone.utc)

    duration_days = (target_date - created).days
    days_elapsed = (now - created).days
    days_remaining = (target_date - now).days

    # ── sufficiency gate ─────────────────────────────────────────────────────
    if duration_days < MIN_DURATION_DAYS:
        return GoalPrediction(goal.goal_id, None, "Goal window is too short to model.", trained_on, ece)
    if days_elapsed < MIN_DAYS_ELAPSED:
        return GoalPrediction(
            goal.goal_id, None,
            f"Needs at least {MIN_DAYS_ELAPSED} days of history — this goal is {max(days_elapsed, 0)} day(s) old.",
            trained_on, ece,
        )
    if days_remaining <= 0:
        return GoalPrediction(goal.goal_id, None, "Deadline has passed.", trained_on, ece)

    target = _f(goal.target_value)
    current = _f(goal.current_value)
    if target <= 0:
        return GoalPrediction(goal.goal_id, None, "Goal has no positive target.", trained_on, ece)

    required_daily_original = target / duration_days
    observed_daily = current / max(days_elapsed, 1)
    remaining = max(0.0, target - current)
    required_daily_remaining = remaining / days_remaining

    n_contrib, days_since_last = await _contribution_stats(user.id, goal.goal_id, now)
    if days_since_last is None:
        days_since_last = days_elapsed

    competing = sum(1 for g in user.active_goals if g.goal_id != goal.goal_id and g.completed_at is None)

    features = {
        "progress_ratio": current / target,
        "time_elapsed_ratio": days_elapsed / duration_days,
        "rate_ratio": observed_daily / required_daily_original if required_daily_original else 0.0,
        "required_rate_multiple": min(required_daily_remaining / required_daily_original, 20.0)
        if required_daily_original else 20.0,
        "days_remaining": days_remaining,
        "duration_days": duration_days,
        "log_target_value": math.log10(max(target, 1.0)),
        "competing_goals": competing,
        "contribution_count": n_contrib,
        "days_since_last_contribution": days_since_last,
        "user_prior_completion_rate": _prior_completion_rate(user, goal.goal_id),
    }
    for col in CATEGORY_COLUMNS:
        features[col] = 1.0 if col == f"cat_{goal.category.value}" else 0.0

    names = artifact["feature_names"]
    missing = [n for n in names if n not in features]
    if missing:
        # Fail loudly in logs, quietly to the user — a silently mis-aligned
        # feature vector produces a confident, meaningless number.
        logger.error("Feature mismatch for goal %s; missing %s", goal.goal_id, missing)
        return GoalPrediction(goal.goal_id, None, "Model feature mismatch.", trained_on, ece)

    # ── out-of-distribution gate ─────────────────────────────────────────────
    # A linear model extrapolates past its training range silently and with high
    # confidence. A real goal tracked without linked transactions has
    # contribution_count = 0, which never occurs in the synthetic training data
    # (range [3, 105]) — and the model returned 99.8% for it. Refusing is the
    # correct answer: the model genuinely has no basis for that input.
    ranges = artifact.get("feature_ranges") or {}
    outside = []
    for name in names:
        bounds = ranges.get(name)
        if not bounds:
            continue
        lo, hi = bounds["min"], bounds["max"]
        if hi <= lo:
            continue
        value = float(features[name])
        # Tolerate a margin either side; flag only material excursions.
        span = hi - lo
        if value < lo - 0.25 * span or value > hi + 0.25 * span:
            outside.append(name)

    if outside:
        logger.info(
            "Goal %s outside training distribution on %s; refusing to predict.",
            goal.goal_id, ", ".join(outside),
        )
        readable = {
            "contribution_count": "no linked transactions recorded for this goal",
            "days_since_last_contribution": "no recent linked activity",
        }
        detail = readable.get(outside[0], f"{outside[0]} is outside the model's trained range")
        return GoalPrediction(
            goal.goal_id, None,
            f"Not enough comparable history — {detail}.",
            trained_on, ece,
        )

    vector = [[float(features[n]) for n in names]]
    probability = float(artifact["model"].predict_proba(vector)[0][1])
    return GoalPrediction(goal.goal_id, round(probability, 4), None, trained_on, ece)


async def predict_for_user(user: User) -> list[GoalPrediction]:
    return [await predict_for_goal(user, g) for g in user.active_goals]
