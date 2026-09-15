"""
tests/test_finance_service.py — Unit tests for services/finance_service.py.

No real DB/network — patches the specific Beanie I/O calls each function makes
(record.insert()/.save()/.delete(), FinancialRecord.find_one/.find/.aggregate) with
mocks, mirroring the style of tests/test_forecast_service.py.
"""
from datetime import datetime, timezone
from decimal import Decimal
from bson.decimal128 import Decimal128
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId
from bson import Decimal128

from core.exceptions import NotFoundError
from models.enums import FinancialCategory, TransactionType
from models.finance import FinancialRecord
from models.user import User
from schemas.finance_schema import FinanceCreateRequest, FinanceUpdateRequest
import services.finance_service as finance_service

USER_ID = "507f1f77bcf86cd799439011"
TXN_ID = "507f1f77bcf86cd799439022"
GOAL_ID = "beb887d1-50ef-45cf-8c1f-5d00d3cdfe12"


def _fake_insert():
    async def insert(self):
        self.id = PydanticObjectId(TXN_ID)
        return self
    return insert


def _patch_document_init():
    """FinancialRecord's normal __init__ (used by finance_service.create_transaction,
    which constructs via `FinancialRecord(...)` rather than `.model_construct(...)`)
    calls get_motor_collection(), which raises CollectionWasNotInitialized unless
    init_beanie() has run against a real DB. Patch it to a harmless mock for construction."""
    return patch.object(FinancialRecord, "get_motor_collection", return_value=MagicMock())


def _patch_goal_update():
    """Mocks the atomic $inc call _adjust_linked_goal_progress makes against
    User's raw Motor collection — returns the mock so a test can assert on
    the exact update_one(...) call it received."""
    collection = MagicMock()
    collection.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    async def _echo(query, update, **kwargs):
        return {
            "active_goals": [
                {
                    "goal_id": query.get("active_goals.goal_id"),
                    "current_value": Decimal128("1"),
                    "target_value": Decimal128("100"),
                    "status": "ACTIVE",
                    "completed_at": None,
                }
            ]
        }

    collection.find_one_and_update = AsyncMock(side_effect=_echo)
    return patch.object(User, "get_motor_collection", return_value=collection), collection


# ─── create_transaction ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_transaction_normal_case():
    payload = FinanceCreateRequest(type=TransactionType.INCOME, amount=Decimal("5000"), category=FinancialCategory.SALARY)
    with _patch_document_init(), \
         patch.object(FinancialRecord, "insert", new=_fake_insert()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()):
        result = await finance_service.create_transaction(USER_ID, payload)
    assert result.type == TransactionType.INCOME
    assert result.amount == Decimal("5000")
    assert result.id == TXN_ID


