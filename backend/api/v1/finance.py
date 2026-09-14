"""
api/v1/finance.py — Financial data collection endpoints.
POST /api/v1/finance/transactions              → log a new transaction
GET  /api/v1/finance/transactions              → paginated transaction history
GET  /api/v1/finance/analytics/cashflow        → monthly cashflow aggregation (ML pipeline)
GET  /api/v1/finance/analytics/category        → category spending breakdown (donut chart data)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Annotated

from fastapi import APIRouter, Query, status

from api.dependencies import CurrentUser
from models.enums import TransactionType, FinancialCategory
from schemas.finance_schema import (
    FinanceCreateRequest,
    FinanceUpdateRequest,
    FinanceRecordResponse,
    PaginatedFinanceResponse,
    MonthlyCashflowItem,
    CategoryBreakdownItem,
)
import services.finance_service as finance_service
from core.config import get_settings

logger = logging.getLogger("digital_twin_ai.finance_router")
router = APIRouter(prefix="/finance", tags=["Financial Tracking"])

settings = get_settings()


@router.post(
    "/transactions",
    response_model=FinanceRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a new financial transaction",
)
async def create_transaction(
    payload: FinanceCreateRequest,
    current_user: CurrentUser,
) -> FinanceRecordResponse:
    """
    Appends an immutable financial record to the `financial_records` collection.
    Validates recurring_frequency requirement via Pydantic model_validator.
    """
    return await finance_service.create_transaction(str(current_user.id), payload)


@router.patch(
    "/transactions/{transaction_id}",
    response_model=FinanceRecordResponse,
    summary="Update a financial transaction",
)
async def update_transaction(
    transaction_id: str,
    payload: FinanceUpdateRequest,
    current_user: CurrentUser,
) -> FinanceRecordResponse:
    """Updates an existing financial record."""
    return await finance_service.update_transaction(str(current_user.id), transaction_id, payload)


@router.delete(
    "/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a financial transaction",
)
async def delete_transaction(
    transaction_id: str,
    current_user: CurrentUser,
) -> None:
    """Deletes a financial record."""
    await finance_service.delete_transaction(str(current_user.id), transaction_id)


@router.get(
    "/transactions",
    response_model=PaginatedFinanceResponse,
    summary="Get paginated transaction history",
)
async def list_transactions(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    type: Optional[TransactionType] = Query(default=None, alias="type"),
    category: Optional[FinancialCategory] = Query(default=None),
) -> PaginatedFinanceResponse:
    """
    Returns paginated transaction records for the authenticated user.
    Leverages idx_finance_user_date (user_id + transaction_date DESC) ESR index.
    Supports optional filtering by transaction type and category.
    """
    return await finance_service.list_transactions(
        user_id=str(current_user.id),
        page=page,
        limit=limit,
        type_filter=type,
        category_filter=category,
    )


@router.get(
    "/analytics/cashflow",
    response_model=list[MonthlyCashflowItem],
    summary="Monthly cashflow aggregation for ML Random Forest pipeline",
)
async def get_monthly_cashflow(
    current_user: CurrentUser,
    months_back: int = Query(default=6, ge=1, le=24, description="Number of months of history"),
) -> list[MonthlyCashflowItem]:
    """
    Runs the MongoDB aggregation pipeline grouping Income/Expense/Savings by month.
    Python port of getMonthlyCashflowPipeline() from finance_repository.ts.
    """
    start = datetime.now(timezone.utc) - timedelta(days=months_back * 30)
    return await finance_service.get_monthly_cashflow(str(current_user.id), start)


@router.get(
    "/analytics/category",
    response_model=list[CategoryBreakdownItem],
    summary="Category spending breakdown for dashboard donut charts",
)
async def get_category_breakdown(
    current_user: CurrentUser,
    months_back: int = Query(default=1, ge=1, le=12),
) -> list[CategoryBreakdownItem]:
    """
    Runs the MongoDB aggregation pipeline grouping EXPENSE records by category.
    Python port of getCategorySpendingBreakdown() from finance_repository.ts.
    """
    start = datetime.now(timezone.utc) - timedelta(days=months_back * 30)
    return await finance_service.get_category_breakdown(str(current_user.id), start)
