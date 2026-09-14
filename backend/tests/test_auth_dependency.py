"""
tests/test_auth_dependency.py — Unit tests for api/dependencies.py.
No DB/network — patches User.get and decode_access_token directly.

Most tests target _validate_token_and_get_user directly (the actual token/user
validation logic — decode, 401s, stale token_version) since it's callable with a
bare token string. get_current_user itself is the thin FastAPI-facing wrapper that
picks the token from a cookie or the Authorization header before delegating to it —
covered separately below with a minimal Request-like stand-in.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from beanie import PydanticObjectId

from api.dependencies import _validate_token_and_get_user, get_current_user
from core.exceptions import AuthenticationError
from core.security import create_access_token
from models.user import Profile, User

USER_ID = "507f1f77bcf86cd799439011"


def _user(token_version: int = 0) -> User:
    user = User.model_construct(
        email="depstest@example.com", password_hash="x",
        profile=Profile(name="Dep Test", age=30), token_version=token_version,
    )
    user.id = PydanticObjectId(USER_ID)
    return user


@pytest.mark.asyncio
async def test_valid_token_matching_version_returns_user():
    token = create_access_token(subject=USER_ID, token_version=0)
    with patch.object(User, "get", new=AsyncMock(return_value=_user(token_version=0))):
        result = await _validate_token_and_get_user(token)
    assert str(result.id) == USER_ID


@pytest.mark.asyncio
async def test_garbage_token_rejected():
    with pytest.raises(AuthenticationError):
        await _validate_token_and_get_user("not-a-real-token")


@pytest.mark.asyncio
async def test_token_for_nonexistent_user_rejected():
    token = create_access_token(subject=USER_ID, token_version=0)
    with patch.object(User, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(AuthenticationError):
            await _validate_token_and_get_user(token)


@pytest.mark.asyncio
async def test_stale_token_version_rejected():
    """The core regression test for this session's logout/password-change feature:
    a token minted under an older token_version must be rejected once the user's
    stored version has been bumped (by logout or a password change)."""
    token = create_access_token(subject=USER_ID, token_version=0)
    with patch.object(User, "get", new=AsyncMock(return_value=_user(token_version=1))):
        with pytest.raises(AuthenticationError) as exc_info:
            await _validate_token_and_get_user(token)
    assert "invalidated" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_pre_existing_token_with_no_tv_claim_still_works_for_a_fresh_user():
    """Backward-compatibility check: a user who has never logged out/changed their
    password (token_version still 0) must still authenticate with a legacy-shaped
    token that has no `tv` claim at all (decode_access_token defaults it to 0)."""
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    from core.config import get_settings

    settings = get_settings()
    legacy_payload = {
        "sub": USER_ID,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    legacy_token = jwt.encode(legacy_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    with patch.object(User, "get", new=AsyncMock(return_value=_user(token_version=0))):
        result = await _validate_token_and_get_user(legacy_token)
    assert str(result.id) == USER_ID


# ─── get_current_user: cookie vs. Authorization-header extraction ─────────────
# Only .cookies is ever accessed on the request object, so a SimpleNamespace
# stands in fine — no need for a full Starlette Request.

@pytest.mark.asyncio
async def test_get_current_user_prefers_cookie_over_bearer_header():
    cookie_token = create_access_token(subject=USER_ID, token_version=0)
    header_token = create_access_token(subject="507f1f77bcf86cd799439099", token_version=0)
    request = SimpleNamespace(cookies={"access_token": cookie_token})

    with patch.object(User, "get", new=AsyncMock(return_value=_user(token_version=0))) as mock_get:
        result = await get_current_user(request, header_token)
    assert str(result.id) == USER_ID
    # Confirms the cookie's user_id (USER_ID) was used, not the header's.
    mock_get.assert_awaited_once_with(PydanticObjectId(USER_ID))


@pytest.mark.asyncio
async def test_get_current_user_falls_back_to_bearer_header_with_no_cookie():
    header_token = create_access_token(subject=USER_ID, token_version=0)
    request = SimpleNamespace(cookies={})

    with patch.object(User, "get", new=AsyncMock(return_value=_user(token_version=0))):
        result = await get_current_user(request, header_token)
    assert str(result.id) == USER_ID


@pytest.mark.asyncio
async def test_get_current_user_rejects_when_neither_cookie_nor_header_present():
    request = SimpleNamespace(cookies={})
    with pytest.raises(AuthenticationError):
        await get_current_user(request, None)
