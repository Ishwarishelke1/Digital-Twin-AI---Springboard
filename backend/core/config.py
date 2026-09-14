"""
core/config.py — Type-safe environment variable loader for the FastAPI backend.
Mirrors the intent of backend/database/config/db_settings.ts, adapted for Python/Pydantic-Settings.
"""
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

_INSECURE_JWT_SECRET_PLACEHOLDER = "CHANGE-THIS-SECRET-IN-PRODUCTION"

# The common .env lives at the repo root (shared with the frontend — see
# frontend/vite.config.js's envDir), not inside backend/. Resolved from
# this file's own location rather than a bare relative ".env" so it's found
# correctly regardless of the CWD the server is launched from.
_ROOT_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── MongoDB Atlas ──────────────────────────────────────────────────────────
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "digital_twin_ai_prod"
    MONGODB_MAX_POOL_SIZE: int = 100
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_CONNECT_TIMEOUT_MS: int = 10_000
    MONGODB_SOCKET_TIMEOUT_MS: int = 45_000

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Digital Twin AI – FastAPI Backend"
    APP_VERSION: str = "1.0.0"
    NODE_ENV: str = "development"   # matches TS layer key name for shared .env

    # ── JWT / Security ────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = _INSECURE_JWT_SECRET_PLACEHOLDER
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # The `access_token` cookie's Secure flag — must be True behind real HTTPS.
    # Left unset (None) by default so it *follows* NODE_ENV rather than needing
    # to be remembered as a second, independent variable — see `cookie_secure`
    # below. A deploy that sets NODE_ENV=production is verified (Docker/Phase 0
    # of docs/TEST_PLAN.md) to hide /api/docs and engage require_non_production();
    # before this became a computed default, that same deploy shipped the auth
    # cookie with no Secure flag unless COOKIE_SECURE=true was *also* set by
    # hand — one flag doing its job while a second, easy-to-forget one silently
    # didn't. Still overridable explicitly (e.g. an internal non-HTTPS prod).
    COOKIE_SECURE: Optional[bool] = None

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def reject_insecure_default_jwt_secret(cls, v: str) -> str:
        """Fail startup loudly rather than silently signing tokens with the
        publicly-known placeholder if JWT_SECRET_KEY was never set via .env."""
        if v == _INSECURE_JWT_SECRET_PLACEHOLDER:
            raise ValueError(
                "JWT_SECRET_KEY is still set to its insecure placeholder value. "
                "Set a real secret via the JWT_SECRET_KEY environment variable (.env)."
            )
        return v

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
]
    # ── Pagination ────────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # ── AI Assistant (Milestone 4) ───────────────────────────────────────────
    # Gemini is the primary provider; Groq (an OpenAI-compatible API) is the
    # fallback if Gemini is unset or a call to it fails. Both optional so the
    # app still starts without them — ai_assistant_service raises a clean
    # AIProviderUnavailableError at call time instead if neither is configured.
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    @property
    def is_production(self) -> bool:
        return self.NODE_ENV == "production"

    @property
    def cookie_secure(self) -> bool:
        """Effective value for the auth cookie's Secure flag: the explicit
        COOKIE_SECURE override when set, otherwise whatever is_production says."""
        return self.COOKIE_SECURE if self.COOKIE_SECURE is not None else self.is_production


@lru_cache()
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance."""
    return Settings()
