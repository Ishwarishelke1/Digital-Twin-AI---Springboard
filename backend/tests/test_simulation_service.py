"""
tests/test_simulation_service.py — Unit tests for services/simulation_service.py.

Two layers:
1. Pure-function tests: exercise the scenario math and the shared multi-factor
   scoring engine directly with plain data, no mocking, no DB (mirrors the style
   of tests/test_forecast_service.py).
2. Service-level tests: patch out the engine calls (forecast_service/
   productivity_service/habit_analytics_service), User.get, and Simulation/
   Recommendation .insert() with AsyncMock, mirroring test_forecast_service.py's
   _patch_user_get pattern.
"""
from contextlib import ExitStack
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from beanie import PydanticObjectId

from core.exceptions import BusinessRuleError, NotFoundError
from models.enums import GoalCategory, SimulationDomain, SimulationStatus
from models.simulation import Recommendation, ScenarioResult, Simulation
from models.user import ActiveGoal, Profile, User
from schemas.forecast_schema import (
    ExpenseProjectionResponse,
    ForecastMethod,
    IncomeProjectionResponse,
    MonthlyProjectionPoint,
)
from schemas.habit_analytics_schema import HabitTrendResponse, WeeklyHabitPoint
from schemas.productivity_schema import (
    AnalyticsMethod,
    PerformancePredictionResponse,
    ProductivityScoreResponse,
    WeeklyProjectionPoint,
    WeeklyTrendPoint,
    WeeklyTrendResponse,
)
from schemas.simulation_schema import FitnessScenarioRequest, StudyScenarioRequest
from services.simulation_service import (
    DecisionSimulationService,
    _average_months_to_goals,
    _estimate_months_to_goal,
    _finance_scenario_deltas,
    _finance_scenario_outcome,
    _fitness_scenario_deltas,
    _fitness_scenario_outcome,
    _normalize_optional,
    _score_scenarios,
    _study_scenario_deltas,
    _study_scenario_outcome,
)

VALID_USER_ID = "507f1f77bcf86cd799439011"


def _goal(current: float, target: float) -> ActiveGoal:
    return ActiveGoal(
        title="Test Goal",
        category=GoalCategory.FINANCE,
        target_value=target,
        current_value=current,
        unit="INR",
        target_date="2027-01-01T00:00:00Z",
    )


# ─── _normalize_optional ───────────────────────────────────────────────────────

def test_normalize_optional_higher_is_better():
    result = _normalize_optional([10.0, 20.0, 30.0], higher_is_better=True)
    assert result == [0.0, 0.5, 1.0]


def test_normalize_optional_lower_is_better():
    result = _normalize_optional([10.0, 20.0, 30.0], higher_is_better=False)
    assert result == [1.0, 0.5, 0.0]


def test_normalize_optional_missing_values_are_neutral():
    result = _normalize_optional([None, 10.0, None], higher_is_better=True)
    assert result == [0.5, 1.0, 0.5]


def test_normalize_optional_all_missing():
    assert _normalize_optional([None, None], higher_is_better=True) == [0.5, 0.5]


def test_normalize_optional_flat_values():
    assert _normalize_optional([5.0, 5.0, 5.0], higher_is_better=True) == [0.5, 0.5, 0.5]


# ─── _score_scenarios ───────────────────────────────────────────────────────────

def test_score_scenarios_best_outcome_scores_highest():
    scores = _score_scenarios([100.0, 200.0, 300.0], [None, None, None], confidence=0.8)
    assert scores[2] > scores[1] > scores[0]


def test_score_scenarios_within_bounds():
    scores = _score_scenarios([0.0, 50.0, 100.0], [10.0, 5.0, None], confidence=0.5)
    assert all(0 <= s <= 100 for s in scores)


def test_score_scenarios_goal_impact_rewards_fewer_months():
    # Same primary outcome, but scenario B reaches its goal sooner.
    scores = _score_scenarios([100.0, 100.0], [12.0, 3.0], confidence=0.9)
    assert scores[1] > scores[0]