@pytest.mark.asyncio
async def test_create_transaction_linked_goal_id_passed_through_as_str():
    """Regression check: linked_goal_id must survive as a plain str (ActiveGoal.goal_id
    is a UUID string, not a Mongo ObjectId — this used to be silently miscast)."""
    payload = FinanceCreateRequest(
        type=TransactionType.SAVINGS_DEPOSIT, amount=Decimal("500"),
        category=FinancialCategory.SAVINGS, linked_goal_id=GOAL_ID,
    )
    goal_patch, _ = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(FinancialRecord, "insert", new=_fake_insert()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        result = await finance_service.create_transaction(USER_ID, payload)
    assert result.linked_goal_id == GOAL_ID


@pytest.mark.asyncio
async def test_create_transaction_savings_deposit_increments_linked_goal():
    """A SAVINGS_DEPOSIT linked to a goal should atomically $inc its progress."""
    payload = FinanceCreateRequest(
        type=TransactionType.SAVINGS_DEPOSIT, amount=Decimal("500"),
        category=FinancialCategory.SAVINGS, linked_goal_id=GOAL_ID,
    )
    goal_patch, collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(FinancialRecord, "insert", new=_fake_insert()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await finance_service.create_transaction(USER_ID, payload)

    collection.find_one_and_update.assert_awaited_once()
    filter_arg, update_arg = collection.find_one_and_update.call_args.args
    assert filter_arg == {"_id": PydanticObjectId(USER_ID), "active_goals.goal_id": GOAL_ID}
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("500")


@pytest.mark.asyncio
async def test_create_transaction_expense_does_not_touch_linked_goal():
    """Regression test for a real bug: an EXPENSE linked to a goal used to add
    its raw amount to the goal's progress regardless of type — spending counted
    as savings. Only SAVINGS_DEPOSIT/INVESTMENT/INCOME should move a goal's
    current_value."""
    payload = FinanceCreateRequest(
        type=TransactionType.EXPENSE, amount=Decimal("200"),
        category=FinancialCategory.FOOD, linked_goal_id=GOAL_ID,
    )
    goal_patch, collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(FinancialRecord, "insert", new=_fake_insert()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await finance_service.create_transaction(USER_ID, payload)

    collection.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_transaction_income_increments_linked_goal():
    """An INCOME linked to a goal counts as progress too — earmarking money
    you've received toward a goal (e.g. salary set aside for a purchase) is
    genuine progress, the same reasoning as SAVINGS_DEPOSIT/INVESTMENT."""
    payload = FinanceCreateRequest(
        type=TransactionType.INCOME, amount=Decimal("21000"),
        category=FinancialCategory.SALARY, linked_goal_id=GOAL_ID,
    )
    goal_patch, collection = _patch_goal_update()
    with _patch_document_init(), \
         patch.object(FinancialRecord, "insert", new=_fake_insert()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await finance_service.create_transaction(USER_ID, payload)

    collection.find_one_and_update.assert_awaited_once()
    filter_arg, update_arg = collection.find_one_and_update.call_args.args
    assert filter_arg == {"_id": PydanticObjectId(USER_ID), "active_goals.goal_id": GOAL_ID}
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("21000")


# ─── update_transaction ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_transaction_normal_case():
    record = FinancialRecord.model_construct(
        user_id=PydanticObjectId(USER_ID), type=TransactionType.EXPENSE, amount=Decimal("100"),
        category=FinancialCategory.FOOD, description=None, is_recurring=False,
        recurring_frequency=None, linked_goal_id=None,
        transaction_date=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(TXN_ID)

    with patch.object(FinancialRecord, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(FinancialRecord, "save", new=AsyncMock()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()):
        result = await finance_service.update_transaction(
            USER_ID, TXN_ID, FinanceUpdateRequest(amount=Decimal("250"))
        )
    assert result.amount == Decimal("250")


@pytest.mark.asyncio
async def test_update_transaction_reconciles_linked_goal_amount_change():
    """Regression test: editing a goal-linked SAVINGS_DEPOSIT's amount must adjust
    the goal by the *net* difference, not add the new amount on top of the old
    (which would double-count what the original create_transaction already applied)."""
    record = FinancialRecord.model_construct(
        user_id=PydanticObjectId(USER_ID), type=TransactionType.SAVINGS_DEPOSIT, amount=Decimal("300"),
        category=FinancialCategory.SAVINGS, description=None, is_recurring=False,
        recurring_frequency=None, linked_goal_id=GOAL_ID,
        transaction_date=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    record.id = PydanticObjectId(TXN_ID)

    goal_patch, collection = _patch_goal_update()
    with patch.object(FinancialRecord, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(FinancialRecord, "save", new=AsyncMock()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await finance_service.update_transaction(
            USER_ID, TXN_ID, FinanceUpdateRequest(amount=Decimal("500"))
        )

    collection.find_one_and_update.assert_awaited_once()
    _, update_arg = collection.find_one_and_update.call_args.args
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("200")  # 500 - 300


@pytest.mark.asyncio
async def test_update_transaction_not_found_bad_id_format():
    with pytest.raises(NotFoundError):
        await finance_service.update_transaction(USER_ID, "not-an-object-id", FinanceUpdateRequest())


@pytest.mark.asyncio
async def test_update_transaction_not_found_valid_id_no_match():
    with patch.object(FinancialRecord, "find_one", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await finance_service.update_transaction(USER_ID, TXN_ID, FinanceUpdateRequest())


# ─── delete_transaction ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_transaction_normal_case():
    record = FinancialRecord.model_construct(
        user_id=PydanticObjectId(USER_ID), type=TransactionType.EXPENSE, amount=Decimal("100"),
        category=FinancialCategory.FOOD,
    )
    record.id = PydanticObjectId(TXN_ID)

    with patch.object(FinancialRecord, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(FinancialRecord, "delete", new=AsyncMock()) as mock_delete, \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()):
        await finance_service.delete_transaction(USER_ID, TXN_ID)
    mock_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_transaction_reverses_linked_goal_progress():
    """Regression test: deleting a goal-linked SAVINGS_DEPOSIT must subtract what
    it had contributed — otherwise the goal stays credited for a transaction that
    no longer exists."""
    record = FinancialRecord.model_construct(
        user_id=PydanticObjectId(USER_ID), type=TransactionType.SAVINGS_DEPOSIT, amount=Decimal("300"),
        category=FinancialCategory.SAVINGS, linked_goal_id=GOAL_ID,
    )
    record.id = PydanticObjectId(TXN_ID)

    goal_patch, collection = _patch_goal_update()
    with patch.object(FinancialRecord, "find_one", new=AsyncMock(return_value=record)), \
         patch.object(FinancialRecord, "delete", new=AsyncMock()), \
         patch("services.finance_service.activity_service.log_activity", new=AsyncMock()), \
         goal_patch:
        await finance_service.delete_transaction(USER_ID, TXN_ID)

    collection.find_one_and_update.assert_awaited_once()
    _, update_arg = collection.find_one_and_update.call_args.args
    assert update_arg["$inc"]["active_goals.$.current_value"].to_decimal() == Decimal("-300")


@pytest.mark.asyncio
async def test_delete_transaction_not_found():
    with patch.object(FinancialRecord, "find_one", new=AsyncMock(return_value=None)):
        with pytest.raises(NotFoundError):
            await finance_service.delete_transaction(USER_ID, TXN_ID)


# ─── list_transactions ───────────────────────────────────────────────────────────

def _mock_find(records, total):
    query = MagicMock()
    query.to_list = AsyncMock(return_value=records)
    query.count = AsyncMock(return_value=total)
    return MagicMock(return_value=query)


@pytest.mark.asyncio
async def test_list_transactions_pagination_math():
    with patch.object(FinancialRecord, "find", new=_mock_find([], 45)):
        result = await finance_service.list_transactions(USER_ID, page=2, limit=20)
    assert result.total == 45
    assert result.total_pages == 3  # ceil(45/20)
    assert result.page == 2


@pytest.mark.asyncio
async def test_list_transactions_filters_reach_the_query():
    captured = {}

    def fake_find(query_filter, **kwargs):
        captured["filter"] = query_filter
        query = MagicMock()
        query.to_list = AsyncMock(return_value=[])
        query.count = AsyncMock(return_value=0)
        return query

    with patch.object(FinancialRecord, "find", side_effect=fake_find):
        await finance_service.list_transactions(
            USER_ID, type_filter=TransactionType.EXPENSE, category_filter="FOOD"
        )
    assert captured["filter"]["type"] == TransactionType.EXPENSE
    assert captured["filter"]["category"] == "FOOD"


# ─── get_monthly_cashflow ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_monthly_cashflow_maps_aggregation_results():
    raw_results = [
        {"_id": {"year": 2026, "month": 6, "type": "INCOME"}, "total_amount": Decimal128("40000"), "transaction_count": 1},
        {"_id": {"year": 2026, "month": 6, "type": "EXPENSE"}, "total_amount": Decimal128("15000"), "transaction_count": 3},
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=raw_results)

    with patch.object(FinancialRecord, "aggregate", return_value=mock_cursor):
        items = await finance_service.get_monthly_cashflow(
            USER_ID, datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
    assert len(items) == 2
    assert items[0].year == 2026 and items[0].month == 6
    assert items[0].type == TransactionType.INCOME
    assert items[0].total_amount == Decimal("40000")


# ─── get_category_breakdown ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_category_breakdown_percentages_sum_correctly():
    raw_results = [
        {"_id": "HOUSING", "total_amount": Decimal128("6000")},
        {"_id": "FOOD", "total_amount": Decimal128("4000")},
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=raw_results)

    with patch.object(FinancialRecord, "aggregate", return_value=mock_cursor):
        items = await finance_service.get_category_breakdown(
            USER_ID, datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
    assert items[0].category == "HOUSING"
    assert items[0].percentage_of_total == 60.0
    assert items[1].percentage_of_total == 40.0


@pytest.mark.asyncio
async def test_get_category_breakdown_empty_history_no_division_by_zero():
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])

    with patch.object(FinancialRecord, "aggregate", return_value=mock_cursor):
        items = await finance_service.get_category_breakdown(
            USER_ID, datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
    assert items == []
