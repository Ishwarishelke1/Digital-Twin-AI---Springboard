"""
tests/test_security.py — Unit tests for core/security.py's JWT token_version ("tv" claim)
backward-compatibility logic: a token minted before this claim existed must still decode
to version 0, matching User.token_version's default, so existing sessions aren't broken
by introducing logout/password-change invalidation.
"""
from datetime import datetime, timedelta, timezone

from jose import jwt

from core.config import get_settings
from core.security import create_access_token, decode_access_token

settings = get_settings()


def test_decode_returns_user_id_and_token_version():
    token = create_access_token(subject="507f1f77bcf86cd799439011", token_version=3)
    result = decode_access_token(token)
    assert result == ("507f1f77bcf86cd799439011", 3)


def test_decode_defaults_token_version_to_zero_when_created_without_one():
    token = create_access_token(subject="507f1f77bcf86cd799439011")
    result = decode_access_token(token)
    assert result == ("507f1f77bcf86cd799439011", 0)


def test_decode_pre_existing_token_with_no_tv_claim_defaults_to_zero():
    """Simulates a token minted before the `tv` claim was introduced at all —
    must still decode successfully with token_version treated as 0."""
    payload = {
        "sub": "507f1f77bcf86cd799439011",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    legacy_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    result = decode_access_token(legacy_token)
    assert result == ("507f1f77bcf86cd799439011", 0)


def test_decode_invalid_token_returns_none():
    assert decode_access_token("not-a-real-token") is None


def test_decode_expired_token_returns_none():
    payload = {
        "sub": "507f1f77bcf86cd799439011",
        "tv": 0,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    expired_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert decode_access_token(expired_token) is None
