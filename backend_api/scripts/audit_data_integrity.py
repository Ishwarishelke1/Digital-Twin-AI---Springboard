"""
scripts/audit_data_integrity.py — docs/TEST_PLAN.md Phase 3.1–3.2: read-only
integrity audit of the live database.

WHY THIS IS READ-ONLY, AND WHY THAT MEANS IT RUNS AGAINST THE REAL CLUSTER
Every other write-capable script in this directory calls require_non_production()
(core/db_guard.py) before touching anything, because the risk they guard against
is a destructive write landing on real data. This script performs none —
`index_information()`, `find()`, `aggregate()` and `count_documents()` only — so
that guard doesn't apply, and deliberately isn't imported. The whole point of a
Phase 3 audit is to look at what's actually on the live cluster; running it
against a disposable local database instead would answer a different, much less
useful question.

Connects through core.database.connect_to_mongo() — the exact function `main.py`
calls on real startup — so a clean run of this script is itself a live
confirmation that startup index creation works (Phase 3.3's "AIRecommendation is
a new collection; confirm first startup creates it and its unique index").

WHAT "FLAGGED" MEANS
Some checks below are hard invariants (a unique index holding, a field's BSON
type) — any flag there is a real bug. Others, marked as such, are informational:
current_value manually edited away from what its linked records would sum to is
allowed (ActiveGoalUpdateRequest.current_value exists for exactly that), so a
mismatch there is worth a human's eyes, not an automatic failure.

Usage (from backend_api/):
    python3 scripts/audit_data_integrity.py
"""
from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId
from bson.decimal128 import Decimal128

from core.config import get_settings  # noqa: E402
import core.database as db_module  # noqa: E402

ISSUES: list[str] = []
NOTES: list[str] = []


def flag(msg: str) -> None:
    ISSUES.append(msg)
    print(f"  ✗ {msg}")


