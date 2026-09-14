"""
api/v1/auth.py — Authentication endpoints.
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
"""
import logging

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from api.dependencies import CurrentUser
from beanie.operators import Inc
from core.security import clear_auth_cookie, create_access_token, set_auth_cookie
from core.exceptions import ConflictError, AuthenticationError
from core.rate_limit import limiter
from models.user import User
from schemas.auth_schema import RegisterRequest, LoginRequest, TokenResponse
import services.user_service as user_service

logger = logging.getLogger("digital_twin_ai.auth_router")
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
@limiter.limit("5/minute")
async def register(request: Request, response: Response, payload: RegisterRequest) -> TokenResponse:
    """
    Creates a new user document in the `users` collection.
    Sets an httpOnly session cookie and also returns the JWT in the response body
    (kept for API/schema stability — the browser frontend relies on the cookie only).
    Raises 409 if the email is already registered.
    Rate limited to 5/minute per IP to blunt automated mass-registration.
    """
    user = await user_service.create_user(payload)
    token = create_access_token(subject=str(user.id), token_version=user.token_version)
    set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        email=user.email,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT access token",
)
@limiter.limit("10/minute")
async def login(request: Request, response: Response, payload: LoginRequest) -> TokenResponse:
    """
    Validates credentials, sets an httpOnly session cookie, and also returns the JWT
    in the response body (kept for API/schema stability — the browser frontend
    relies on the cookie only). Rate limited to 10/minute per IP to blunt
    brute-force/credential-stuffing attempts.
    """
    user = await user_service.authenticate_user(payload.email, payload.password)
    token = create_access_token(subject=str(user.id), token_version=user.token_version)
    set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        email=user.email,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate the current session everywhere",
)
async def logout(response: Response, current_user: CurrentUser) -> None:
    """
    Bumps token_version, which immediately invalidates every JWT previously issued
    to this user (not just the one used to call this endpoint) — there's no
    per-device session concept in this app, so logout is "logout everywhere."
    Also clears the cookie directly, so the browser's cookie jar is cleaned up
    immediately rather than just failing auth on the next request.
    """
    await current_user.update(Inc({User.token_version: 1}))
    clear_auth_cookie(response)
    logger.info("User %s logged out (token_version bumped).", current_user.id)