# ─── _estimate_months_to_goal / _average_months_to_goals ──────────────────────

def test_estimate_months_to_goal_already_met():
    assert _estimate_months_to_goal(current_value=500, target_value=400, monthly_rate=100) == 0.0


def test_estimate_months_to_goal_unreachable():
    assert _estimate_months_to_goal(current_value=0, target_value=1000, monthly_rate=0) is None


def test_estimate_months_to_goal_normal_case():
    assert _estimate_months_to_goal(current_value=0, target_value=1000, monthly_rate=250) == 4.0


def test_average_months_to_goals_empty_list_is_none():
    assert _average_months_to_goals([], monthly_rate=100) is None


def test_average_months_to_goals_averages_open_goals():
    goals = [_goal(current=0, target=1000), _goal(current=0, target=2000)]
    # monthly_rate=500 -> 2 months and 4 months -> average 3.0
    assert _average_months_to_goals(goals, monthly_rate=500) == 3.0


def test_average_months_to_goals_completed_goal_counts_as_zero():
    goals = [_goal(current=1000, target=1000), _goal(current=0, target=1000)]
    # first goal already met -> 0 months remaining, second needs 2 months at rate 500
    assert _average_months_to_goals(goals, monthly_rate=500) == 1.0


# ─── Finance scenario math ──────────────────────────────────────────────────────

def test_finance_scenario_deltas_uses_stretch_fallback_when_zero():
    deltas = _finance_scenario_deltas(additional_monthly_saving=0, expense_reduction_pct=0)
    names = [d[0] for d in deltas]
    assert names == ["Current Plan", "Target Plan", "Stretch Plan"]
    assert deltas[0] == ("Current Plan", 0.0, 0.0)
    assert deltas[1][2] == 10.0  # DEFAULT_FINANCE_EXPENSE_REDUCTION_STRETCH_PCT


def test_finance_scenario_deltas_scales_requested_delta():
    deltas = _finance_scenario_deltas(additional_monthly_saving=2000, expense_reduction_pct=0)
    assert deltas[1] == ("Target Plan", 2000.0, 0.0)
    assert deltas[2] == ("Stretch Plan", 3000.0, 0.0)


def test_finance_scenario_outcome_basic():
    monthly_saving, future_saving = _finance_scenario_outcome(
        baseline_income=40000, baseline_expense=25000, additional_saving=2000,
        expense_reduction_pct=0, months_ahead=6,
    )
    assert monthly_saving == 17000.0
    assert future_saving == 102000.0


def test_finance_scenario_outcome_with_expense_reduction():
    monthly_saving, _ = _finance_scenario_outcome(
        baseline_income=40000, baseline_expense=20000, additional_saving=0,
        expense_reduction_pct=10, months_ahead=1,
    )
    assert monthly_saving == 22000.0  # 40000 - (20000 * 0.9)


# ─── Study scenario math ─────────────────────────────────────────────────────────

def test_study_scenario_deltas_uses_stretch_fallback_when_zero():
    deltas = _study_scenario_deltas(additional_weekly_study_hours=0)
    assert deltas[1][1] == 3.0  # DEFAULT_STUDY_HOURS_STRETCH


def test_study_scenario_outcome_more_hours_increases_score():
    baseline_score, baseline_hours = 60.0, 5.0
    score_more, hours_more = _study_scenario_outcome(baseline_score, baseline_hours, delta_hours=5.0)
    score_less, hours_less = _study_scenario_outcome(baseline_score, baseline_hours, delta_hours=-2.0)
    assert score_more > baseline_score > score_less
    assert hours_more == 10.0
    assert hours_less == 3.0


def test_study_scenario_outcome_clamped_to_100():
    score, _ = _study_scenario_outcome(baseline_score=99.0, baseline_weekly_hours=14.0, delta_hours=100.0)
    assert score <= 100.0


# ─── Fitness scenario math ───────────────────────────────────────────────────────

def test_fitness_scenario_deltas_uses_stretch_fallback_when_zero():
    deltas = _fitness_scenario_deltas(additional_exercise_minutes=0, sleep_adjustment_hours=0)
    assert deltas[1][1] == 30.0  # DEFAULT_FITNESS_EXERCISE_STRETCH_MINUTES


