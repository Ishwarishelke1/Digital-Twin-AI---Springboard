"""
scripts/seed_playwright_user.py — Seeds one realistic user for the Playwright
page walk (docs/TEST_PLAN.md Phase 2.2), against whatever MONGODB_URI/
MONGODB_DB_NAME are in the environment when this runs — never called with no
override, always pointed at a disposable local database by the harness that
invokes it.

Goes through the real service layer (not direct inserts), so the data is
exactly as realistic as a real user's — every write here is a write the app
itself would make, just batched.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import core.database as db_module
from schemas.auth_schema import RegisterRequest
from schemas.finance_schema import FinanceCreateRequest
from schemas.habit_schema import HabitCreateRequest
from schemas.study_schema import StudyCreateRequest
from schemas.user_schema import ActiveGoalCreateRequest
from models.enums import (
    FinancialCategory, GoalCategory, SessionType, TransactionType,
)
from services import finance_service, habit_service, study_service, user_service

EMAIL = "playwright-demo@example.com"
PASSWORD = "a-genuinely-fine-password-1"


async def main() -> None:
    await db_module.connect_to_mongo()

    user = await user_service.create_user(RegisterRequest(
        email=EMAIL, password=PASSWORD, name="Playwright Demo",
        age=28, monthly_income_baseline=Decimal("60000"),
    ))

    now = datetime.now(timezone.utc)

    user = await user_service.add_active_goal(user, ActiveGoalCreateRequest(
        title="Emergency Fund", category=GoalCategory.FINANCE,
        target_value=Decimal("50000"), unit="INR",
        target_date=now + timedelta(days=200),
    ))
    user = await user_service.add_active_goal(user, ActiveGoalCreateRequest(
        title="Finish DSA Course", category=GoalCategory.STUDY,
        target_value=Decimal("30"), unit="sessions",
        target_date=now + timedelta(days=90),
    ))
    user = await user_service.add_active_goal(user, ActiveGoalCreateRequest(
        title="Gym 20 Days", category=GoalCategory.HABIT,
        target_value=Decimal("20"), unit="days",
        target_date=now + timedelta(days=45),
    ))
    finance_goal_id = user.active_goals[0].goal_id
    study_goal_id = user.active_goals[1].goal_id

    for i in range(14):
        d = now - timedelta(days=i * 2)
        await finance_service.create_transaction(str(user.id), FinanceCreateRequest(
            type=TransactionType.EXPENSE, amount=Decimal(str(200 + i * 15)),
            category=FinancialCategory.FOOD, description=f"Groceries #{i}",
            transaction_date=d,
        ))
    for i in range(4):
        d = now - timedelta(days=i * 5)
        await finance_service.create_transaction(str(user.id), FinanceCreateRequest(
            type=TransactionType.SAVINGS_DEPOSIT, amount=Decimal("2500.00"),
            category=FinancialCategory.SAVINGS, description="Monthly saving",
            linked_goal_id=finance_goal_id, transaction_date=d,
        ))
    await finance_service.create_transaction(str(user.id), FinanceCreateRequest(
        type=TransactionType.INCOME, amount=Decimal("60000.00"),
        category=FinancialCategory.SALARY, description="Salary", transaction_date=now,
    ))

    subjects = ["Mathematics", "Computer Science", "Physics"]
    for i in range(10):
        d = now - timedelta(days=i * 3)
        await study_service.log_study_session(str(user.id), StudyCreateRequest(
            subject=subjects[i % len(subjects)], study_hours=Decimal("2.0"),
            session_type=SessionType.PRACTICE_EXAM if i % 3 == 0 else SessionType.DEEP_WORK,
            quiz_marks=Decimal("16") if i % 3 == 0 else None,
            max_quiz_marks=Decimal("20") if i % 3 == 0 else None,
            linked_goal_id=study_goal_id if i % 2 == 0 else None,
            session_date=d,
        ))

    for i in range(10):
        d = now - timedelta(days=i)
        await habit_service.upsert_daily_log(str(user.id), HabitCreateRequest(
            sleep_hours=Decimal("7.5"), exercise_minutes=25 + i,
            water_intake_liters=Decimal("2.0"), screen_time_hours=Decimal("5.0"),
            mood_rating=(i % 5) + 1, log_date=d,
        ))

    await db_module.close_mongo_connection()
    print(f"Seeded {EMAIL} / {PASSWORD}")
    print(f"  user_id={user.id}")
    print(f"  finance_goal_id={finance_goal_id}  study_goal_id={study_goal_id}")


if __name__ == "__main__":
    asyncio.run(main())
