"""
core/db_guard.py — Refuses to run destructive operations against a production
database unless explicitly and specifically authorised.

Why this exists: there is one Atlas cluster, and scripts/seed_zohaib.py opens with
"wipes and re-seeds ... in the live Atlas database". It calls delete_many() on three
collections and overwrites active_goals, using whichever MONGODB_URI/MONGODB_DB_NAME
happens to be loaded from .env at the time — with no environment check and no
confirmation prompt. Running it with the wrong shell environment loaded destroys real
user data with no undo, and MONGODB_DB_NAME defaults to "digital_twin_ai_prod", so a
missing env var fails *toward* production rather than away from it.

Every script that writes or deletes must call require_non_production() before it
touches the database. The check is deliberately noisy and deliberately annoying to
bypass: the override names the exact database, so it cannot be satisfied by a stale
export left in a shell.
"""
from __future__ import annotations

import os

from core.config import get_settings

# Substrings that mark a database name as production. Matched case-insensitively.
_PRODUCTION_MARKERS = ("prod", "production", "live")

# To proceed against a production database, this env var must be set to that exact
# database name — not "1", not "true". Naming the database is the point: it cannot be
# satisfied accidentally, and it cannot be left set from a previous unrelated run
# against a different database.
_OVERRIDE_ENV_VAR = "DESTRUCTIVE_WRITE_ALLOW_DB"


class ProductionWriteBlocked(RuntimeError):
    """Raised when a destructive operation targets a production database."""


def looks_like_production(db_name: str) -> bool:
    lowered = db_name.lower()
    return any(marker in lowered for marker in _PRODUCTION_MARKERS)


def require_non_production(action: str) -> None:
    """Abort unless the configured database is safe to destroy.

    Blocks when NODE_ENV is production, or when the database name looks like a
    production database. Pass the override env var (set to the exact database name)
    to proceed anyway.

    Args:
        action: human-readable description of what is about to happen, e.g.
            "wipe and re-seed zohaib@gmail.com's records". Shown in the error.
    """
    settings = get_settings()
    db_name = settings.MONGODB_DB_NAME
    override = os.environ.get(_OVERRIDE_ENV_VAR)

    blocked_reason = None
    if settings.is_production:
        blocked_reason = "NODE_ENV is set to 'production'"
    elif looks_like_production(db_name):
        blocked_reason = f"the database name {db_name!r} looks like a production database"

    if blocked_reason is None:
        return

    if override == db_name:
        print(
            f"WARNING: proceeding against {db_name!r} because {_OVERRIDE_ENV_VAR} "
            f"names it explicitly. About to: {action}."
        )
        return

    raise ProductionWriteBlocked(
        f"\nRefusing to {action}.\n"
        f"Reason: {blocked_reason}.\n"
        f"Target database: {db_name!r}\n\n"
        f"This operation deletes or overwrites data and cannot be undone.\n\n"
        f"If this is genuinely a throwaway database, point MONGODB_DB_NAME at it.\n"
        f"If you really mean to run this against {db_name!r}, re-run with:\n\n"
        f"    {_OVERRIDE_ENV_VAR}={db_name} python3 <script>\n\n"
        f"Take a backup first — there is currently one cluster and no tested restore path.\n"
    )