def test_fitness_scenario_outcome_more_exercise_and_better_sleep_increases_score():
    baseline = dict(baseline_sleep=6.0, baseline_exercise=10.0, baseline_water=1.5, baseline_screen=8.0)
    score_baseline, _, _ = _fitness_scenario_outcome(**baseline, exercise_delta=0, sleep_delta=0)
    score_improved, new_exercise, new_sleep = _fitness_scenario_outcome(**baseline, exercise_delta=30, sleep_delta=1.5)
    assert score_improved > score_baseline
    assert new_exercise == 40.0
    assert new_sleep == 7.5


def test_fitness_scenario_outcome_score_never_negative():
    score, exercise, sleep = _fitness_scenario_outcome(
        baseline_sleep=8.0, baseline_exercise=0.0, baseline_water=2.0, baseline_screen=4.0,
        exercise_delta=-100.0, sleep_delta=-20.0,
    )
    assert score >= 0.0
    assert exercise == 0.0  # clamped at 0, deltas can't drive it negative
    assert sleep == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Service-level tests (engines + User.get + Simulation/Recommendation.insert mocked)
# ─────────────────────────────────────────────────────────────────────────────

def _fake_user() -> User:
    return User.model_construct(
        email="sim@example.com",
        password_hash="hashed",
        profile=Profile(name="Sim User", age=25, monthly_income_baseline=Decimal("0")),
        active_goals=[],
    )


def _patch_user_get(user):
    return patch("services.simulation_service.User.get", new=AsyncMock(return_value=user))


def _patch_insert():
    return (
        patch("services.simulation_service.Simulation.insert", new=AsyncMock(return_value=None)),
        patch("services.simulation_service.Recommendation.insert", new=AsyncMock(return_value=None)),
    )


def _patch_finance_engine(income=50000.0, expense=40000.0, confidence=0.8):
    income_resp = IncomeProjectionResponse(
        user_id=VALID_USER_ID,
        projections=[MonthlyProjectionPoint(year=2026, month=10, projected_amount=Decimal(str(income)))],
        method_used=ForecastMethod.LINEAR_REGRESSION,
        data_points_used=6,
        confidence_score=confidence,
    )
    expense_resp = ExpenseProjectionResponse(
        user_id=VALID_USER_ID,
        projections=[MonthlyProjectionPoint(year=2026, month=10, projected_amount=Decimal(str(expense)))],
        method_used=ForecastMethod.LINEAR_REGRESSION,
        data_points_used=6,
        confidence_score=confidence,
    )
    return (
        patch(
            "services.simulation_service.forecast_service.project_income",
            new=AsyncMock(return_value=income_resp),
        ),
        patch(
            "services.simulation_service.forecast_service.project_expenses",
            new=AsyncMock(return_value=expense_resp),
        ),
    )


def _patch_study_engine(live_score=50.0, projected_score=70.0, weekly_hours=10.0, confidence=0.6):
    score_resp = ProductivityScoreResponse(
        user_id=VALID_USER_ID, productivity_score=live_score, data_points_used=8, lookback_days=90,
    )
    weekly_resp = WeeklyTrendResponse(
        user_id=VALID_USER_ID,
        trend=[
            WeeklyTrendPoint(
                week_start=date(2026, 8, 24), total_study_hours=weekly_hours,
                average_focus_score=70.0, average_productivity_score=live_score, session_count=3,
            )
        ],
    )
    prediction_resp = PerformancePredictionResponse(
        user_id=VALID_USER_ID,
        predicted_productivity=[
            WeeklyProjectionPoint(week_start=date(2026, 9, 1), projected_score=projected_score)
        ],
        productivity_method_used=AnalyticsMethod.LINEAR_REGRESSION,
        productivity_confidence_score=confidence,
        data_points_used=8,
    )
    return (
        patch(
            "services.simulation_service.productivity_service.get_productivity_score",
            new=AsyncMock(return_value=score_resp),
        ),
        patch(
            "services.simulation_service.productivity_service.get_weekly_trend",
            new=AsyncMock(return_value=weekly_resp),
        ),
        patch(
            "services.simulation_service.productivity_service.predict_performance",
            new=AsyncMock(return_value=prediction_resp),
        ),
    )


