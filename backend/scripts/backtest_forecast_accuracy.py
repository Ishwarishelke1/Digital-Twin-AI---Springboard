"""
One-off script: measures Financial Forecasting accuracy (Milestone 2's "≥85%"
evaluation criterion) via walk-forward backtesting against a real user's actual
transaction history — evidence, not an assumption, same approach as
scripts/benchmark_simulation.py for Milestone 4's "within 5 seconds" criterion.

Pure read/compute — no HTTP, no auth, connects to Mongo directly and calls the
same forecast_service.backtest_accuracy() the API endpoint uses.

Usage (run from backend/, with a real backend/.env or root .env present):
    python3 scripts/backtest_forecast_accuracy.py --email zohaib@gmail.com
"""
import argparse
import asyncio

from core.database import close_mongo_connection, connect_to_mongo
from models.user import User
from services.forecast_service import forecast_service

ACCURACY_THRESHOLD_PCT = 85.0


async def main(email: str) -> None:
    await connect_to_mongo()
    try:
        user = await User.find_one(User.email == email)
        if not user:
            print(f"No user found with email: {email}")
            return

        result = await forecast_service.backtest_accuracy(str(user.id))

        print(f"Backtested forecasting accuracy for {email}\n")
        print(f"{'Series':<12} {'Accuracy':>10} {'Points':>8}")
        print("-" * 32)
        print(f"{'Income':<12} {result.income_accuracy.accuracy_pct:>9.2f}% {result.income_accuracy.points_evaluated:>8}")
        print(f"{'Expense':<12} {result.expense_accuracy.accuracy_pct:>9.2f}% {result.expense_accuracy.points_evaluated:>8}")
        print(f"{'Savings':<12} {result.savings_accuracy.accuracy_pct:>9.2f}% {result.savings_accuracy.points_evaluated:>8}")
        print()

        if result.by_method:
            print("By method tier:")
            for method, acc in result.by_method.items():
                print(f"  {method.value:<20} {acc:>6.2f}%")
            print()

        verdict = "PASS" if result.overall_accuracy_pct >= ACCURACY_THRESHOLD_PCT else "FAIL"
        print(f"Overall accuracy: {result.overall_accuracy_pct:.2f}%")
        print(f"Deliverable check — financial forecasting accuracy ≥{ACCURACY_THRESHOLD_PCT:.0f}%: {verdict}")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest financial forecasting accuracy for a user.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.email))
