from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class ActivityRecordResponse(BaseModel):
    id: str
    action_type: str
    entity_type: str
    entity_id: Optional[str] = None
    description: str
    timestamp: datetime

    class Config:
        from_attributes = True

class PaginatedActivityResponse(BaseModel):
    """Field names (data/total_pages) match every other Paginated*Response in this
    app (finance/study/habit) — this used to be the one outlier (items/pages)."""
    data: list[ActivityRecordResponse]
    total: int
    page: int
    limit: int
    total_pages: int