def _patch_fitness_engine(sleep=7.0, exercise=20.0, water=1.8, screen=5.0, days_logged=3):
    trend_resp = HabitTrendResponse(
        user_id=VALID_USER_ID,
        daily=[],
        weekly=[
            WeeklyHabitPoint(
                week_start=date(2026, 8, 24), days_logged=days_logged, average_habit_score=60.0,
                average_sleep_hours=sleep, average_exercise_minutes=exercise,
                average_water_intake_liters=water, average_screen_time_hours=screen,
            )
        ],
        monthly=[],
    )
    return patch(
        "services.simulation_service.habit_analytics_service.get_habit_trend",
        new=AsyncMock(return_value=trend_resp),
    )


@pytest.mark.asyncio
async def test_compare_all_domains_does_not_persist_anything():
    """Regression test for the persist-on-GET bug: compare_all_domains must not
    write Simulation/Recommendation docs — it's a GET with no explicit user
    "run a simulation" action."""
    service = DecisionSimulationService()
    with ExitStack() as stack:
        stack.enter_context(_patch_user_get(_fake_user()))
        for p in _patch_finance_engine():
            stack.enter_context(p)
        for p in _patch_study_engine():
            stack.enter_context(p)
        stack.enter_context(_patch_fitness_engine())
        sim_patch, rec_patch = _patch_insert()
        sim_insert_mock = stack.enter_context(sim_patch)
        rec_insert_mock = stack.enter_context(rec_patch)
        result = await service.compare_all_domains(VALID_USER_ID)

    assert sim_insert_mock.await_count == 0
    assert rec_insert_mock.await_count == 0
    assert result.overall_recommendation is not None


@pytest.mark.asyncio
async def test_simulate_finance_scenarios_persists_when_called_directly():
    """Contrast case for the above: a real, explicit simulate call still persists."""
    from schemas.simulation_schema import FinanceScenarioRequest

    service = DecisionSimulationService()
    with ExitStack() as stack:
        stack.enter_context(_patch_user_get(_fake_user()))
        for p in _patch_finance_engine():
            stack.enter_context(p)
        sim_patch, rec_patch = _patch_insert()
        sim_insert_mock = stack.enter_context(sim_patch)
        rec_insert_mock = stack.enter_context(rec_patch)
        await service.simulate_finance_scenarios(VALID_USER_ID, FinanceScenarioRequest())

    assert sim_insert_mock.await_count == 1
    assert rec_insert_mock.await_count == 1


@pytest.mark.asyncio
async def test_simulate_study_scenarios_uses_requested_weeks_ahead_for_prediction():
    """Regression test: weeks_ahead must actually reach predict_performance,
    not be silently hardcoded to 1."""
    service = DecisionSimulationService()
    predict_resp = PerformancePredictionResponse(
        user_id=VALID_USER_ID,
        predicted_productivity=[WeeklyProjectionPoint(week_start=date(2026, 10, 1), projected_score=80.0)],
        productivity_method_used=AnalyticsMethod.LINEAR_REGRESSION,
        productivity_confidence_score=0.6,
        data_points_used=8,
    )
    with ExitStack() as stack:
        stack.enter_context(_patch_user_get(_fake_user()))
        score_resp = ProductivityScoreResponse(
            user_id=VALID_USER_ID, productivity_score=50.0, data_points_used=8, lookback_days=90,
        )
        weekly_resp = WeeklyTrendResponse(
            user_id=VALID_USER_ID,
            trend=[
                WeeklyTrendPoint(
                    week_start=date(2026, 8, 24), total_study_hours=10.0,
                    average_focus_score=70.0, average_productivity_score=50.0, session_count=3,
                )
            ],
        )
        stack.enter_context(patch(
            "services.simulation_service.productivity_service.get_productivity_score",
            new=AsyncMock(return_value=score_resp),
        ))
        stack.enter_context(patch(
            "services.simulation_service.productivity_service.get_weekly_trend",
            new=AsyncMock(return_value=weekly_resp),
        ))
        predict_mock = stack.enter_context(patch(
            "services.simulation_service.productivity_service.predict_performance",
            new=AsyncMock(return_value=predict_resp),
        ))
        for p in _patch_insert():
            stack.enter_context(p)
        await service.simulate_study_scenarios(VALID_USER_ID, StudyScenarioRequest(weeks_ahead=9))

    assert predict_mock.await_args.kwargs.get("weeks_ahead") == 9


