"""
api/v1/activity.py — User Activity History endpoints.
GET  /api/v1/activity              → paginated activity history
"""
import logging

from fastapi import APIRouter, Query, status

from api.dependencies import CurrentUser
from schemas.activity_schema import PaginatedActivityResponse
import services.activity_service as activity_service

logger = logging.getLogger("digital_twin_ai.activity_router")
router = APIRouter(prefix="/activity", tags=["Activity History"])

@router.get(
    "",
    response_model=PaginatedActivityResponse,
    summary="Get paginated user activity history",
)
async def list_activities(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> PaginatedActivityResponse:
    """
    Returns paginated activity history for the authenticated user.
    """
    return await activity_service.list_activities(
        user_id=str(current_user.id),
        page=page,
        limit=limit,
    )
