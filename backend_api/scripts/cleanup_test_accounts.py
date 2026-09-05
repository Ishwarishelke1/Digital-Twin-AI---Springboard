"""
scripts/cleanup_test_accounts.py — Removes accumulated test accounts and their data.

Automated tests, manual QA and verification runs have created throwaway accounts in
the live database over months. They inflate the user count, pollute any analytics or
model training that reads the users collection, and make it harder to see real usage.

Safety model — deliberately fail-safe:
  - An account is deleted ONLY if its email matches a known test pattern. Anything
    unrecognised is kept, so a new real user is never at risk from a pattern gap.
  - PROTECTED_EMAILS is an explicit second guard for known real/demo accounts.
  - Dry run by default. --apply is required to delete anything.
  - Goes through core/db_guard, so running against production needs the override.
  - Deletion uses user_service.delete_user(), which cascades across all seven
    related collections — a raw users.delete_many() would orphan financial records,
    study activities, habit logs, activity entries, simulations, recommendations
    and assistant feedback.

Usage (from backend_api/):
    python3 scripts/cleanup_test_accounts.py                     # dry run
    python3 scripts/cleanup_test_accounts.py --apply             # delete (non-prod)
    DESTRUCTIVE_WRITE_ALLOW_DB=<db> python3 scripts/cleanup_test_accounts.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import close_mongo_connection, connect_to_mongo  # noqa: E402
from core.db_guard import require_non_production  # noqa: E402
from models.finance import FinancialRecord  # noqa: E402
from models.habit import HabitTracking  # noqa: E402
from models.simulation import Recommendation, Simulation  # noqa: E402
from models.study import StudyActivity  # noqa: E402
from models.activity import UserActivity  # noqa: E402
from models.feedback import AssistantFeedback  # noqa: E402
from models.user import User  # noqa: E402
from services.user_service import delete_user  # noqa: E402

# Emails that must never be deleted regardless of pattern. zohaib@gmail.com is the
# demo account that scripts/seed_zohaib.py and scripts/backtest_forecast_accuracy.py
# both operate on by name — deleting it breaks both.
PROTECTED_EMAILS = {
    "zohaib@gmail.com",
    "sofianchicktay1507@gmail.com",
    "thiriloshaniraju@gmail.com",
    "thiriloshanis@gmail.com",
    "aarav.sharma@example.in",
}

# Only emails matching one of these are eligible for deletion.
TEST_PATTERNS = [
    r"^regression_",
    r"^full_regression_",
    r"^sim_regression_",
    r"^xss_",
    r"^quicktest\d*@",
    r"^testuser\d*_",
    r"^testuser_\d+@",
    r"^testcrud_",
    r"^postmantest@",
    r"^verify_test@",
    r"^duplicate_test@",
    r"^dash_verify_",
    r"^authtest_",
    r"^twin_zero_test_",
    r"^m3test\+",
    r"^m3_trend2_",
    r"^goal-test-",
    # created during this session's verification work
    r"^studio-check-",
    r"^studio-redesign-check-",
    r"^remediation-",
    r"^e2e-goal-",
]
_COMPILED = [re.compile(p, re.I) for p in TEST_PATTERNS]

RELATED = [
    ("financial_records", FinancialRecord),
    ("study_activities", StudyActivity),
    ("habit_trackings", HabitTracking),
    ("user_activities", UserActivity),
    ("simulations", Simulation),
    ("recommendations", Recommendation),
    ("assistant_feedback", AssistantFeedback),
]


def is_test_account(email: str) -> bool:
    if email in PROTECTED_EMAILS:
        return False
    return any(p.match(email) for p in _COMPILED)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Delete accumulated test accounts.")
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args()

    if args.apply:
        require_non_production("delete test accounts and all their related records")

    await connect_to_mongo()
    try:
        users = await User.find_all().to_list()
        targets = [u for u in users if is_test_account(u.email)]
        kept = [u for u in users if not is_test_account(u.email)]

        print(f"{len(users)} accounts total → {len(targets)} match test patterns, {len(kept)} kept\n")

        total_related = 0
        print(f"{'email':<46}{'related records'}")
        print("-" * 66)
        for u in sorted(targets, key=lambda x: x.email):
            counts = {}
            for label, model in RELATED:
                n = await model.find(model.user_id == u.id).count()
                if n:
                    counts[label] = n
            n_total = sum(counts.values())
            total_related += n_total
            detail = ", ".join(f"{k}={v}" for k, v in counts.items()) or "none"
            print(f"  {u.email[:42]:<44}{n_total:>4}  {detail}")

        print("-" * 66)
        print(f"{len(targets)} accounts, {total_related} related records\n")

        print("KEPT (not matching any test pattern, or explicitly protected):")
        for u in sorted(kept, key=lambda x: x.email):
            tag = "  [protected]" if u.email in PROTECTED_EMAILS else ""
            print(f"  {u.email}{tag}")

        if not args.apply:
            print("\nDRY RUN — nothing deleted. Re-run with --apply to proceed.")
            return

        print("\nDeleting…")
        for u in targets:
            await delete_user(u)  # cascades across all related collections
        print(f"✓ Deleted {len(targets)} accounts and {total_related} related records.")

        remaining = await User.find_all().count()
        print(f"  users remaining: {remaining}")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
