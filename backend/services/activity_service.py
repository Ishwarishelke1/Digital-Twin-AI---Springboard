import math
from typing import Optional
from beanie import PydanticObjectId
from models.activity import UserActivity
from schemas.activity_schema import PaginatedActivityResponse, ActivityRecordResponse
import logging

logger = logging.getLogger("digital_twin_ai.activity_service")

async def log_activity(
    user_id: str,
    action_type: str,
    entity_type: str,
    description: str,
    entity_id: Optional[str] = None
) -> None:
    """
    Logs a user activity. This function doesn't raise errors to avoid interrupting core flows.
    """
    try:
        activity = UserActivity(
            user_id=PydanticObjectId(user_id),
            action_type=action_type,
            entity_type=entity_type,
            description=description,
            entity_id=entity_id
        )
        await activity.insert()
    except Exception:
        # Never let activity logging interrupt the core flow it's attached to,
        # but log with a full traceback (exc_info) so failures are actually
        # diagnosable instead of a one-line message with no stack context.
        logger.error("Failed to log activity for user %s (action_type=%s)", user_id, action_type, exc_info=True)

async def list_activities(
    user_id: str,
    page: int = 1,
    limit: int = 20
) -> PaginatedActivityResponse:
    """
    Returns paginated activity history for the user.
    """
    skip = (page - 1) * limit
    
    query = UserActivity.find({"user_id": PydanticObjectId(user_id)})
    
    total = await query.count()
    records = await query.sort("-timestamp").skip(skip).limit(limit).to_list()
    
    items = [
        ActivityRecordResponse(
            id=str(r.id),
            action_type=r.action_type,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            description=r.description,
            timestamp=r.timestamp
        )
        for r in records
    ]
    
    return PaginatedActivityResponse(
        data=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if limit > 0 else 1
    )