@pytest.mark.asyncio
async def test_simulate_study_scenarios_baseline_uses_trend_projected_score():
    """Regression test: the scenario's baseline score must come from the
    weeks_ahead-projected trend, not today's live score — otherwise changing
    the "Simulation Period" would never change the output."""
    service = DecisionSimulationService()
    with ExitStack() as stack:
        stack.enter_context(_patch_user_get(_fake_user()))
        for p in _patch_study_engine(live_score=50.0, projected_score=90.0, weekly_hours=0.0):
            stack.enter_context(p)
        for p in _patch_insert():
            stack.enter_context(p)
        result = await service.simulate_study_scenarios(
            VALID_USER_ID, StudyScenarioRequest(additional_weekly_study_hours=0, weeks_ahead=4)
        )

    # The "Current Pace" (zero-delta) scenario's projected score should reflect
    # the trend-projected baseline (90.0), not the live score (50.0).
    baseline_scenario = next(s for s in result.scenarios if s.name == "Current Pace")
    assert baseline_scenario.primary_metric_value == 90.0


@pytest.mark.asyncio
async def test_simulate_fitness_scenarios_cumulative_metric_scales_with_weeks_ahead():
    """Regression test: weeks_ahead must genuinely affect fitness scenario
    output (a cumulative-exercise metric scaled by the requested horizon)."""
    service = DecisionSimulationService()

    async def run(weeks_ahead: int):
        with ExitStack() as stack:
            stack.enter_context(_patch_user_get(_fake_user()))
            stack.enter_context(_patch_fitness_engine(exercise=20.0))
            for p in _patch_insert():
                stack.enter_context(p)
            return await service.simulate_fitness_scenarios(
                VALID_USER_ID, FitnessScenarioRequest(additional_exercise_minutes=0, weeks_ahead=weeks_ahead)
            )

    result_short = await run(2)
    result_long = await run(8)

    def cumulative_metric(sim_response):
        baseline = next(s for s in sim_response.scenarios if s.name == "Current Routine")
        metric = next(m for m in baseline.metrics if "Weeks" in m.label)
        return metric.value

    assert cumulative_metric(result_long) == 4 * cumulative_metric(result_short)


@pytest.mark.asyncio
async def test_simulate_hybrid_scenarios_persists_one_composite_simulation():
    """Regression coverage gap: simulate_hybrid_scenarios was untested at the
    service level — only its pure math was covered indirectly via the other
    domains' tests."""
    from schemas.simulation_schema import HybridScenarioRequest

    service = DecisionSimulationService()
    with ExitStack() as stack:
        stack.enter_context(_patch_user_get(_fake_user()))
        for p in _patch_finance_engine():
            stack.enter_context(p)
        for p in _patch_study_engine():
            stack.enter_context(p)
        stack.enter_context(_patch_fitness_engine())
        sim_patch, rec_patch = _patch_insert()
        sim_insert_mock = stack.enter_context(sim_patch)
        rec_insert_mock = stack.enter_context(rec_patch)
        result = await service.simulate_hybrid_scenarios(
            VALID_USER_ID, HybridScenarioRequest(additional_monthly_saving=500)
        )

    # Exactly one composite Simulation/Recommendation persisted — not the 3
    # sub-domain runs consumed internally to build it (those pass persist=False).
    assert sim_insert_mock.await_count == 1
    assert rec_insert_mock.await_count == 1
    assert len(result.scenarios) == 5  # named_combinations
    assert any(s.name == "Status Quo" for s in result.scenarios)


