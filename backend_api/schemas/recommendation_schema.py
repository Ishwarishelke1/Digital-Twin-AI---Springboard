"""
schemas/recommendation_schema.py — AI-written recommendations for the Habits and
Study pages.

`provider` is part of the contract rather than an internal detail: "rules" means
no model wrote these — either nothing has been generated yet, or every provider
failed — and the UI has to say so. A panel that presents fallback text as model
output is the specific dishonesty this field exists to prevent.

`stale` marks a stored set whose figures have since moved or which has aged past
its TTL. It is shown rather than withheld, labelled so the reader knows the data
underneath it has changed.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AIRecommendationResponse(BaseModel):
    items: list[str] = Field(default_factory=list)
    provider: str = Field(..., description='"groq", "gemini", or "rules" when no model answered')
    generated_at: datetime
    cached: bool = Field(..., description="True when served from the stored set rather than just generated")
    stale: bool = Field(
        default=False,
        description="True when the stored set predates the current figures or has aged past its TTL",
    )
