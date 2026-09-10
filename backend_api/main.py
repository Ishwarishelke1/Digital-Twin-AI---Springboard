"""
main.py — FastAPI application entry point for Digital Twin AI.
Wires together: database lifecycle, CORS middleware, global exception handlers, and all v1 routers.
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware
from core.config import get_settings
from core.database import lifespan, ping_database
from core.exceptions import register_exception_handlers
from core.rate_limit import limiter
from api.v1 import (
    auth,
    users,
    finance,
    study,
    habits,
    activity,
    forecast,
    productivity,
    habit_analytics,
    trend_prediction,
    simulation,
    assistant,
    recommendations,
)

# ─── Logging Configuration ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

settings = get_settings()

# ─── Application Factory ──────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "FastAPI backend for Digital Twin AI — Personal Life Simulation & Decision Assistant. "
        "Connects to the production-ready MongoDB Atlas database (users, financial_records, "
        "study_activities, habit_trackings) via async Motor + Beanie ODM."
    ),
    # Hidden in production — the full API schema/interactive docs shouldn't be
    # publicly browsable outside development.
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None if settings.is_production else "/api/redoc",
    openapi_url=None if settings.is_production else "/api/openapi.json",
    lifespan=lifespan,                  # Async startup/shutdown (replaces @app.on_event)
)

# ─── Rate Limiting (scoped to auth endpoints — see api/v1/auth.py) ────────────
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Global Exception Handlers ─────────────────────────────────────────────────
# Includes the RateLimitExceeded handler for the limiter registered above.
register_exception_handlers(app)

# ─── API Routers ──────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(auth.router,    prefix=API_PREFIX)
app.include_router(users.router,   prefix=API_PREFIX)
app.include_router(finance.router, prefix=API_PREFIX)
app.include_router(study.router,   prefix=API_PREFIX)
app.include_router(habits.router,  prefix=API_PREFIX)
app.include_router(activity.router, prefix=API_PREFIX)
app.include_router(forecast.router, prefix=API_PREFIX)
app.include_router(productivity.router, prefix=API_PREFIX)
app.include_router(habit_analytics.router, prefix=API_PREFIX)
app.include_router(trend_prediction.router, prefix=API_PREFIX)
app.include_router(simulation.router, prefix=API_PREFIX)
app.include_router(assistant.router, prefix=API_PREFIX)
app.include_router(recommendations.router, prefix=API_PREFIX)

# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"], summary="Application health check")
async def health_check() -> dict:
    db_ok = await ping_database()
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.NODE_ENV,
        "database": "connected" if db_ok else "unreachable",
    }

# ─── Frontend (same-origin deploy) ────────────────────────────────────────────
# Deployment topology decision (see docs/TEST_PLAN.md Phase 0.1): frontend and
# API are served from ONE origin. This is what makes the httpOnly auth cookie
# work with SameSite=Lax in production — the same reason vite.config.js proxies
# /api to the backend in dev, so the browser never sees the request as
# cross-site. It also means CORS_ORIGINS and VITE_API_URL are dev-only concerns:
# a same-origin request needs neither.
#
# Conditional on the build existing so local `python -m uvicorn main:app --reload`
# (no frontend build present) keeps working exactly as it does today — this
# block is a no-op until `npm run build` has produced frontend/dist.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(request: Request, full_path: str):
        """SPA fallback: any path that isn't an API route, a static asset, or a
        favicon-style file resolves to index.html so React Router can take over
        client-side routing (e.g. a direct GET /finance from a fresh tab).

        Registered last and matches everything, so it must never shadow a real
        API route — FastAPI resolves routes in registration order, and every
        router above is already registered by the time this catch-all is added.
        A *mistyped* API path is the case this still has to get right: something
        under /api/ that matches no route above must stay a JSON 404, never fall
        through to index.html — silently returning HTML for a broken API call
        turns a loud error into a confusing one.
        """
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "not_found", "message": "Not found."})

        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
