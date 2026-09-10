"""
models/ai_recommendation.py — Cached LLM-generated recommendations.
Collection: `ai_recommendations`.

WHY THIS IS CACHED AT ALL
The Habits and Study pages render recommendations on every load. Calling an LLM
per page load would be slow, would burn quota on a user who is doing nothing but
navigating, and would hand back different advice each refresh for identical data —
which reads as unreliable even when each individual answer is fine.

So a set is keyed by `context_hash`, a digest of the exact figures the model was
shown. Unchanged data reuses the stored set; log a habit or a study session and
the hash moves, which regenerates. `generated_at` is a second, independent bound:
even with static data the advice is refreshed once the TTL lapses, so a user who
has stalled does not read the same four lines forever.

One document per (user_id, domain), upserted — history is not kept, since an
earlier set of suggestions for data that no longer exists has no use.
"""
from __future__ import annotations

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from models.enums import RecommendationDomain


class AIRecommendation(Document):
    user_id: PydanticObjectId
    domain: RecommendationDomain
    items: list[str] = Field(default_factory=list)
    provider: str = Field(..., max_length=32)
    context_hash: str = Field(..., max_length=64)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "ai_recommendations"
        # Unique per user+domain: the read path looks a set up by exactly this pair,
        # and the write path upserts on it. Without the constraint a failed upsert
        # race would leave two rows and the reader would pick one arbitrarily.
        indexes = [
            IndexModel([("user_id", ASCENDING), ("domain", ASCENDING)], unique=True),
        ]

    class Config:
        populate_by_name = True
