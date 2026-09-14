"""
api/dependencies.py — Reusable FastAPI dependency injection functions.
`get_current_user` is the primary auth guard used by all protected endpoints.
"""
import logging
from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from beanie import PydanticObjectId
from core.security import AUTH_COOKIE_NAME, decode_access_token
from core.exceptions import AuthenticationError
from models.user import User

logger = logging.getLogger("digital_twin_ai.auth")

# auto_error=False: a cookie-only request (no Authorization header at all) must not
# be rejected by this dependency before get_current_user gets a chance to check the
# cookie — see get_current_user below.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def _validate_token_and_get_user(token: Optional[str]) -> User:
    """
    Decodes the JWT and returns the live User document from MongoDB.
    Raises HTTP 401 if there's no token, or it's invalid/expired, the user no longer
    exists, or the token's version has been superseded by a logout/password change.
    Split out from get_current_user so it's directly callable with a bare token
    string in tests, without needing to construct a Request.
    """
    if not token:
        raise AuthenticationError("Could not validate credentials.")

    decoded = decode_access_token(token)
    if not decoded:
        logger.warning("Invalid or expired JWT token presented.")
        raise AuthenticationError("Could not validate credentials.")
    user_id, token_version = decoded

    user = await User.get(PydanticObjectId(user_id))
    if not user:
        logger.warning("JWT references non-existent user_id: %s", user_id)
        raise AuthenticationError("User account not found.")

    if token_version != user.token_version:
        logger.warning("Stale token_version for user %s (token had %s, current is %s).",
                        user_id, token_version, user.token_version)
        raise AuthenticationError("Session has been invalidated. Please log in again.")

    return user


async def get_current_user(
    request: Request,
    bearer_token: Annotated[Optional[str], Depends(oauth2_scheme)],
) -> User:
    """
    Resolves the current user from either an httpOnly `access_token` cookie (the
    browser frontend's auth mechanism) or a bearer Authorization header (kept for
    Swagger UI's Authorize flow, and any non-browser API client) — cookie takes
    priority when both are present. This is the FastAPI equivalent of the TS
    layer's getTwinContext() O(1) read.
    """
    token = request.cookies.get(AUTH_COOKIE_NAME) or bearer_token
    return await _validate_token_and_get_user(token)


# Convenience type alias for use in endpoint signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