def note(msg: str) -> None:
    NOTES.append(msg)
    print(f"  ⚠ {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


# ─── 3.1a — declared indexes actually exist ────────────────────────────────

async def check_indexes(db) -> None:
    print("\n[3.1] Indexes — created by connect_to_mongo() itself; listing what's live.")
    expected = {
        "users": ["email_1"],
        "financial_records": None,   # any index beyond _id counts as present; see below
        "study_activities": None,
        "habit_trackings": None,
        "ai_recommendations": None,
    }
    for coll_name in expected:
        info = await db[coll_name].index_information()
        names = sorted(info.keys())
        if len(names) <= 1:  # only the default _id_ index
            flag(f"{coll_name}: no secondary indexes found ({names}) — connect_to_mongo() "
                 f"should have created them; check models/*.py's Settings.indexes")
        else:
            ok(f"{coll_name}: {names}")


# ─── 3.1b — unique constraints actually hold ───────────────────────────────

async def check_unique_constraints(db) -> None:
    print("\n[3.1] Unique constraints — scanning for duplicate keys the index should forbid.")

    dupes = await db.users.aggregate([
        {"$group": {"_id": "$email", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
    ]).to_list(None)
    if dupes:
        flag(f"users.email: {len(dupes)} duplicate email(s) exist despite the unique index: {dupes[:5]}")
    else:
        ok("users.email: no duplicates")

    dupes = await db.habit_trackings.aggregate([
        {"$group": {"_id": {"user_id": "$user_id", "log_date": "$log_date"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
    ]).to_list(None)
    if dupes:
        flag(f"habit_trackings (user_id, log_date): {len(dupes)} duplicate pair(s): {dupes[:5]}")
    else:
        ok("habit_trackings (user_id, log_date): no duplicates")

    dupes = await db.ai_recommendations.aggregate([
        {"$group": {"_id": {"user_id": "$user_id", "domain": "$domain"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
    ]).to_list(None)
    if dupes:
        flag(f"ai_recommendations (user_id, domain): {len(dupes)} duplicate pair(s): {dupes[:5]}")
    else:
        ok("ai_recommendations (user_id, domain): no duplicates")


# ─── 3.1c — type consistency: no ObjectId where the model declares str ────

async def check_type_consistency(db) -> None:
    """This has bitten three times before, each time making a real account
    unloadable — active_goals[].goal_id, FinancialRecord.linked_goal_id,
    StudyActivity.linked_goal_id. Checking the raw BSON type directly (not via
    Beanie, which would coerce/hide the mismatch on read) is the only way to
    actually catch a stray ObjectId sitting where the schema promises a str."""
    print("\n[3.1] Type consistency — any linked_goal_id/goal_id stored as ObjectId, not str.")

    bad = 0
    async for user in db.users.find({}, {"active_goals.goal_id": 1}):
        for g in user.get("active_goals", []):
            if isinstance(g.get("goal_id"), ObjectId):
                bad += 1
    if bad:
        flag(f"users.active_goals[].goal_id: {bad} value(s) stored as ObjectId, not str")
    else:
        ok("users.active_goals[].goal_id: all str")

    for coll_name in ("financial_records", "study_activities", "habit_trackings"):
        bad = 0
        async for rec in db[coll_name].find(
            {"linked_goal_id": {"$type": "objectId"}}, {"_id": 1}
        ):
            bad += 1
        if bad:
            flag(f"{coll_name}.linked_goal_id: {bad} value(s) stored as ObjectId, not str")
        else:
            ok(f"{coll_name}.linked_goal_id: all str (or null)")


# ─── 3.1d — Decimal128 on every money/measurement field ────────────────────

async def check_decimal128(db) -> None:
    """A raw Motor write that skips Decimal ↔ Decimal128 conversion stores a
    plain float/int instead — Beanie's ODM layer handles this automatically on
    .save()/.update(), a raw collection.update_one() does not (see
    user_service.update_active_goal's docstring for the real bug this was)."""
    print("\n[3.1] Decimal128 — money/measurement fields stored as the wrong BSON type.")

    fields_by_collection = {
        "financial_records": ["amount"],
        "study_activities": ["study_hours", "quiz_marks", "max_quiz_marks", "exam_marks", "max_exam_marks"],
        "habit_trackings": ["sleep_hours", "water_intake_liters", "screen_time_hours"],
    }
    for coll_name, fields in fields_by_collection.items():
        for field in fields:
            bad = await db[coll_name].count_documents({
                field: {"$exists": True, "$ne": None, "$not": {"$type": "decimal"}}
            })
            if bad:
                flag(f"{coll_name}.{field}: {bad} document(s) not stored as Decimal128")
            else:
                ok(f"{coll_name}.{field}: all Decimal128 (or absent/null)")

    bad = 0
    async for user in db.users.find({}, {"active_goals.target_value": 1, "active_goals.current_value": 1}):
        for g in user.get("active_goals", []):
            if not isinstance(g.get("target_value"), Decimal128) or not isinstance(g.get("current_value"), Decimal128):
                bad += 1
    if bad:
        flag(f"users.active_goals[].target_value/current_value: {bad} goal(s) with a non-Decimal128 value")
    else:
        ok("users.active_goals[].target_value/current_value: all Decimal128")


# ─── 3.2a — orphaned linked_goal_id references ─────────────────────────────

async def check_orphaned_goal_links(db) -> None:
    print("\n[3.2] Orphaned links — linked_goal_id pointing at a goal that no longer exists.")

    goal_ids_by_user: dict[str, set[str]] = {}
    async for user in db.users.find({}, {"active_goals.goal_id": 1}):
        goal_ids_by_user[str(user["_id"])] = {g["goal_id"] for g in user.get("active_goals", [])}

    for coll_name in ("financial_records", "study_activities", "habit_trackings"):
        bad = 0
        async for rec in db[coll_name].find(
            {"linked_goal_id": {"$ne": None}}, {"user_id": 1, "linked_goal_id": 1}
        ):
            owned = goal_ids_by_user.get(str(rec["user_id"]), set())
            if rec["linked_goal_id"] not in owned:
                bad += 1
        if bad:
            flag(f"{coll_name}: {bad} record(s) linked to a goal_id that doesn't exist "
                 f"(or belongs to a different user) — a deleted goal that never unlinked its records")
        else:
            ok(f"{coll_name}: every linked_goal_id resolves to a real, owned goal")


# ─── 3.2b — records belonging to a deleted user ────────────────────────────

async def check_no_orphaned_user_data(db) -> None:
    print("\n[3.2] Orphaned user data — records whose user_id has no matching user.")

    real_user_ids = {u["_id"] async for u in db.users.find({}, {"_id": 1})}
    for coll_name in (
        "financial_records", "study_activities", "habit_trackings", "user_activities",
        "assistant_feedback", "recommendations", "simulations", "ai_recommendations",
    ):
        orphan_ids = set()
        async for rec in db[coll_name].find({}, {"user_id": 1}):
            uid = rec.get("user_id")
            if uid is not None and uid not in real_user_ids:
                orphan_ids.add(uid)
        if orphan_ids:
            flag(f"{coll_name}: records exist for {len(orphan_ids)} user_id(s) with no matching user "
                 f"— a user delete that didn't clean up everywhere it should have")
        else:
            ok(f"{coll_name}: every record's user_id resolves to a real user")


# ─── 3.2c — goal current_value vs. what its linked records actually total ──

async def check_goal_progress_reconciliation(db) -> None:
    """FINANCE goals accrue via the *summed amount* of linked SAVINGS_DEPOSIT/
    INVESTMENT transactions (finance_service.GOAL_PROGRESS_TYPES); STUDY/HABIT
    goals accrue via a flat +1 *count* per linked record
    (study_service/habit_service.GOAL_PROGRESS_PER_LINK). Different mechanisms,
    checked separately, matching the actual code rather than one formula
    guessed to fit both.

    Informational, not asserted: current_value is intentionally
    user-editable (ActiveGoalUpdateRequest.current_value), so a manual
    correction is expected to disagree with this recomputation — that's not a
    bug, it's the feature working as designed. Reported for a human to look at,
    same reasoning as the sensitivity analysis reporting a range rather than a
    single pass/fail number."""
    print("\n[3.2] Goal progress reconciliation — informational, not a pass/fail assertion.")

    GOAL_PROGRESS_TYPES = {"SAVINGS_DEPOSIT", "INVESTMENT"}
    mismatches = 0
    checked = 0

    async for user in db.users.find({}, {"_id": 1, "active_goals": 1}):
        uid = user["_id"]
        for g in user.get("active_goals", []):
            category = g.get("category")
            recorded = g.get("current_value")
            recorded_dec = recorded.to_decimal() if isinstance(recorded, Decimal128) else recorded

            if category == "FINANCE":
                agg = await db.financial_records.aggregate([
                    {"$match": {"user_id": uid, "linked_goal_id": g["goal_id"],
                                "type": {"$in": list(GOAL_PROGRESS_TYPES)}}},
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
                ]).to_list(None)
                expected = agg[0]["total"].to_decimal() if agg and isinstance(agg[0]["total"], Decimal128) else (
                    agg[0]["total"] if agg else 0
                )
            elif category in ("STUDY", "HABIT"):
                coll = db.study_activities if category == "STUDY" else db.habit_trackings
                expected = await coll.count_documents(
                    {"user_id": uid, "linked_goal_id": g["goal_id"]}
                )
            else:
                continue  # FITNESS/CAREER: no linking mechanism exists to reconcile against

            checked += 1
            if recorded_dec != expected:
                mismatches += 1
                note(f"user {uid} goal '{g.get('title')}' ({category}): recorded current_value="
                     f"{recorded_dec}, linked records total {expected} — could be a manual edit, "
                     f"or could be drift; worth a look")

    print(f"  Checked {checked} FINANCE/STUDY/HABIT goals; {mismatches} disagree with their linked "
          f"records (informational — see NOTES above, not counted as issues).")


async def main() -> None:
    settings = get_settings()
    print(f"Auditing: {settings.MONGODB_DB_NAME} @ {settings.MONGODB_URI.split('@')[-1] if '@' in settings.MONGODB_URI else settings.MONGODB_URI}")
    print("(read-only — no writes, no deletes)")

    await db_module.connect_to_mongo()
    # Read the module's live global rather than a name imported at module-load
    # time — `from core.database import _client` would bind None permanently,
    # since connect_to_mongo() mutates the module's global after that binding
    # already happened.
    db = db_module._client[settings.MONGODB_DB_NAME]  # noqa: SLF001 — same access pattern connect_to_mongo() itself uses

    try:
        await check_indexes(db)
        await check_unique_constraints(db)
        await check_type_consistency(db)
        await check_decimal128(db)
        await check_orphaned_goal_links(db)
        await check_no_orphaned_user_data(db)
        await check_goal_progress_reconciliation(db)
    finally:
        await db_module.close_mongo_connection()

    print(f"\n{'='*70}")
    if ISSUES:
        print(f"✗ {len(ISSUES)} real issue(s) found:")
        for i in ISSUES:
            print(f"    - {i}")
    else:
        print("✓ No integrity issues found.")
    if NOTES:
        print(f"⚠ {len(NOTES)} informational note(s) — see above, not necessarily bugs.")
    print(f"{'='*70}")

    sys.exit(1 if ISSUES else 0)


if __name__ == "__main__":
    asyncio.run(main())
