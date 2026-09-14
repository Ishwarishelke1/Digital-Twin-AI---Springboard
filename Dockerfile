# Dockerfile — one image, one origin.
#
# Three stages: build the frontend, train the goal-completion model, then
# assemble a slim runtime image from the outputs of both. The runtime stage
# never installs Node, pandas, or matplotlib — those only exist in the build
# stages and are discarded with them.
#
# See docs/TEST_PLAN.md Phase 0.1 for why this is one image rather than two
# services behind CORS: FastAPI serves the built frontend itself (main.py's
# "Frontend (same-origin deploy)" block), so the browser never sees the API
# call as cross-site and the httpOnly cookie's SameSite=Lax just works — the
# same reason vite.config.js proxies /api in development.


# ─── Stage 1: frontend build ───────────────────────────────────────────────
# No VITE_API_URL is set here, deliberately — the same-origin deploy means the
# frontend's relative "/api/v1" default (src/services/api.js) is already
# correct, so there is no build-time secret or config to pass in.
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# ─── Stage 2: train the goal-completion model ──────────────────────────────
# backend/models_store/ is gitignored on purpose (see .gitignore's comment:
# "deterministic under --seed, so regenerate rather than commit"), matching how
# backend/data/ is already treated. Both generator and trainer default to a
# fixed --seed, so this reproduces the same artifact on every build rather than
# depending on a binary someone remembered to commit.
#
# Both scripts are fully standalone (no import from the app's own models/
# services/schemas) — confirmed by reading them — so only scripts/ needs to be
# present here, not the rest of the backend.
FROM python:3.11-slim AS model-build
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/scripts/generate_synthetic_users.py backend/scripts/train_goal_model.py ./scripts/
RUN python scripts/generate_synthetic_users.py --out data/synthetic \
 && python scripts/train_goal_model.py --data data/synthetic/goals.csv --out data/model_eval
# → produces models_store/goal_completion.joblib


# ─── Stage 3: runtime ───────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runs as a non-root user — nothing in this app needs root, and a container
# breakout is a meaningfully worse outcome if the process inside it wasn't
# already running as one.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code. Scripts, tests, and generated data are deliberately NOT copied —
# none of them are needed to run the server, and every one of them is either a
# dev-only tool or (for data/models_store) already produced fresh by Stage 2.
COPY backend/api/ ./api/
COPY backend/core/ ./core/
COPY backend/models/ ./models/
COPY backend/schemas/ ./schemas/
COPY backend/services/ ./services/
COPY backend/main.py ./

# The trained artifact from Stage 2, and the built frontend from Stage 1 —
# placed at frontend/dist relative to the repo root, exactly matching
# main.py's `Path(__file__).resolve().parent.parent / "frontend" / "dist"`
# (backend/main.py's parent.parent), so no path override is needed.
COPY --from=model-build /app/backend/models_store/ ./models_store/
COPY --from=frontend-build /app/frontend/dist/ ../frontend/dist/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# No secrets are baked into this image (see .dockerignore) — MONGODB_URI,
# JWT_SECRET_KEY, GEMINI_API_KEY, GROQ_API_KEY, and NODE_ENV=production reach
# the container only via the platform's own env-var mechanism at deploy time.
#
# --workers 1: see docs/TEST_PLAN.md Phase 0.4 — the rate limiter's storage is
# in-process, so more than one worker (or more than one instance) silently
# divides each limit by however many there are. Raise this only alongside
# moving the limiter to shared storage, not before.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
