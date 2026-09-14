"""
core/exceptions.py — Centralised custom exception classes and FastAPI exception handlers.
Covers all MongoDB-specific error types plus domain business logic errors.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError
from slowapi.errors import RateLimitExceeded


# ─── Custom Domain Exceptions ─────────────────────────────────────────────────

class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""
    def __init__(self, resource: str, identifier: str):
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} not found: {identifier}")


class ConflictError(Exception):
    """Raised on unique constraint violations (e.g., duplicate daily habit log)."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BusinessRuleError(Exception):
    """Raised when a business rule is violated (e.g., goals cap exceeded)."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AuthenticationError(Exception):
    """Raised on invalid credentials."""
    def __init__(self, message: str = "Invalid credentials."):
        self.message = message
        super().__init__(message)


class AIProviderUnavailableError(Exception):
    """Raised when every configured LLM provider (Gemini, then Groq) fails or
    none is configured — an upstream dependency being down, not our bug, so
    this maps to 503 rather than 500."""
    def __init__(self, message: str = "The AI assistant is temporarily unavailable. Please try again shortly."):
        self.message = message
        super().__init__(message)


# ─── Exception Handlers ───────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Registers all global exception handlers with the FastAPI app."""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "NOT_FOUND", "message": str(exc)},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "CONFLICT", "message": exc.message},
        )

    @app.exception_handler(BusinessRuleError)
    async def business_rule_handler(request: Request, exc: BusinessRuleError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "BUSINESS_RULE_VIOLATION", "message": exc.message},
        )

    @app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "AUTHENTICATION_FAILED", "message": exc.message},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AIProviderUnavailableError)
    async def ai_provider_unavailable_handler(request: Request, exc: AIProviderUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "AI_PROVIDER_UNAVAILABLE", "message": exc.message},
        )

    @app.exception_handler(DuplicateKeyError)
    async def mongo_duplicate_key_handler(request: Request, exc: DuplicateKeyError) -> JSONResponse:
        """
        Catches MongoDB duplicate key errors — most critically the
        unique compound index (user_id, log_date) on habit_trackings.
        """
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "DUPLICATE_KEY",
                "message": "A record with this unique constraint already exists.",
                "detail": str(exc)[:200],
            },
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        """
        Overrides slowapi's default plain-text response with the same JSON error
        shape every other handler in this file uses, so frontend error parsing
        (getApiErrorMessage) works identically for a 429 as for any other error.
        """
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "RATE_LIMITED",
                "message": "Too many attempts. Please wait a moment and try again.",
            },
        )