@pytest.mark.asyncio
async def test_compare_all_domains_picks_domain_with_larger_relative_improvement():
    """Regression test for the cross-domain comparability fix: overall_recommendation
    must be based on % improvement over each domain's own baseline, not each
    domain's raw (domain-internal-only) score — a domain with a trivial real
    improvement must not be able to outrank one with a dramatically larger real
    improvement just because its 3 scenarios happen to be tightly clustered."""
    # All three domains use ordinary nonzero baselines (deliberately avoiding
    # baseline_value == 0, which triggers relative_improvement's separate
    # "unbounded improvement" branch) so this test isolates the actual ratio
    # comparison: finance ~15% best-vs-baseline, fitness ~25%, study ~129% —
    # study has by far the largest *relative* improvement despite having the
    # smallest raw numbers (a live score of 5 vs finance's thousands of INR),
    # which is exactly what the old domain-internal-only scoring couldn't see.
    service = DecisionSimulationService()
    with ExitStack() as stack:
        stack.enter_context(_patch_user_get(_fake_user()))
        for p in _patch_finance_engine(income=10000.0, expense=5000.0, confidence=0.9):
            stack.enter_context(p)
        for p in _patch_study_engine(live_score=5.0, projected_score=5.0, weekly_hours=0.0, confidence=0.9):
            stack.enter_context(p)
        stack.enter_context(_patch_fitness_engine(sleep=6.0, exercise=10.0, water=1.5, screen=7.0))
        for p in _patch_insert():
            stack.enter_context(p)
        result = await service.compare_all_domains(VALID_USER_ID)

    assert result.overall_recommendation.category == result.study.recommendation.category


@pytest.mark.asyncio
async def test_compare_all_domains_zero_baseline_treated_as_unbounded_improvement():
    """Edge case for the fix's zero-baseline branch: a domain starting at a
    genuine zero (e.g. a brand-new user with no fitness history at all) that
    improves to ANY positive value must win over finite-percentage domains —
    and the win must be based on that being unbounded, not on the raw
    magnitude of best_value happening to exceed the other domains' ratios."""
    service = DecisionSimulationService()
    with ExitStack() as stack:
        stack.enter_context(_patch_user_get(_fake_user()))
        for p in _patch_finance_engine(income=10000.0, expense=5000.0, confidence=0.9):
            stack.enter_context(p)
        for p in _patch_study_engine(live_score=5.0, projected_score=5.0, weekly_hours=0.0, confidence=0.9):
            stack.enter_context(p)
        # Fitness baseline is a genuine zero across the board -> Current
        # Routine's habit_score is exactly 0.0.
        stack.enter_context(_patch_fitness_engine(sleep=0.0, exercise=0.0, water=0.0, screen=20.0))
        for p in _patch_insert():
            stack.enter_context(p)
        result = await service.compare_all_domains(VALID_USER_ID)

    assert result.fitness.scenarios[0].primary_metric_value == 0.0  # confirms the zero-baseline setup
    assert result.overall_recommendation.category == result.fitness.recommendation.category


# ─────────────────────────────────────────────────────────────────────────────
# History / detail / feedback (Simulation.find/.get, Recommendation.get/.save mocked)
# ─────────────────────────────────────────────────────────────────────────────

def _fake_simulation(domain=None, scenario_name="Current Plan", score=80.0):
    return Simulation.model_construct(
        id=_object_id(),
        user_id=_object_id(),
        domain=domain or _sim_domain(),
        input_parameters={},
        scenarios=[
            ScenarioResult(
                name=scenario_name, deltas={}, metrics=[], primary_metric_label="Future Saving",
                primary_metric_value=1000.0, score=score, confidence_score=0.8,
            )
        ],
        status=SimulationStatus.SUCCESS,
        created_at=datetime.now(timezone.utc),
    )


def _sim_domain():
    return SimulationDomain.FINANCE


def _object_id():
    return PydanticObjectId()


