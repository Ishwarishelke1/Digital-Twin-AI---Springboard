"""
scripts/fix_legacy_goal_ids.py — Repairs embedded goals whose goal_id is an
ObjectId instead of a string.

models/user.py declares ActiveGoal.goal_id as a str (a UUID string, per the
comment there: "compatible with MongoDB ObjectId-less embedded docs"). At least
one document predating that convention stores a real ObjectId, which Pydantic
rejects — so Beanie cannot parse that User document at all. Any request that loads
it (GET /users/me, and anything iterating User.find_all()) raises a
ValidationError and 500s. The account is effectively unusable.

The fix converts the ObjectId to its 24-character hex string, which satisfies the
declared type and keeps the value stable, so nothing referencing that goal by id
breaks.

Dry run by default; --apply is required. Guarded, so running against production
needs the explicit override.

Usage (from backend/):
    python3 scripts/fix_legacy_goal_ids.py                              # dry run
    MONGODB_DB_NAME=<staging> python3 scripts/fix_legacy_goal_ids.py --apply
    DESTRUCTIVE_WRITE_ALLOW_DB=<db> python3 scripts/fix_legacy_goal_ids.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from core.db_guard import require_non_production  # noqa: E402

load_dotenv(str(Path(__file__).resolve().parent.parent.parent / ".env"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair non-string embedded goal_ids.")
    parser.add_argument("--apply", action="store_true", help="write the fix (default: dry run)")
    args = parser.parse_args()

    if args.apply:
        require_non_production("rewrite non-string goal_id values on embedded active_goals")

    db_name = os.environ["MONGODB_DB_NAME"]
    client = MongoClient(os.environ["MONGODB_URI"])
    db = client[db_name]
    print(f"database: {db_name}\n")

    # (collection, mongo field path, human label)
    LINKED_GOAL_COLLECTIONS = [
        ("financial_records", "linked_goal_id"),
        ("study_activities", "linked_goal_id"),
        ("habit_trackings", "linked_goal_id"),
    ]

    fixes: list[tuple] = []

    # users.active_goals[].goal_id
    for user in db.users.find({}, {"email": 1, "active_goals": 1}):
        for index, goal in enumerate(user.get("active_goals") or []):
            gid = goal.get("goal_id")
            if gid is not None and not isinstance(gid, str):
                fixes.append(
                    ("users", user["_id"], f"active_goals.{index}.goal_id", gid,
                     f"{user.get('email')} — goal {goal.get('title')!r}")
                )

    # <records>.linked_goal_id — same legacy shape, and it breaks the same way:
    # Beanie cannot parse the document, so every query touching it 500s.
    for coll, field in LINKED_GOAL_COLLECTIONS:
        for doc in db[coll].find({}, {field: 1}):
            value = doc.get(field)
            if value is not None and not isinstance(value, str):
                fixes.append((coll, doc["_id"], field, value, f"{coll} record"))

    if not fixes:
        print("No non-string id values found — nothing to do.")
        return

    print(f"{len(fixes)} field(s) to repair:\n")
    for coll, _id, path, old, label in fixes:
        print(f"  {coll}.{path}")
        print(f"    {label}")
        print(f"    _id={_id}")
        print(f"    {type(old).__name__}({old})  →  str({str(old)!r})\n")

    if not args.apply:
        print("DRY RUN — nothing written. Re-run with --apply to fix.")
        return

    for coll, _id, path, old, label in fixes:
        result = db[coll].update_one({"_id": _id}, {"$set": {path: str(old)}})
        print(f"  ✓ {coll}.{path}: matched={result.matched_count} modified={result.modified_count}")

    remaining = sum(
        1
        for u in db.users.find({}, {"active_goals": 1})
        for g in (u.get("active_goals") or [])
        if g.get("goal_id") is not None and not isinstance(g.get("goal_id"), str)
    ) + sum(
        1
        for coll, field in LINKED_GOAL_COLLECTIONS
        for d in db[coll].find({}, {field: 1})
        if d.get(field) is not None and not isinstance(d.get(field), str)
    )
    print(f"\n✓ Done. Remaining non-string ids: {remaining}")


if __name__ == "__main__":
    main()
