# CLAUDE.md

Guidance for working in this repo. See `README.md` for the full project description and setup instructions — this file covers conventions and non-obvious behavior an agent (or a new contributor) needs to know before making changes. For UI/UX-specific work, see `docs/SKILLS.md`, which documents the design-review workflow (audit → visualize → plan → implement) this project's frontend changes go through.

For the forward-looking architecture roadmap — event sourcing, the ML models, the causal/simulation layers — see `docs/IMPLEMENTATION_PLAN.md`. **That file describes work that has not been done yet**, so read it as a plan, never as a description of how the system currently behaves; this file (`CLAUDE.md`) is the authority on current behavior. Where the two disagree, the code and `CLAUDE.md` win.

## Stack

- **Backend** (`backend_api/`): FastAPI + MongoDB Atlas via async Motor + Beanie ODM, JWT auth.
- **Frontend** (`frontend/`): React 19 + Vite + Tailwind CSS v4.

## Running things

```bash
# Backend
cd backend_api && pip install -r requirements.txt
python3 -m uvicorn main:app --reload          # http://127.0.0.1:8000, docs at /api/docs

# Backend tests (no live DB needed — see "Testing" below)
cd backend_api && python3 -m pytest tests/ -q

# Frontend
cd frontend && npm install && npm run dev     # http://localhost:5173
cd frontend && npx eslint . && npx vite build # lint + build check
```

