"""
services/simulation_service.py — Decision Simulation & Recommendation Engine (Milestone 3).

Composes the three existing analytics engines rather than re-querying MongoDB directly:
  - services.forecast_service.forecast_service        (Finance: income/expense baseline)
  - services.productivity_service.productivity_service (Study: weekly hours/productivity baseline)
  - services.habit_analytics_service.habit_analytics_service (Fitness: sleep/exercise/water/screen baseline)

For each domain it generates several what-if scenarios (deltas applied to the real baseline),
scores every scenario with one shared, domain-agnostic multi-factor scoring function
(`_score_scenarios`), and persists both the Simulation and its top Recommendation.

Small per-domain scoring formulas (hours -> productivity contribution, exercise/sleep -> habit
score) are duplicated here in miniature from productivity_service.py / habit_analytics_service.py
rather than imported, mirroring the existing precedent (see trend_prediction_service.py's
docstring) of keeping engines decoupled from each other's private internals.

All pure math lives in module-level functions (no Beanie/Mongo) so it is unit-testable
without a live database. DecisionSimulationService only orchestrates:
fetch baselines -> build scenarios -> score -> persist -> return schema.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from beanie import PydanticObjectId

from core.exceptions import BusinessRuleError, NotFoundError
from models.enums import GoalCategory, Priority, RecommendationCategory, RiskTolerance, SimulationDomain, UserFeedback
from models.simulation import MetricPoint, Recommendation, ScenarioResult, Simulation
from models.user import ActiveGoal, User
from schemas.simulation_schema import (
    DomainComparisonResponse,
    FitnessScenarioRequest,
    FinanceScenarioRequest,
    HybridScenarioRequest,
    MetricPointResponse,
    RecommendationResponse,
    ScenarioResultResponse,
    SimulationDetailResponse,
    SimulationHistoryItem,
    SimulationResponse,
    StudyScenarioRequest,
)
from services.forecast_service import forecast_service
from services.habit_analytics_service import habit_analytics_service
from services.productivity_service import productivity_service

WEEKS_PER_MONTH = 4.345

# ─── Finance scenario presets ──────────────────────────────────────────────────
DEFAULT_FINANCE_EXPENSE_REDUCTION_STRETCH_PCT = 10.0
FINANCE_SCENARIO_MULTIPLIERS = [(0.0, "Current Plan"), (1.0, "Target Plan"), (1.5, "Stretch Plan")]

# ─── Study scenario presets ─────────────────────────────────────────────────────
DEFAULT_STUDY_HOURS_STRETCH = 3.0
STUDY_SCENARIO_MULTIPLIERS = [(0.0, "Current Pace"), (1.0, "Target Pace"), (1.5, "Stretch Pace")]
WEEKLY_STUDY_HOURS_BENCHMARK = 14.0   # ~2 hrs/day, mirrors productivity_service.STUDY_HOURS_BENCHMARK * 7
HOURS_SCORE_WEIGHT = 0.20             # mirrors PRODUCTIVITY_WEIGHTS["hours"] in productivity_service.py

# ─── Fitness scenario presets ───────────────────────────────────────────────────
DEFAULT_FITNESS_EXERCISE_STRETCH_MINUTES = 30.0
FITNESS_SCENARIO_MULTIPLIERS = [(0.0, "Current Routine"), (1.0, "Target Routine"), (1.5, "Stretch Routine")]
EXERCISE_TARGET_MINUTES = 30.0
SLEEP_HEALTHY_RANGE = (7.0, 9.0)
WATER_TARGET_LITERS = 2.0
SCREEN_TIME_HEALTHY_MAX = 6.0

# ─── Recommendation engine weights ─────────────────────────────────────────────
# Per-domain scenario scoring shifts by the user's own risk_tolerance (Profile.risk_tolerance,
# defaults to MODERATE, which reproduces the pre-existing 50/30/20 constants and pre-existing
# recommendations unchanged for any user who never set a preference).
#
# Two independent mechanisms, because one alone isn't enough: every scenario set here is built
# as Current/Target/Stretch with strictly-increasing deltas (more saving, more study hours, more
# exercise), so the Stretch scenario's outcome AND goal-progress are, by construction, never worse
# than Target's or Current's. Re-weighting outcome/goal-impact/confidence alone (RISK_TOLERANCE_
# WEIGHTS below) therefore never changes which scenario wins — it only rescales the displayed
# score uniformly (verified: with a fixed 3-scenario input, every weight row in this table picks
# the same argmax). What actually lets a conservative user land on a smaller scenario is
# RISK_STRETCH_PENALTY: a penalty proportional to each scenario's own "stretch" (how far its
# delta is from the 0.0-multiplier baseline, e.g. Stretch Plan's multiplier 1.5 vs Current Plan's
# 0.0 — see _RawScenario.intensity), applied to its outcome ratio before scoring. This only
# flips the winner when the marginal gain from Target to Stretch is already thin relative to how
# much bigger an ask Stretch is (diminishing returns) — a real Stretch improvement with no
# plateau still wins even for a conservative user, which is the correct behavior: there's no
# genuine risk being asked of them when the numbers keep climbing cleanly.
RISK_TOLERANCE_WEIGHTS: dict[RiskTolerance, tuple[float, float, float]] = {
    # (outcome_weight, goal_impact_weight, confidence_weight) — each row sums to 1.0
    RiskTolerance.CONSERVATIVE: (0.3, 0.3, 0.4),
    RiskTolerance.MODERATE: (0.5, 0.3, 0.2),
    RiskTolerance.AGGRESSIVE: (0.65, 0.25, 0.1),
}
RISK_STRETCH_PENALTY: dict[RiskTolerance, float] = {
    # Subtracted from a scenario's outcome_ratio, scaled by its intensity (0=baseline, 1=max
    # stretch offered in this domain) and clamped back into [0, 1]. CONSERVATIVE is penalized
    # (pulls big-ask scenarios down when their edge over a smaller ask is thin), MODERATE is
    # exactly 0.0 (today's unmodified behavior), AGGRESSIVE is a small negative penalty — a
    # bonus that nudges bigger-ask scenarios up further on close calls.
    RiskTolerance.CONSERVATIVE: 0.6,
    RiskTolerance.MODERATE: 0.0,
    RiskTolerance.AGGRESSIVE: -0.15,
}
OUTCOME_WEIGHT, GOAL_IMPACT_WEIGHT, CONFIDENCE_WEIGHT = RISK_TOLERANCE_WEIGHTS[RiskTolerance.MODERATE]


# ─── Pure helpers: generic min-max scoring (no I/O — unit-tested directly) ────

def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _normalize_optional(values: list[Optional[float]], higher_is_better: bool) -> list[float]:
    """Min-max normalizes the present values into [0, 1]; missing (None) entries get
    a neutral 0.5 (no goal data to judge them by), and a single present value or a
    flat set of values also gets a neutral-but-not-punishing 1.0/0.5 fallback."""
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    result = [0.5] * len(values)
    if not present:
        return result
    vals = [v for _, v in present]
    lo, hi = min(vals), max(vals)
    for i, v in present:
        if hi == lo:
            result[i] = 1.0 if len(present) == 1 else 0.5
        else:
            result[i] = (v - lo) / (hi - lo) if higher_is_better else (hi - v) / (hi - lo)
    return result


def _score_scenarios(
    primary_values: list[float],
    goal_months: list[Optional[float]],
    confidence: float,
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    scenario_intensity: Optional[list[float]] = None,
) -> list[float]:
    """Shared multi-factor recommendation score (0-100) for every domain: a blend of relative
    outcome improvement within this scenario set, relative goal-completion impact (fewer months
    remaining scores higher; no matching goal is scored neutral), and confidence in the underlying
    data the scenario was projected from. The three weights come from RISK_TOLERANCE_WEIGHTS,
    keyed by the user's own Profile.risk_tolerance (MODERATE — the default for any user who
    hasn't set one — reproduces the original fixed 50/30/20 split).

    scenario_intensity (parallel to primary_values, each in roughly [0, 1] — see
    _RawScenario.intensity) lets RISK_STRETCH_PENALTY pull a scenario's outcome_ratio down
    (CONSERVATIVE) or nudge it up (AGGRESSIVE) in proportion to how big an ask it represents,
    before the weighted blend below runs. Omit it (None, the default) to skip this entirely —
    every existing caller/test that predates risk-aware scoring is unaffected."""
    outcome_weight, goal_impact_weight, confidence_weight = RISK_TOLERANCE_WEIGHTS[risk_tolerance]
    outcome_ratios = _normalize_optional(list(primary_values), higher_is_better=True)
    goal_ratios = _normalize_optional(goal_months, higher_is_better=False)
    penalty = RISK_STRETCH_PENALTY[risk_tolerance]
    if scenario_intensity is not None and penalty != 0.0:
        outcome_ratios = [
            _clamp(o - penalty * intensity, 0.0, 1.0) for o, intensity in zip(outcome_ratios, scenario_intensity)
        ]
    return [
        round(100 * (outcome_weight * o + goal_impact_weight * g + confidence_weight * confidence), 2)
        for o, g in zip(outcome_ratios, goal_ratios)
    ]


def _estimate_months_to_goal(current_value: float, target_value: float, monthly_rate: float) -> Optional[float]:
    """0 if already met, None if unreachable at this rate, else months (fractional)."""
    remaining = target_value - current_value
    if remaining <= 0:
        return 0.0
    if monthly_rate <= 0:
        return None
    return round(remaining / monthly_rate, 2)


def _average_months_to_goals(
    goals: list[ActiveGoal], monthly_rate: float
) -> Optional[float]:
    """Averages estimated months-to-completion across active goals in one category.
    A goal already met counts as 0 months remaining (pulling the average down, since
    it reflects a real completed goal); only goals unreachable at this rate are
    excluded (None). Returns None if there are no active goals at all, or every
    goal is unreachable, so the scenario is scored neutrally instead of punished."""
    estimates = []
    for g in goals:
        months = _estimate_months_to_goal(float(g.current_value), float(g.target_value), monthly_rate)
        if months is not None:
            estimates.append(months)
    if not estimates:
        return None
    return round(sum(estimates) / len(estimates), 2)


# ─── Finance: pure scenario math ───────────────────────────────────────────────

def _finance_scenario_deltas(
    additional_monthly_saving: float, expense_reduction_pct: float
) -> list[tuple[str, float, float, float]]:
    """When the caller doesn't specify any target delta, fall back to a modest
    stretch goal (10% expense reduction) so the scenario set isn't degenerate.
    The trailing float is the raw multiplier (0.0/1.0/1.5) — see _RawScenario.intensity."""
    if additional_monthly_saving == 0 and expense_reduction_pct == 0:
        expense_reduction_pct = DEFAULT_FINANCE_EXPENSE_REDUCTION_STRETCH_PCT
    return [
        (name, additional_monthly_saving * m, expense_reduction_pct * m, m)
        for m, name in FINANCE_SCENARIO_MULTIPLIERS
    ]


def _finance_scenario_outcome(
    baseline_income: float, baseline_expense: float, additional_saving: float,
    expense_reduction_pct: float, months_ahead: int,
) -> tuple[float, float]:
    """Returns (monthly_saving, future_saving) for one finance scenario."""
    reduced_expense = baseline_expense * (1 - expense_reduction_pct / 100.0)
    monthly_saving = (baseline_income - reduced_expense) + additional_saving
    future_saving = monthly_saving * months_ahead
    return round(monthly_saving, 2), round(future_saving, 2)


# ─── Study: pure scenario math ─────────────────────────────────────────────────

def _study_scenario_deltas(additional_weekly_study_hours: float) -> list[tuple[str, float, float]]:
    """The trailing float is the raw multiplier (0.0/1.0/1.5) — see _RawScenario.intensity."""
    hours = additional_weekly_study_hours if additional_weekly_study_hours > 0 else DEFAULT_STUDY_HOURS_STRETCH
    return [(name, hours * m, m) for m, name in STUDY_SCENARIO_MULTIPLIERS]


def _study_scenario_outcome(
    baseline_score: float, baseline_weekly_hours: float, delta_hours: float
) -> tuple[float, float]:
    """Returns (projected_productivity_score, new_weekly_hours). Recomputes only the
    'hours' component of the composite productivity score (see PRODUCTIVITY_WEIGHTS
    in productivity_service.py) against a full-marks weekly-hours benchmark."""
    new_weekly_hours = max(0.0, baseline_weekly_hours + delta_hours)
    baseline_component = min(1.0, baseline_weekly_hours / WEEKLY_STUDY_HOURS_BENCHMARK)
    new_component = min(1.0, new_weekly_hours / WEEKLY_STUDY_HOURS_BENCHMARK)
    score_delta = (new_component - baseline_component) * HOURS_SCORE_WEIGHT * 100
    return round(_clamp(baseline_score + score_delta), 2), round(new_weekly_hours, 2)


# ─── Fitness: pure scenario math (mirrors habit_analytics_service's 4D scoring) ─

def _fitness_scenario_deltas(
    additional_exercise_minutes: float, sleep_adjustment_hours: float
) -> list[tuple[str, float, float, float]]:
    """The trailing float is the raw multiplier (0.0/1.0/1.5) — see _RawScenario.intensity."""
    exercise = additional_exercise_minutes if additional_exercise_minutes > 0 else DEFAULT_FITNESS_EXERCISE_STRETCH_MINUTES
    sleep = sleep_adjustment_hours
    return [(name, exercise * m, sleep * m, m) for m, name in FITNESS_SCENARIO_MULTIPLIERS]


def _sleep_score(hours: float) -> float:
    lo, hi = SLEEP_HEALTHY_RANGE
    if lo <= hours <= hi:
        return 100.0
    deficit_or_excess = (lo - hours) if hours < lo else (hours - hi)
    return _clamp(100.0 - deficit_or_excess * 25.0)


def _exercise_score(minutes: float) -> float:
    return _clamp((minutes / EXERCISE_TARGET_MINUTES) * 100.0)


def _water_score(liters: float) -> float:
    return _clamp((liters / WATER_TARGET_LITERS) * 100.0)


def _screen_time_score(hours: float) -> float:
    if hours <= SCREEN_TIME_HEALTHY_MAX:
        return 100.0
    excess = hours - SCREEN_TIME_HEALTHY_MAX
    return _clamp(100.0 - excess * 20.0)


def _fitness_scenario_outcome(
    baseline_sleep: float, baseline_exercise: float, baseline_water: float, baseline_screen: float,
    exercise_delta: float, sleep_delta: float,
) -> tuple[float, float, float]:
    """Returns (projected_habit_score, new_exercise_minutes, new_sleep_hours)."""
    new_exercise = max(0.0, baseline_exercise + exercise_delta)
    new_sleep = max(0.0, baseline_sleep + sleep_delta)
    scores = [
        _sleep_score(new_sleep),
        _exercise_score(new_exercise),
        _water_score(baseline_water),
        _screen_time_score(baseline_screen),
    ]
    habit_score = round(sum(scores) / len(scores), 2)
    return habit_score, round(new_exercise, 2), round(new_sleep, 2)


# ─── DecisionSimulationService ─────────────────────────────────────────────────

@dataclass
class _RawScenario:
    name: str
    deltas: dict[str, float]
    metrics: list[MetricPoint]
    primary_metric_label: str
    primary_metric_value: float
    goal_months: Optional[float]
    confidence_score: float
    intensity: float = 0.0  # 0.0 = baseline (no ask), 1.0 = the biggest ask offered in this domain


def _build_recommendation_text(domain_label: str, best: _RawScenario, baseline_name: str) -> tuple[str, str]:
    if best.name == baseline_name:
        title = f"Continue with your current {domain_label} plan."
        reason = f"Your current plan already provides the best available outcome among the simulated scenarios."
        return title, reason
    title = f"Recommended: {best.name}"
    reason = (
        f"{best.name} results in a {best.primary_metric_label.lower()} of "
        f"{best.primary_metric_value:,.2f}, the strongest outcome among the simulated scenarios."
    )
    if best.goal_months is not None:
        reason += f" It also brings your linked goal(s) to an estimated {best.goal_months:.1f} months to completion."
    return title, reason


class DecisionSimulationService:
    # ── Finance ─────────────────────────────────────────────────────────────
    async def simulate_finance_scenarios(
        self, user_id: str, request: FinanceScenarioRequest, persist: bool = True
    ) -> SimulationResponse:
        uid = PydanticObjectId(user_id)
        user = await User.get(uid)
        if not user:
            raise NotFoundError("User", user_id)

        income_resp, expense_resp = await asyncio.gather(
            forecast_service.project_income(user_id, months_ahead=1),
            forecast_service.project_expenses(user_id, months_ahead=1),
        )
        baseline_income = float(income_resp.projections[0].projected_amount) if income_resp.projections else 0.0
        baseline_expense = float(expense_resp.projections[0].projected_amount) if expense_resp.projections else 0.0
        confidence = round((income_resp.confidence_score + expense_resp.confidence_score) / 2, 2)

        finance_goals = [g for g in user.active_goals if g.category == GoalCategory.FINANCE]

        max_multiplier = max(m for m, _ in FINANCE_SCENARIO_MULTIPLIERS)
        raw_scenarios: list[_RawScenario] = []
        for name, additional_saving, expense_reduction_pct, multiplier in _finance_scenario_deltas(
            request.additional_monthly_saving, request.expense_reduction_pct
        ):
            monthly_saving, future_saving = _finance_scenario_outcome(
                baseline_income, baseline_expense, additional_saving, expense_reduction_pct, request.months_ahead
            )
            goal_months = _average_months_to_goals(finance_goals, monthly_saving)
            raw_scenarios.append(
                _RawScenario(
                    name=name,
                    deltas={"additional_monthly_saving": additional_saving, "expense_reduction_pct": expense_reduction_pct},
                    metrics=[
                        MetricPoint(label="Monthly Saving", value=monthly_saving, unit="INR"),
                        MetricPoint(label="Future Saving", value=future_saving, unit="INR"),
                    ],
                    primary_metric_label="Future Saving",
                    primary_metric_value=future_saving,
                    goal_months=goal_months,
                    confidence_score=confidence,
                    intensity=multiplier / max_multiplier,
                )
            )

        return await self._finalize(
            user_id, SimulationDomain.FINANCE, RecommendationCategory.FINANCE,
            request.model_dump(), raw_scenarios, baseline_name="Current Plan", persist=persist,
            risk_tolerance=user.profile.risk_tolerance,
        )

    # ── Study ───────────────────────────────────────────────────────────────
    async def simulate_study_scenarios(
        self, user_id: str, request: StudyScenarioRequest, persist: bool = True
    ) -> SimulationResponse:
        uid = PydanticObjectId(user_id)
        user = await User.get(uid)
        if not user:
            raise NotFoundError("User", user_id)

        score_resp, weekly_resp, prediction_resp = await asyncio.gather(
            productivity_service.get_productivity_score(user_id),
            productivity_service.get_weekly_trend(user_id, weeks_back=4),
            productivity_service.predict_performance(user_id, weeks_ahead=request.weeks_ahead),
        )
        active_weeks = [w for w in weekly_resp.trend if w.session_count > 0]
        baseline_weekly_hours = active_weeks[-1].total_study_hours if active_weeks else 0.0
        # Baseline is the trend-projected score at the user-selected horizon (not
        # today's live score) — otherwise "Simulation Period" (weeks_ahead) would be
        # a validated request field with no effect on the projected outcome at all.
        # Falls back to today's live score when there isn't enough history to trend
        # forward (predict_performance returns an empty projection list).
        baseline_score = (
            prediction_resp.predicted_productivity[-1].projected_score
            if prediction_resp.predicted_productivity
            else score_resp.productivity_score
        )
        confidence = prediction_resp.productivity_confidence_score

        study_goals = [g for g in user.active_goals if g.category == GoalCategory.STUDY]

        max_multiplier = max(m for m, _ in STUDY_SCENARIO_MULTIPLIERS)
        raw_scenarios: list[_RawScenario] = []
        for name, delta_hours, multiplier in _study_scenario_deltas(request.additional_weekly_study_hours):
            projected_score, new_weekly_hours = _study_scenario_outcome(baseline_score, baseline_weekly_hours, delta_hours)
            monthly_rate = new_weekly_hours * WEEKS_PER_MONTH
            goal_months = _average_months_to_goals(study_goals, monthly_rate)
            raw_scenarios.append(
                _RawScenario(
                    name=name,
                    deltas={"additional_weekly_study_hours": delta_hours},
                    metrics=[
                        MetricPoint(label="Weekly Study Hours", value=new_weekly_hours, unit="hrs"),
                        MetricPoint(label="Projected Productivity Score", value=projected_score, unit="pts"),
                    ],
                    primary_metric_label="Projected Productivity Score",
                    primary_metric_value=projected_score,
                    goal_months=goal_months,
                    confidence_score=confidence,
                    intensity=multiplier / max_multiplier,
                )
            )

        return await self._finalize(
            user_id, SimulationDomain.ACADEMIC, RecommendationCategory.ACADEMIC,
            request.model_dump(), raw_scenarios, baseline_name="Current Pace", persist=persist,
            risk_tolerance=user.profile.risk_tolerance,
        )

    # ── Fitness ─────────────────────────────────────────────────────────────
    async def simulate_fitness_scenarios(
        self, user_id: str, request: FitnessScenarioRequest, persist: bool = True
    ) -> SimulationResponse:
        uid = PydanticObjectId(user_id)
        user = await User.get(uid)
        if not user:
            raise NotFoundError("User", user_id)

        trend = await habit_analytics_service.get_habit_trend(user_id, weeks_back=4)
        active_weeks = [w for w in trend.weekly if w.days_logged > 0]
        latest = active_weeks[-1] if active_weeks else None
        baseline_sleep = latest.average_sleep_hours if latest else 0.0
        baseline_exercise = latest.average_exercise_minutes if latest else 0.0
        baseline_water = latest.average_water_intake_liters if latest else 0.0
        baseline_screen = latest.average_screen_time_hours if latest else 0.0
        days_logged = latest.days_logged if latest else 0
        # Simple data-volume confidence, mirroring the shape (not the exact curve) used by
        # forecast_service._compute_confidence — this domain has no forward-forecast method
        # of its own to borrow a confidence score from.
        confidence = round(min(0.95, 0.2 + 0.15 * min(days_logged, 5)), 2)

        fitness_goals = [g for g in user.active_goals if g.category in (GoalCategory.HABIT, GoalCategory.FITNESS)]

        max_multiplier = max(m for m, _ in FITNESS_SCENARIO_MULTIPLIERS)
        raw_scenarios: list[_RawScenario] = []
        for name, exercise_delta, sleep_delta, multiplier in _fitness_scenario_deltas(
            request.additional_exercise_minutes, request.sleep_adjustment_hours
        ):
            habit_score, new_exercise, new_sleep = _fitness_scenario_outcome(
                baseline_sleep, baseline_exercise, baseline_water, baseline_screen, exercise_delta, sleep_delta
            )
            monthly_rate = new_exercise * 30
            goal_months = _average_months_to_goals(fitness_goals, monthly_rate)
            # habit_analytics_service has no forward-trend method of its own to project
            # a horizon-adjusted habit_score from (unlike study's predict_performance),
            # so weeks_ahead is applied here instead as a genuine cumulative projection
            # — total exercise minutes over the user-selected horizon at the new daily
            # rate — the same "rate x horizon" shape finance's months_ahead already uses
            # for Future Saving.
            cumulative_exercise_minutes = round(new_exercise * 7 * request.weeks_ahead, 2)
            raw_scenarios.append(
                _RawScenario(
                    name=name,
                    deltas={"additional_exercise_minutes": exercise_delta, "sleep_adjustment_hours": sleep_delta},
                    metrics=[
                        MetricPoint(label="Daily Exercise", value=new_exercise, unit="min"),
                        MetricPoint(label="Daily Sleep", value=new_sleep, unit="hrs"),
                        MetricPoint(label="Projected Habit Score", value=habit_score, unit="pts"),
                        MetricPoint(
                            label=f"Exercise Over {request.weeks_ahead} Weeks",
                            value=cumulative_exercise_minutes,
                            unit="min",
                        ),
                    ],
                    primary_metric_label="Projected Habit Score",
                    primary_metric_value=habit_score,
                    goal_months=goal_months,
                    confidence_score=confidence,
                    intensity=multiplier / max_multiplier,
                )
            )

        return await self._finalize(
            user_id, SimulationDomain.HABIT, RecommendationCategory.FITNESS,
            request.model_dump(), raw_scenarios, baseline_name="Current Routine", persist=persist,
            risk_tolerance=user.profile.risk_tolerance,
        )

    # ── Hybrid (combines all three domains into named lifestyle scenarios) ──
    async def simulate_hybrid_scenarios(
        self, user_id: str, request: HybridScenarioRequest
    ) -> SimulationResponse:
        user = await User.get(PydanticObjectId(user_id))
        if not user:
            raise NotFoundError("User", user_id)

        finance_req = FinanceScenarioRequest(
            additional_monthly_saving=request.additional_monthly_saving,
            months_ahead=request.months_ahead,
        )
        study_req = StudyScenarioRequest(additional_weekly_study_hours=request.additional_weekly_study_hours)
        fitness_req = FitnessScenarioRequest(
            additional_exercise_minutes=request.additional_exercise_minutes,
            sleep_adjustment_hours=request.sleep_adjustment_hours,
        )
        # persist=False: these are intermediate sub-domain runs consumed only to build
        # the hybrid scenario set below — persisting them too would silently write 3
        # "invisible" simulations the user never actually asked to save, on top of the
        # one hybrid result this call is actually for.
        finance_sim, study_sim, fitness_sim = await asyncio.gather(
            self.simulate_finance_scenarios(user_id, finance_req, persist=False),
            self.simulate_study_scenarios(user_id, study_req, persist=False),
            self.simulate_fitness_scenarios(user_id, fitness_req, persist=False),
        )

        def top(sim: SimulationResponse):
            return max(sim.scenarios, key=lambda s: s.score)

        finance_top, study_top, fitness_top = top(finance_sim), top(study_sim), top(fitness_sim)
        confidence = round(
            (finance_top.confidence_score + study_top.confidence_score + fitness_top.confidence_score) / 3, 2
        )

        named_combinations = [
            ("Status Quo", 0.0, 0.0, 0.0),
            ("Balanced Growth", 0.5, 0.5, 0.5),
            ("Aggressive Savings Focus", 1.0, 0.2, 0.2),
            ("Aggressive Study Focus", 0.2, 1.0, 0.2),
            ("Aggressive Fitness Focus", 0.2, 0.2, 1.0),
        ]
        raw_scenarios: list[_RawScenario] = []
        max_weight_total = max(fw + sw + ftw for _, fw, sw, ftw in named_combinations)
        for name, finance_w, study_w, fitness_w in named_combinations:
            weight_total = finance_w + study_w + fitness_w
            # Weighted average of each domain's own best score, normalized by the total
            # weight so every named combination lands on the same 0-100 scale regardless
            # of how many of the three weights are close to 1.0.
            weighted_sum = finance_top.score * finance_w + study_top.score * study_w + fitness_top.score * fitness_w
            composite_score = round(weighted_sum / weight_total, 2) if weight_total > 0 else 0.0
            raw_scenarios.append(
                _RawScenario(
                    name=name,
                    deltas={"finance_weight": finance_w, "study_weight": study_w, "fitness_weight": fitness_w},
                    metrics=[
                        MetricPoint(label="Future Saving", value=finance_top.primary_metric_value * finance_w, unit="INR"),
                        MetricPoint(label="Productivity Score", value=study_top.primary_metric_value * study_w, unit="pts"),
                        MetricPoint(label="Habit Score", value=fitness_top.primary_metric_value * fitness_w, unit="pts"),
                    ],
                    primary_metric_label="Composite Life Score",
                    primary_metric_value=composite_score,
                    goal_months=None,
                    confidence_score=confidence,
                    intensity=weight_total / max_weight_total,
                )
            )

        return await self._finalize(
            user_id, SimulationDomain.HYBRID_LIFESTYLE, RecommendationCategory.WELL_BEING,
            request.model_dump(), raw_scenarios, baseline_name="Status Quo",
            risk_tolerance=user.profile.risk_tolerance,
        )

    # ── Comparison across domains ────────────────────────────────────────────
    async def compare_all_domains(self, user_id: str) -> DomainComparisonResponse:
        # persist=False: this is a GET (no explicit user "run a simulation" action),
        # so it must not silently write 3 Simulation + 3 Recommendation docs on every
        # call — same rationale/pattern as simulate_hybrid_scenarios' sub-domain runs.
        finance, study, fitness = await asyncio.gather(
            self.simulate_finance_scenarios(user_id, FinanceScenarioRequest(), persist=False),
            self.simulate_study_scenarios(user_id, StudyScenarioRequest(), persist=False),
            self.simulate_fitness_scenarios(user_id, FitnessScenarioRequest(), persist=False),
        )
        candidates = [finance.recommendation, study.recommendation, fitness.recommendation]
        sims_by_recommendation_id = {
            finance.recommendation.id: finance,
            study.recommendation.id: study,
            fitness.recommendation.id: fitness,
        }

        def relative_improvement(sim: SimulationResponse) -> float:
            """% improvement of the best scenario over this domain's own
            baseline (its zero-delta scenario — always scenarios[0], since
            every domain's scenario list is built in FINANCE/STUDY/FITNESS_
            SCENARIO_MULTIPLIERS order, starting at multiplier 0.0). Unlike
            each ScenarioResult.score (min-max normalized only within that
            domain's own 3 scenarios via _score_scenarios), this is
            comparable *across* domains despite their different units (INR
            vs productivity points vs habit points) — raw scores can't be:
            e.g. a domain whose 3 scenarios only differ by 4% in real terms
            and a domain whose scenarios differ by 5000% both produce a
            best-scenario score of ~83 by construction, since normalization
            only sees relative spread within each domain's own set."""
            baseline_value = sim.scenarios[0].primary_metric_value
            best_value = max(s.primary_metric_value for s in sim.scenarios)
            if baseline_value == 0:
                # Going from literally nothing to something is an unbounded (mathematically
                # infinite) relative improvement — always outranks any finite-percentage
                # improvement elsewhere. Returning best_value's raw magnitude here instead
                # would make this branch dominate or lose purely based on each domain's
                # raw unit scale (INR vs habit points), not the improvement itself.
                return float("inf") if best_value > 0 else 0.0
            return (best_value - baseline_value) / abs(baseline_value)

        overall = max(candidates, key=lambda r: relative_improvement(sims_by_recommendation_id[r.id]))

        return DomainComparisonResponse(
            user_id=user_id,
            finance=finance,
            study=study,
            fitness=fitness,
            overall_recommendation=overall,
            generated_at=datetime.now(timezone.utc),
        )

    # ── Persistence + response assembly (shared by every domain) ────────────
    async def _finalize(
        self,
        user_id: str,
        domain: SimulationDomain,
        category: RecommendationCategory,
        input_parameters: dict,
        raw_scenarios: list[_RawScenario],
        baseline_name: str,
        persist: bool = True,
        risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    ) -> SimulationResponse:
        primary_values = [s.primary_metric_value for s in raw_scenarios]
        goal_months = [s.goal_months for s in raw_scenarios]
        scenario_intensity = [s.intensity for s in raw_scenarios]
        confidence = raw_scenarios[0].confidence_score if raw_scenarios else 0.0
        scores = _score_scenarios(primary_values, goal_months, confidence, risk_tolerance, scenario_intensity)

        scenario_docs = [
            ScenarioResult(
                name=s.name,
                deltas=s.deltas,
                metrics=s.metrics,
                primary_metric_label=s.primary_metric_label,
                primary_metric_value=s.primary_metric_value,
                score=score,
                confidence_score=s.confidence_score,
            )
            for s, score in zip(raw_scenarios, scores)
        ]

        best_idx = max(range(len(scenario_docs)), key=lambda i: scenario_docs[i].score)
        best_raw, best_doc = raw_scenarios[best_idx], scenario_docs[best_idx]
        title, reason = _build_recommendation_text(domain.value.title(), best_raw, baseline_name)

        simulation = Simulation(
            user_id=PydanticObjectId(user_id),
            domain=domain,
            input_parameters=input_parameters,
            scenarios=scenario_docs,
            created_at=datetime.now(timezone.utc),
        )

        priority = Priority.HIGH if best_doc.score >= 75 else Priority.MEDIUM if best_doc.score >= 40 else Priority.LOW
        recommendation = Recommendation(
            user_id=PydanticObjectId(user_id),
            simulation_id=simulation.id,
            category=category,
            title=title,
            reason=reason,
            recommended_scenario_name=best_doc.name,
            priority=priority,
        )

        if persist:
            await simulation.insert()
            recommendation.simulation_id = simulation.id
            await recommendation.insert()
        else:
            # Not persisted (e.g. an intermediate sub-domain run inside simulate_hybrid_scenarios) —
            # still needs valid-looking ids for the response shape, just never written to Mongo.
            simulation.id = PydanticObjectId()
            recommendation.id = PydanticObjectId()

        return SimulationResponse(
            id=str(simulation.id),
            domain=domain,
            scenarios=[
                ScenarioResultResponse(
                    name=s.name,
                    deltas=s.deltas,
                    metrics=[MetricPointResponse(label=m.label, value=m.value, unit=m.unit) for m in s.metrics],
                    primary_metric_label=s.primary_metric_label,
                    primary_metric_value=s.primary_metric_value,
                    score=s.score,
                    confidence_score=s.confidence_score,
                )
                for s in scenario_docs
            ],
            recommendation=RecommendationResponse(
                id=str(recommendation.id),
                category=recommendation.category,
                title=recommendation.title,
                reason=recommendation.reason,
                recommended_scenario_name=recommendation.recommended_scenario_name,
                priority=recommendation.priority,
                stats=[
                    MetricPointResponse(label=m.label, value=m.value, unit=m.unit) for m in best_doc.metrics
                ],
            ),
            generated_at=simulation.created_at,
        )

    # ── History / feedback ────────────────────────────────────────────────
    async def get_simulation_history(
        self, user_id: str, domain: Optional[SimulationDomain] = None, limit: int = 20
    ) -> list[SimulationHistoryItem]:
        query: dict = {"user_id": PydanticObjectId(user_id)}
        if domain is not None:
            query["domain"] = domain
        records = await Simulation.find(query, sort=[("created_at", -1)]).limit(limit).to_list()
        items = []
        for r in records:
            top = max(r.scenarios, key=lambda s: s.score) if r.scenarios else None
            items.append(
                SimulationHistoryItem(
                    id=str(r.id),
                    domain=r.domain,
                    status=r.status.value,
                    top_scenario_name=top.name if top else "",
                    created_at=r.created_at,
                )
            )
        return items

    async def get_simulation(self, user_id: str, simulation_id: str) -> SimulationDetailResponse:
        try:
            sid = PydanticObjectId(simulation_id)
        except Exception:
            raise NotFoundError("Simulation", simulation_id)
        simulation = await Simulation.get(sid)
        if not simulation or simulation.user_id != PydanticObjectId(user_id):
            raise NotFoundError("Simulation", simulation_id)
        return SimulationDetailResponse(
            id=str(simulation.id),
            user_id=str(simulation.user_id),
            domain=simulation.domain,
            input_parameters=simulation.input_parameters,
            scenarios=[
                ScenarioResultResponse(
                    name=s.name,
                    deltas=s.deltas,
                    metrics=[MetricPointResponse(label=m.label, value=m.value, unit=m.unit) for m in s.metrics],
                    primary_metric_label=s.primary_metric_label,
                    primary_metric_value=s.primary_metric_value,
                    score=s.score,
                    confidence_score=s.confidence_score,
                )
                for s in simulation.scenarios
            ],
            status=simulation.status.value,
            created_at=simulation.created_at,
        )

    async def submit_recommendation_feedback(
        self, user_id: str, recommendation_id: str, feedback: str
    ) -> Recommendation:
        try:
            feedback_enum = UserFeedback(feedback.upper())
        except ValueError:
            raise BusinessRuleError(
                f"Invalid feedback value '{feedback}'. Must be one of: {[f.value for f in UserFeedback]}"
            )

        try:
            rid = PydanticObjectId(recommendation_id)
        except Exception:
            raise NotFoundError("Recommendation", recommendation_id)
        recommendation = await Recommendation.get(rid)
        if not recommendation or recommendation.user_id != PydanticObjectId(user_id):
            raise NotFoundError("Recommendation", recommendation_id)

        recommendation.user_feedback = feedback_enum
        recommendation.updated_at = datetime.now(timezone.utc)
        await recommendation.save()
        return recommendation


simulation_service = DecisionSimulationService()