@pytest.mark.asyncio
async def test_get_simulation_history_maps_top_scenario_per_record():
    fake = _fake_simulation(scenario_name="Stretch Plan", score=91.0)
    query = type("Query", (), {})()
    query.limit = lambda self_limit: query
    query.to_list = AsyncMock(return_value=[fake])

    service = DecisionSimulationService()
    with patch.object(Simulation, "find", return_value=query):
        items = await service.get_simulation_history(VALID_USER_ID)

    assert len(items) == 1
    assert items[0].top_scenario_name == "Stretch Plan"
    assert items[0].status == "SUCCESS"


@pytest.mark.asyncio
async def test_get_simulation_history_empty_when_no_scenarios():
    """A Simulation with an empty scenarios list must not crash max()."""
    fake = _fake_simulation()
    fake.scenarios = []
    query = type("Query", (), {})()
    query.limit = lambda self_limit: query
    query.to_list = AsyncMock(return_value=[fake])

    service = DecisionSimulationService()
    with patch.object(Simulation, "find", return_value=query):
        items = await service.get_simulation_history(VALID_USER_ID)

    assert items[0].top_scenario_name == ""


@pytest.mark.asyncio
async def test_get_simulation_returns_detail_for_owned_simulation():
    fake = _fake_simulation()
    fake.user_id = PydanticObjectId(VALID_USER_ID)

    service = DecisionSimulationService()
    with patch.object(Simulation, "get", new=AsyncMock(return_value=fake)):
        result = await service.get_simulation(VALID_USER_ID, str(fake.id))

    assert result.id == str(fake.id)
    assert len(result.scenarios) == 1


@pytest.mark.asyncio
async def test_get_simulation_rejects_another_users_simulation():
    """IDOR guard: a simulation owned by a different user must 404, not leak."""
    fake = _fake_simulation()  # random user_id, not VALID_USER_ID

    service = DecisionSimulationService()
    with patch.object(Simulation, "get", new=AsyncMock(return_value=fake)):
        with pytest.raises(NotFoundError):
            await service.get_simulation(VALID_USER_ID, str(fake.id))


@pytest.mark.asyncio
async def test_get_simulation_not_found_raises():
    service = DecisionSimulationService()
    with patch.object(Simulation, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await service.get_simulation(VALID_USER_ID, str(_object_id()))


def _fake_recommendation(user_id=None):
    return Recommendation.model_construct(
        id=_object_id(),
        user_id=user_id or PydanticObjectId(VALID_USER_ID),
        simulation_id=None,
        category="FINANCE",
        title="Test Recommendation",
        reason="Because.",
        recommended_scenario_name="Stretch Plan",
        priority="HIGH",
        user_feedback=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_submit_recommendation_feedback_persists_feedback():
    fake = _fake_recommendation()
    service = DecisionSimulationService()
    with patch.object(Recommendation, "get", new=AsyncMock(return_value=fake)):
        with patch.object(Recommendation, "save", new=AsyncMock(return_value=None)) as save_mock:
            result = await service.submit_recommendation_feedback(VALID_USER_ID, str(fake.id), "helpful")

    assert result.user_feedback == "HELPFUL"
    assert save_mock.await_count == 1


@pytest.mark.asyncio
async def test_submit_recommendation_feedback_rejects_invalid_value():
    fake = _fake_recommendation()
    service = DecisionSimulationService()
    with patch.object(Recommendation, "get", new=AsyncMock(return_value=fake)):
        with pytest.raises(BusinessRuleError):
            await service.submit_recommendation_feedback(VALID_USER_ID, str(fake.id), "not_a_real_value")


@pytest.mark.asyncio
async def test_submit_recommendation_feedback_rejects_other_users_recommendation():
    fake = _fake_recommendation(user_id=PydanticObjectId())  # a different, random user

    service = DecisionSimulationService()
    with patch.object(Recommendation, "get", new=AsyncMock(return_value=fake)):
        with pytest.raises(NotFoundError):
            await service.submit_recommendation_feedback(VALID_USER_ID, str(fake.id), "helpful")
