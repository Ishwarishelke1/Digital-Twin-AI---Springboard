from datetime import datetime, timezone
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import Field
import pymongo

class UserActivity(Document):
    user_id: PydanticObjectId = Field(description="The ObjectId of the user")
    action_type: str = Field(description="The action performed (e.g., CREATED_FINANCE, DELETED_STUDY)")
    entity_type: str = Field(description="The type of entity (e.g., FINANCE, STUDY, PROFILE)")
    entity_id: Optional[str] = Field(default=None, description="The ID of the affected entity, if applicable")
    description: str = Field(description="Human-readable description of the activity")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "user_activities"
        indexes = [
            [("user_id", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)],
        ]
