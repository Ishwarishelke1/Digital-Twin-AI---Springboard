"""
models/finance.py — Beanie ODM Document mirroring backend/database/schemas/finance_schema.ts.
Collection: `financial_records`
Immutable ledger: no updated_at per TS design decision ("Ledger entries are immutable!").
DO NOT alter field names — they map directly to existing MongoDB documents.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from beanie import Document, DecimalAnnotation, PydanticObjectId
from pydantic import Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from models.enums import TransactionType, FinancialCategory, RecurringFrequency


class FinancialRecord(Document):
    user_id: PydanticObjectId
    type: TransactionType
    amount: DecimalAnnotation = Field(..., gt=0, description="Must be strictly greater than 0.00")
    category: FinancialCategory
    description: Optional[str] = Field(default=None, max_length=255)
    is_recurring: bool = False
    recurring_frequency: Optional[RecurringFrequency] = None
    # str, not PydanticObjectId: active_goals.goal_id is a UUID string (models/user.py),
    # not a Mongo ObjectId — this field must match that type to actually be usable.
    linked_goal_id: Optional[str] = None
    transaction_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("recurring_frequency", mode="before")
    @classmethod
    def frequency_required_when_recurring(cls, v, info):
        # mirrors: required: function() { return this.is_recurring === true; }
        # Full cross-field check is done in the service layer before insert.
        return v

    class Settings:
        name = "financial_records"  # ← Exact collection name from TS layer
        # These already exist on the live database (created out-of-band, before this
        # model declared them) — declared here so a fresh database gets them too.
        # Names/keys match the live indexes exactly so Beanie's startup sync is a
        # no-op against the existing collection.
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("transaction_date", DESCENDING)],
                name="idx_finance_user_date",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("category", ASCENDING), ("transaction_date", DESCENDING)],
                name="idx_finance_user_cat_date",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("type", ASCENDING), ("transaction_date", DESCENDING)],
                name="idx_finance_user_type_date",
            ),
        ]

    class Config:
        populate_by_name = True
