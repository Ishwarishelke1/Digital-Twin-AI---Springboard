"""
schemas/finance_schema.py — Pydantic request/response schemas for finance endpoints.
Field names mirror backend/database/schemas/finance_schema.ts exactly.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from models.enums import TransactionType, FinancialCategory, RecurringFrequency


class FinanceCreateRequest(BaseModel):
    """POST /api/v1/finance/transactions"""
    type: TransactionType
    amount: Decimal = Field(..., gt=0, description="Must be strictly > 0.00")
    category: FinancialCategory
    description: Optional[str] = Field(default=None, max_length=255)
    is_recurring: bool = False
    recurring_frequency: Optional[RecurringFrequency] = None
    linked_goal_id: Optional[str] = None
    transaction_date: Optional[datetime] = None

    @model_validator(mode="after")
    def frequency_required_when_recurring(self) -> "FinanceCreateRequest":
        """Mirrors: required: function() { return this.is_recurring === true; }"""
        if self.is_recurring and not self.recurring_frequency:
            raise ValueError("recurring_frequency is required when is_recurring is True.")
        return self

class FinanceUpdateRequest(BaseModel):
    """PATCH /api/v1/finance/transactions/{id}"""
    type: Optional[TransactionType] = None
    amount: Optional[Decimal] = Field(None, gt=0, description="Must be strictly > 0.00")
    category: Optional[FinancialCategory] = None
    description: Optional[str] = Field(default=None, max_length=255)
    is_recurring: Optional[bool] = None
    recurring_frequency: Optional[RecurringFrequency] = None
    linked_goal_id: Optional[str] = None
    transaction_date: Optional[datetime] = None

    # No "frequency required when recurring" validator here, unlike
    # FinanceCreateRequest — this is a PATCH payload, not the full record. A
    # request that only sends {"is_recurring": true} is valid as long as the
    # *existing* record already has recurring_frequency set; this schema can't
    # see that, only the merged record can, so that check happens in
    # finance_service.update_transaction instead (same fix already applied to
    # StudyUpdateRequest for the identical quiz/exam-marks issue).


class FinanceRecordResponse(BaseModel):
    """Response schema for a single financial record."""
    id: str
    user_id: str
    type: TransactionType
    amount: Decimal
    category: FinancialCategory
    description: Optional[str]
    is_recurring: bool
    recurring_frequency: Optional[RecurringFrequency]
    linked_goal_id: Optional[str]
    transaction_date: datetime
    created_at: datetime


class PaginatedFinanceResponse(BaseModel):
    data: list[FinanceRecordResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class MonthlyCashflowItem(BaseModel):
    """Monthly aggregated cashflow row for ML feature pipelines."""
    year: int
    month: int
    type: TransactionType
    total_amount: Decimal
    transaction_count: int


class CategoryBreakdownItem(BaseModel):
    category: str
    total_amount: Decimal
    percentage_of_total: float
