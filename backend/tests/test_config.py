"""
tests/test_config.py — Covers the two startup guards deployability depends on.

Neither had a test before this file. Both are the kind of thing that only
matters once — at the moment someone deploys with the wrong environment — and
by definition that is not a moment anyone is watching closely, which is exactly
when an untested guard turns out not to fire.

Every Settings() call here passes `_env_file=None` so the test is isolated from
whatever the real root .env happens to contain — this file exercises the
validation logic, not this developer's local configuration.
"""
import pytest
from pydantic import ValidationError

from core.config import Settings, _INSECURE_JWT_SECRET_PLACEHOLDER


# ─── JWT_SECRET_KEY must not ship as the public placeholder ──────────────────

def test_placeholder_jwt_secret_is_rejected():
    """The one line standing between a deploy that forgot to set a real secret
    and every token in production being signable by anyone who has read this
    open-source repo."""
    with pytest.raises(ValidationError, match="insecure placeholder"):
        Settings(JWT_SECRET_KEY=_INSECURE_JWT_SECRET_PLACEHOLDER, _env_file=None)


def test_omitting_jwt_secret_entirely_is_also_rejected():
    """The placeholder is also the field's own default, so an env with no
    JWT_SECRET_KEY at all must fail exactly the same way as one that set it
    to the placeholder explicitly — not start up quietly with it."""
    with pytest.raises(ValidationError, match="insecure placeholder"):
        Settings(_env_file=None)


def test_a_real_jwt_secret_is_accepted():
    settings = Settings(JWT_SECRET_KEY="a-real-secret-value", _env_file=None)
    assert settings.JWT_SECRET_KEY == "a-real-secret-value"


# ─── COOKIE_SECURE follows NODE_ENV unless explicitly overridden ─────────────
#
# Found while containerising the app for docs/TEST_PLAN.md Phase 0: setting
# NODE_ENV=production alone hid /api/docs and engaged require_non_production()
# — both genuinely worked — but shipped the auth cookie with no Secure flag,
# because COOKIE_SECURE was a second, independent variable nobody had also set.
# One guard doing its job while a second, easy-to-forget one silently didn't.

def test_cookie_secure_defaults_off_in_development():
    settings = Settings(JWT_SECRET_KEY="x", _env_file=None)
    assert settings.is_production is False
    assert settings.cookie_secure is False


def test_cookie_secure_follows_production_with_no_override():
    settings = Settings(JWT_SECRET_KEY="x", NODE_ENV="production", _env_file=None)
    assert settings.is_production is True
    assert settings.cookie_secure is True


def test_cookie_secure_explicit_override_still_wins_in_production():
    """An internal, non-HTTPS production deploy is unusual but not this
    project's call to forbid — the explicit value must still be honoured."""
    settings = Settings(
        JWT_SECRET_KEY="x", NODE_ENV="production", COOKIE_SECURE=False, _env_file=None
    )
    assert settings.cookie_secure is False


def test_cookie_secure_explicit_true_holds_in_development_too():
    settings = Settings(JWT_SECRET_KEY="x", COOKIE_SECURE=True, _env_file=None)
    assert settings.is_production is False
    assert settings.cookie_secure is True
