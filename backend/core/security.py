"""
core/security.py — JWT creation/verification and bcrypt password hashing.
Mirrors the authentication intent of the TS layer's password_hash field (users.password_hash).

NOTE: passlib 1.7.4 is incompatible with bcrypt >= 4.x (bcrypt removed __about__ and
enforces strict 72-byte password limits in _finalize_backend_mixin, causing a ValueError
at import/first-use time). We therefore call the `bcrypt` library directly, which gives
identical output format ($2b$ hashes) and is 100% compatible with any existing hashes
stored in MongoDB by the TypeScript layer (which also uses bcrypt directly).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from fastapi import Response
from jose import JWTError, jwt

from core.config import get_settings

settings = get_settings()

_BCRYPT_ROUNDS = 12  # matches typical TS bcrypt default
AUTH_COOKIE_NAME = "access_token"


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Returns a bcrypt $2b$ hash of the provided plain-text password.
    Uses the bcrypt library directly to avoid passlib 1.7.4 / bcrypt >= 4.x incompatibility.
    """
    encoded = plain.encode("utf-8")
    hashed = _bcrypt.hashpw(encoded, _bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Returns True if plain matches the stored bcrypt hash.
    Compatible with hashes produced by both this function and the TS bcrypt layer.
    """
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str, token_version: int = 0, expires_delta: Optional[timedelta] = None
) -> str:
    """
    Creates a signed JWT access token.
    `subject` is the user's MongoDB ObjectId string. `token_version` is embedded as the
    `tv` claim — bumping User.token_version (on logout/password-change) invalidates every
    token minted with an older version, since get_current_user checks this claim against
    the live stored value.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": subject, "tv": token_version, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[tuple[str, int]]:
    """
    Decodes and validates a JWT token.
    Returns (user_id, token_version) if valid, None if expired or invalid.
    A token minted before the `tv` claim existed has no such claim — treated as
    version 0, matching User.token_version's default, so pre-existing sessions
    aren't broken by this claim being introduced.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if not user_id:
            return None
        return user_id, payload.get("tv", 0)
    except JWTError:
        return None


# ─── Auth cookie (httpOnly — the browser frontend's auth mechanism) ────────────
# The Authorization-header path (Swagger UI, non-browser clients) is unaffected —
# see api/dependencies.py's get_current_user, which accepts either, cookie first.

def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