`backend_api/.env` must exist with `MONGODB_URI`, `MONGODB_DB_NAME`, `JWT_SECRET_KEY` at minimum (app fails to start without a real `JWT_SECRET_KEY` — see `core/config.py`). There is currently **no separate test/staging database** — `MONGODB_URI` points at one live Atlas cluster, and `MONGODB_DB_NAME` is `digital_twin_ai_prod`. Be deliberate about what you write there (throwaway test accounts are fine; don't touch real user data).

- **Destructive scripts must call `require_non_production()`** from `core/db_guard.py` before touching the database. It refuses to run when `NODE_ENV=production` or the database name contains `prod`/`production`/`live`, and the override (`DESTRUCTIVE_WRITE_ALLOW_DB`) must name the exact database — a truthy value won't do, so a stale export can't satisfy it. `scripts/seed_zohaib.py` is wired up; wire up any new script that deletes or overwrites. This exists because that script opens by `delete_many()`-ing three collections against whatever `.env` points at, which today is production. See README's "Staging vs. production data" for the workflow.

## Backend conventions

- **Engines compose, they don't reimplement.** `forecast_service`, `productivity_service`, `habit_analytics_service` are the three base analytics engines, each reading directly from Mongo. Everything built on top (`trend_prediction_service`, `simulation_service`) composes their *public* async methods via `asyncio.gather` rather than re-querying the database or reaching into another engine's private helpers — even when it means duplicating a few lines of small pure-math logic (see `trend_prediction_service.py`'s docstring for the rationale). Follow this pattern for new analytics features.
- **Forecasting method tiers**: several engines auto-select a forecasting method based on how much history a user has — `insufficient_data` (0 points) → `naive_last_value` (1) → `moving_average` (2-3) → `linear_regression` (4+), each with its own confidence-score formula. This logic is intentionally duplicated per-engine (not shared) to keep engines decoupled; see `forecast_service.py`'s `_select_method`/`_compute_confidence` for the canonical version.
- **Errors**: raise domain exceptions from `core/exceptions.py` (`NotFoundError`, `ConflictError`, `BusinessRuleError`, `AuthenticationError`) — never a raw `HTTPException` — so every error response has the same `{"error": ..., "message": ...}` shape. They're registered as global handlers in `main.py`.
- **Raw Motor writes need explicit `Decimal128` conversion.** Beanie's ODM-level `.save()`/`.update()` calls handle `Decimal` ↔ `Decimal128` BSON encoding automatically; a raw `collection.update_one(...)` call does not. Forgetting this is a real, previously-hit bug (see `user_service.update_active_goal`).
- **Auth**: the JWT is set by the backend as an httpOnly cookie (not readable/stored by frontend JS — `frontend/src/services/api.js` sends it via `withCredentials: true`), carrying a `tv` (token_version) claim checked against `User.token_version` in `api/dependencies.py`. Logout and password-change bump the counter, invalidating every previously issued token at once (no per-device session concept). A token/user with no `tv`/`token_version` defaults to `0` for backward compatibility.
- **Rate limiting** (`core/rate_limit.py`, `slowapi`) is scoped only to `/auth/login`, `/auth/register`, `/users/me/change-password`, and `/assistant/chat` (LLM calls cost money/quota, same reasoning as the auth-route limits) — not applied app-wide.

## Frontend conventions

- **Service layer**: one file per backend resource in `src/services/`, all routed through the shared `api.js` axios instance (attaches the JWT, retries idempotent GETs on 5xx/network failure, redirects to `/login` on 401).
- **Errors**: use `getApiErrorMessage()` from `src/utils/apiError.js` in every form's catch block — it correctly unwraps both this backend's custom domain-exception shape (`{message}`) and FastAPI's built-in Pydantic validation-error shape (`{detail: [...]}`). Don't hand-roll `err.response?.data?.detail` — that only covers one of the two shapes.
- **Design system primitives** live in `src/components/ui/` (Button, Card, Modal, Drawer, Badge, Skeleton, EmptyState, Field, Pagination, StatTile) — reuse these rather than one-off markup.
- **Currency**: always render money through `formatCurrency(amount, currency)` (`src/utils/currency.js`), with `currency` sourced from `user.preferences.currency` — never hardcode a `$`.
- An `ErrorBoundary` wraps the whole app (`App.jsx`) — a render-time crash shows a recovery screen instead of a blank page.
- **Color/type/radius tokens** live in `src/index.css`'s `@theme` block (the "Studio" warm-paper design system — Fraunces display serif, Inter body, JetBrains Mono for every figure — overriding Tailwind's own gray/indigo/etc. scale rather than renaming classes app-wide). `src/utils/chartColors.js` mirrors the same colors as literal hex for Recharts/Plotly, which can't consume Tailwind classes or CSS variables — keep the two in sync by hand when either changes.
- **The color ramp is dual-purposed — check both directions before recoloring a rung.** Most `slate-*`/`indigo-*`/etc. steps aren't single-role: e.g. `slate-300` is both a light-mode border/fill value *and*, via `dark:text-slate-300` (used at dozens of call sites), a dark-mode text color that must independently clear 4.5:1 against the dark card. Recoloring a rung for one role without checking its other usages is a real, previously-made mistake in this repo — grep for the class name across `.jsx` files before assigning it a new hex, not just for the role you're targeting.
- **Sidebar/`MainLayout`** use an explicit `expanded`/`mobileOpen` state (lifted into `MainLayout.jsx`, persisted to `localStorage`), not CSS `:hover` — the rail must stay keyboard- and touch-operable, not just mouse-hover-operable.
- **`ui/Field.jsx`'s `Select`** is a custom-styled dropdown (not the native OS popup) with full Arrow/Home/End/Enter/Escape keyboard support — a drop-in replacement for `<select>` (same `name`/`value`/`onChange`/`<option>` children), so no call site needs native-`<select>`-specific handling.
- Any UI change should go through the workflow in `docs/SKILLS.md` before landing — audit findings first, then a plan, then the edit plus `npx eslint . && npx vite build`.

## Testing

Backend tests run with **zero live database connection**. `tests/conftest.py` calls `init_beanie()` once against a lazily-constructed, never-actually-connected Motor client — this only registers Beanie's class-level query metadata (needed for `Model.field == value` expressions used internally by some services); every test still mocks the actual I/O calls (`.find`/`.find_one`/`.insert`/`.get`/`.aggregate`/`get_motor_collection`) individually. Follow this pattern for new service tests — don't add a real DB dependency.

There is no frontend test suite yet.

## Known gaps (deliberately not fixed, see conversation history for context)

- `GET /simulation/{simulation_id}` exists on the backend but has no frontend caller.
- Several service-layer functions in the frontend (`forecastService.js`, `trendService.js`, etc.) are unused today but kept deliberately as documented "API-surface completeness" bindings — not dead code to prune.
