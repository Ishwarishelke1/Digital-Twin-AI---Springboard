"""
api/v1/simulation.py — Decision Simulation & Recommendation Engine endpoints.
POST /api/v1/simulation/finance/scenarios      → finance what-if scenarios + recommendation
POST /api/v1/simulation/study/scenarios        → study what-if scenarios + recommendation
POST /api/v1/simulation/fitness/scenarios      → fitness what-if scenarios + recommendation
POST /api/v1/simulation/hybrid/scenarios       → combined lifestyle what-if scenarios
GET  /api/v1/simulation/compare                → bundled comparison across all domains
GET  /api/v1/simulation/history                → past simulations for the current user
GET  /api/v1/simulation/{simulation_id}        → one persisted simulation
PATCH /api/v1/simulation/recommendations/{id}/feedback → record user feedback on a recommendation
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query

from api.dependencies import CurrentUser
from models.enums import SimulationDomain
from schemas.simulation_schema import (
    DomainComparisonResponse,
    FinanceScenarioRequest,
    FitnessScenarioRequest,
    HybridScenarioRequest,
    RecommendationFeedbackRequest,
    SimulationDetailResponse,
    SimulationHistoryItem,
    SimulationResponse,
    StudyScenarioRequest,
)
from services.simulation_service import simulation_service

logger = logging.getLogger("digital_twin_ai.simulation_router")
router = APIRouter(prefix="/simulation", tags=["Decision Simulation"])


@router.post("/finance/scenarios", response_model=SimulationResponse, summary="Simulate finance what-if scenarios")
async def simulate_finance(request: FinanceScenarioRequest, current_user: CurrentUser) -> SimulationResponse:
    """Projects several savings/expense what-if scenarios off the user's real income and
    expense trend, scores them, and persists the run with a recommendation."""
    return await simulation_service.simulate_finance_scenarios(str(current_user.id), request)


@router.post("/study/scenarios", response_model=SimulationResponse, summary="Simulate study what-if scenarios")
async def simulate_study(request: StudyScenarioRequest, current_user: CurrentUser) -> SimulationResponse:
    """Projects several weekly-study-hours what-if scenarios off the user's real
    productivity trend, scores them, and persists the run with a recommendation."""
    return await simulation_service.simulate_study_scenarios(str(current_user.id), request)


@router.post("/fitness/scenarios", response_model=SimulationResponse, summary="Simulate fitness what-if scenarios")
async def simulate_fitness(request: FitnessScenarioRequest, current_user: CurrentUser) -> SimulationResponse:
    """Projects several exercise/sleep what-if scenarios off the user's real habit
    trend, scores them, and persists the run with a recommendation."""
    return await simulation_service.simulate_fitness_scenarios(str(current_user.id), request)


@router.post("/hybrid/scenarios", response_model=SimulationResponse, summary="Simulate combined lifestyle what-if scenarios")
async def simulate_hybrid(request: HybridScenarioRequest, current_user: CurrentUser) -> SimulationResponse:
    """Combines finance/study/fitness deltas into named lifestyle scenarios
    (Balanced Growth, Aggressive Savings Focus, etc.) and recommends the best one."""
    return await simulation_service.simulate_hybrid_scenarios(str(current_user.id), request)


@router.get("/compare", response_model=DomainComparisonResponse, summary="Compare default what-if outcomes across all domains")
async def compare_domains(current_user: CurrentUser) -> DomainComparisonResponse:
    """Runs a default-delta simulation for finance, study, and fitness and returns
    one overall top recommendation across all three."""
    return await simulation_service.compare_all_domains(str(current_user.id))


@router.get("/history", response_model=list[SimulationHistoryItem], summary="List past simulations")
async def simulation_history(
    current_user: CurrentUser,
    domain: Optional[SimulationDomain] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SimulationHistoryItem]:
    return await simulation_service.get_simulation_history(str(current_user.id), domain, limit)


@router.get("/{simulation_id}", response_model=SimulationDetailResponse, summary="Get one persisted simulation")
async def get_simulation(simulation_id: str, current_user: CurrentUser) -> SimulationDetailResponse:
    return await simulation_service.get_simulation(str(current_user.id), simulation_id)


@router.patch(
    "/recommendations/{recommendation_id}/feedback",
    summary="Record user feedback (helpful/unhelpful/irrelevant) on a recommendation",
)
async def submit_feedback(
    recommendation_id: str, request: RecommendationFeedbackRequest, current_user: CurrentUser
):
    recommendation = await simulation_service.submit_recommendation_feedback(
        str(current_user.id), recommendation_id, request.feedback
    )
    return {"id": str(recommendation.id), "user_feedback": recommendation.user_feedback}
