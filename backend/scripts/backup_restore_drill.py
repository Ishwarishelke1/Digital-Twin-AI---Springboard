"""
scripts/backup_restore_drill.py — Proves a backup can actually be restored.

An untested backup is not a backup. This dumps the source database, restores it
into a scratch database, and compares per-collection document counts. If the
counts match, the backup is restorable; if the drill fails, you have found that
out now rather than during an incident.

Atlas M0 (free-tier) clusters have no automated backup or point-in-time restore,
so on M0 this mongodump/mongorestore path *is* the backup strategy — which makes
testing it the difference between having a backup and believing you have one.

Safety:
  - The source is only ever read (mongodump).
  - The restore target must not look like production; core/db_guard.py enforces
    this, and the script additionally refuses if target == source.
  - The scratch database is dropped at the end unless --keep is passed.

Usage (from backend/):
    python3 scripts/backup_restore_drill.py                  # full drill, cleans up
    python3 scripts/backup_restore_drill.py --keep           # leave the restored copy
    python3 scripts/backup_restore_drill.py --dump-only      # just take a backup
    python3 scripts/backup_restore_drill.py --out ~/backups  # choose dump location
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from core.db_guard import ProductionWriteBlocked, looks_like_production  # noqa: E402

load_dotenv()


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.exit(
            f"{name} not found. Install the MongoDB Database Tools:\n"
            f"    brew install mongodb-database-tools"
        )
    return path


def _run(cmd: list[str], label: str) -> None:
    print(f"\n→ {label}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # mongodump/mongorestore write progress to stderr, so only surface it on failure.
        print(result.stderr.strip()[-2000:])
        sys.exit(f"✗ {label} failed (exit {result.returncode})")
    print(f"  done")


def _counts(uri: str, db_name: str) -> dict[str, int]:
    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    try:
        db = client[db_name]
        return {c: db[c].count_documents({}) for c in sorted(db.list_collection_names())}
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup and restore verification drill.")
    parser.add_argument("--out", default="./backups", help="directory for the dump (default: ./backups)")
    parser.add_argument("--target", default=None, help="scratch database to restore into")
    parser.add_argument("--keep", action="store_true", help="keep the restored scratch database")
    parser.add_argument("--dump-only", action="store_true", help="take a backup, skip the restore")
    args = parser.parse_args()

    uri = os.environ.get("MONGODB_URI")
    source_db = os.environ.get("MONGODB_DB_NAME")
    if not uri or not source_db:
        sys.exit("MONGODB_URI and MONGODB_DB_NAME must be set (see the root .env).")

    mongodump = _require_tool("mongodump")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out).expanduser().resolve() / f"{source_db}-{stamp}"

    print(f"source database : {source_db}")
    print(f"dump directory  : {out_dir}")

    before = _counts(uri, source_db)
    total = sum(before.values())
    print(f"\nsource contents ({total} documents across {len(before)} collections):")
    for name, n in before.items():
        print(f"  {n:>7}  {name}")

    # ── backup (read-only against the source) ────────────────────────────────
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [mongodump, f"--uri={uri}", f"--db={source_db}", f"--out={out_dir}"],
        f"mongodump {source_db} → {out_dir}",
    )

    dumped = out_dir / source_db
    if not dumped.is_dir():
        sys.exit(f"✗ expected dump at {dumped}, not found")
    size_mb = sum(f.stat().st_size for f in dumped.rglob("*") if f.is_file()) / 1_048_576
    print(f"  dump size: {size_mb:.2f} MB")

    if args.dump_only:
        print(f"\n✓ Backup written to {out_dir}")
        print("  Restore is UNVERIFIED — re-run without --dump-only to prove it works.")
        return

    # ── restore into a scratch database ──────────────────────────────────────
    mongorestore = _require_tool("mongorestore")
    # Deliberately not derived from source_db: "digital_twin_ai_prod_restore_drill"
    # contains "prod" and would (correctly) trip the guard below.
    target_db = args.target or "restore_drill_scratch"

    if target_db == source_db:
        sys.exit("✗ refusing to restore over the source database")
    if looks_like_production(target_db):
        raise ProductionWriteBlocked(
            f"✗ refusing to restore into {target_db!r}, which looks like a production database."
        )

    print(f"\nrestore target  : {target_db}")
    _run(
        [
            mongorestore,
            f"--uri={uri}",
            f"--nsFrom={source_db}.*",
            f"--nsTo={target_db}.*",
            "--drop",
            str(out_dir),
        ],
        f"mongorestore → {target_db}",
    )

    # ── verify ───────────────────────────────────────────────────────────────
    after = _counts(uri, target_db)
    print("\nverification (source → restored):")
    ok = True
    for name in sorted(set(before) | set(after)):
        src, dst = before.get(name, 0), after.get(name, 0)
        mark = "✓" if src == dst else "✗"
        if src != dst:
            ok = False
        print(f"  {mark} {name:<28} {src:>7} → {dst:>7}")

    if not args.keep:
        client = MongoClient(uri, serverSelectionTimeoutMS=15000)
        try:
            client.drop_database(target_db)
            print(f"\ncleaned up scratch database {target_db!r}")
        finally:
            client.close()
    else:
        print(f"\nkept scratch database {target_db!r} (--keep)")

    if ok:
        print(f"\n✓ DRILL PASSED — backup at {out_dir} is restorable.")
        print("  Keep this dump somewhere off the cluster; a backup stored only on")
        print("  the thing it protects is not a backup.")
    else:
        sys.exit("\n✗ DRILL FAILED — counts differ. Do not rely on this backup.")


if __name__ == "__main__":
    main()
