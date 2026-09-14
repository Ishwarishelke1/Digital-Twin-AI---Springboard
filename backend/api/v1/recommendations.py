"""
api/v1/recommendations.py — AI-written recommendations (Habits + Study).

GET /api/v1/recommendations/habits → grounded suggestions from the habit analytics engine
GET /api/v1/recommendations/study  → grounded suggestions from the productivity engine

Both compose the existing engines rather than querying Mongo directly, per the
project's "engines compose, they don't reimplement" convention — which also means
the model is shown exactly the figures the page itself renders, so its advice
cannot contradict the charts beside it.

A plain GET never reaches a model: it returns the stored set, or the deterministic
threshold lines when nothing has been generated yet. Only `?generate=true` calls a
provider, which is why the rate limit sits here — a page load costs nothing, and
the user decides when to spend a generation.
"""
import logging

from fastapi import APIRouter, Query, Request

from api.dependencies import CurrentUser
from core.rate_limit import limiter
from models.enums import RecommendationDomain
from schemas.recommendation_schema import AIRecommendationResponse
from services.habit_analytics_service import HabitAnalyticsService
from services.productivity_service import ProductivityService
import services.ai_recommendation_service as ai_recommendation_service
import services.study_service as study_service

logger = logging.getLogger("digital_twin_ai.recommendations_router")
router = APIRouter(prefix="/recommendations", tags=["AI Recommendations"])


@router.get(
    "/habits",
    response_model=AIRecommendationResponse,
    summary="AI recommendations grounded in the user's habit data",
)
@limiter.limit("20/minute")
async def habit_recommendations(
    request: Request,
    current_user: CurrentUser,
    generate: bool = Query(default=False, description="Call a model. Omit to read the stored set only."),
) -> AIRecommendationResponse:
    user_id = str(current_user.id)
    summary = await HabitAnalyticsService().get_summary(user_id)
    goals = [g for g in current_user.active_goals if g.category.value == "HABIT"]

    result = await ai_recommendation_service.get_recommendations(
        user=current_user,
        domain=RecommendationDomain.HABITS,
        snapshot=ai_recommendation_service.build_habit_snapshot(summary, goals),
        fallback_items=ai_recommendation_service.rule_based_habit_items(summary),
        generate=generate,
    )
    return AIRecommendationResponse(**vars(result))


@router.get(
    "/study",
    response_model=AIRecommendationResponse,
    summary="AI recommendations grounded in the user's study data",
)
@limiter.limit("20/minute")
async def study_recommendations(
    request: Request,
    current_user: CurrentUser,
    generate: bool = Query(default=False, description="Call a model. Omit to read the stored set only."),
) -> AIRecommendationResponse:
    user_id = str(current_user.id)
    productivity = await ProductivityService().get_summary(user_id)
    subjects = await study_service.get_subject_performance(user_id)
    goals = [g for g in current_user.active_goals if g.category.value == "STUDY"]

    result = await ai_recommendation_service.get_recommendations(
        user=current_user,
        domain=RecommendationDomain.STUDY,
        snapshot=ai_recommendation_service.build_study_snapshot(productivity, subjects, goals),
        fallback_items=ai_recommendation_service.rule_based_study_items(productivity, subjects),
        generate=generate,
    )
    return AIRecommendationResponse(**vars(result))
