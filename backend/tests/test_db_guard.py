"""
tests/test_db_guard.py — Covers the production-write guard.

This protects against a concrete, live risk: scripts/seed_zohaib.py calls
delete_many() on three collections and overwrites active_goals, against whichever
database .env happens to point at. The repo has one Atlas cluster whose database is
named "digital_twin_ai_prod", and MONGODB_DB_NAME defaults to that name — so a
missing env var fails *toward* production.

No DB connection: the guard only reads settings and os.environ.
"""
import os
from unittest.mock import patch

import pytest

from core.db_guard import (
    ProductionWriteBlocked,
    looks_like_production,
    require_non_production,
)

ACTION = "wipe everything"


def _settings(db_name: str, node_env: str = "development"):
    """A stand-in for the cached Settings singleton."""
    class _S:
        MONGODB_DB_NAME = db_name
        NODE_ENV = node_env

        @property
        def is_production(self) -> bool:
            return self.NODE_ENV == "production"

    return _S()


def _patch_settings(db_name: str, node_env: str = "development"):
    return patch("core.db_guard.get_settings", return_value=_settings(db_name, node_env))


@pytest.mark.parametrize(
    "name,expected",
    [
        ("digital_twin_ai_prod", True),
        ("digital_twin_ai_production", True),
        ("dt_live", True),
        ("DIGITAL_TWIN_PROD", True),   # case-insensitive
        ("digital_twin_ai_staging", False),
        ("digital_twin_ai_test", False),
        ("scratch", False),
    ],
)
def test_looks_like_production(name, expected):
    assert looks_like_production(name) is expected


def test_blocks_on_production_database_name():
    with _patch_settings("digital_twin_ai_prod"), patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ProductionWriteBlocked) as exc:
            require_non_production(ACTION)
    # The message must name the database and the action — a generic "blocked" is
    # not actionable at 2am.
    assert "digital_twin_ai_prod" in str(exc.value)
    assert ACTION in str(exc.value)


def test_blocks_when_node_env_is_production_even_if_db_name_looks_safe():
    with _patch_settings("scratch", node_env="production"), patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ProductionWriteBlocked):
            require_non_production(ACTION)


def test_allows_non_production_database():
    with _patch_settings("digital_twin_ai_staging"), patch.dict(os.environ, {}, clear=True):
        require_non_production(ACTION)  # must not raise


def test_override_must_name_the_exact_database():
    """A truthy value is not enough — the override names the database so it can't
    be satisfied by a stale export left over from an unrelated run."""
    with _patch_settings("digital_twin_ai_prod"):
        for value in ("1", "true", "yes", "some_other_db"):
            with patch.dict(os.environ, {"DESTRUCTIVE_WRITE_ALLOW_DB": value}, clear=True):
                with pytest.raises(ProductionWriteBlocked):
                    require_non_production(ACTION)


def test_override_with_exact_database_name_permits(capsys):
    with _patch_settings("digital_twin_ai_prod"), patch.dict(
        os.environ, {"DESTRUCTIVE_WRITE_ALLOW_DB": "digital_twin_ai_prod"}, clear=True
    ):
        require_non_production(ACTION)  # must not raise

    # Proceeding must still be loud.
    assert "WARNING" in capsys.readouterr().out
