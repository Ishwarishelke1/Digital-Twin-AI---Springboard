# CLAUDE.md

Guidance for working in this repo. See `README.md` for the full project description and setup instructions — this file covers conventions and non-obvious behavior an agent (or a new contributor) needs to know before making changes. For UI/UX-specific work, see `docs/SKILLS.md`, which documents the design-review workflow (audit → visualize → plan → implement) this project's frontend changes go through.

For the forward-looking architecture roadmap — event sourcing, the ML models, the causal/simulation layers — see `docs/IMPLEMENTATION_PLAN.md`. **That file describes work that has not been done yet**, so read it as a plan, never as a description of how the system currently behaves; this file (`CLAUDE.md`) is the authority on current behavior. Where the two disagree, the code and `CLAUDE.md` win.

## Stack

- **Backend** (`backend/`): FastAPI + MongoDB Atlas via async Motor + Beanie ODM, JWT auth.
- **Frontend** (`frontend/`): React 19 + Vite + Tailwind CSS v4.

## Running things

```bash
# Backend
cd backend && pip install -r requirements.txt
python3 -m uvicorn main:app --reload          # http://127.0.0.1:8000, docs at /api/docs

# Backend tests (no live DB needed — see "Testing" below)
cd backend && python3 -m pytest tests/ -q

# Frontend
cd frontend && npm install && npm run dev     # http://localhost:5173
cd frontend && npx eslint . && npx vite build # lint + build check
```

`backend/.env` must exist with `MONGODB_URI`, `MONGODB_DB_NAME`, `JWT_SECRET_KEY` at minimum (app fails to start without a real `JWT_SECRET_KEY` — see `core/config.py`). There is currently **no separate test/staging database** — `MONGODB_URI` points at one live Atlas cluster, and `MONGODB_DB_NAME` is `digital_twin_ai_prod`. Be deliberate about what you write there (throwaway test accounts are fine; don't touch real user data).

- **Destructive scripts must call `require_non_production()`** from `core/db_guard.py` before touching the database. It refuses to run when `NODE_ENV=production` or the database name contains `prod`/`production`/`live`, and the override (`DESTRUCTIVE_WRITE_ALLOW_DB`) must name the exact database — a truthy value won't do, so a stale export can't satisfy it. `scripts/seed_zohaib.py` is wired up; wire up any new script that deletes or overwrites. This exists because that script opens by `delete_many()`-ing three collections against whatever `.env` points at, which today is production. See README's "Staging vs. production data" for the workflow.

## Backend conventions

- **Engines compose, they don't reimplement.** `forecast_service`, `productivity_service`, `habit_analytics_service` are the three base analytics engines, each reading directly from Mongo. Everything built on top (`trend_prediction_service`, `simulation_service`) composes their *public* async methods via `asyncio.gather` rather than re-querying the database or reaching into another engine's private helpers — even when it means duplicating a few lines of small pure-math logic (see `trend_prediction_service.py`'s docstring for the rationale). Follow this pattern for new analytics features.
- **Forecasting method tiers**: several engines auto-select a forecasting method based on how much history a user has — `insufficient_data` (0 points) → `naive_last_value` (1) → `moving_average` (2-3) → `linear_regression` (4+), each with its own confidence-score formula. This logic is intentionally duplicated per-engine (not shared) to keep engines decoupled; see `forecast_service.py`'s `_select_method`/`_compute_confidence` for the canonical version.
- **Errors**: raise domain exceptions from `core/exceptions.py` (`NotFoundError`, `ConflictError`, `BusinessRuleError`, `AuthenticationError`) — never a raw `HTTPException` — so every error response has the same `{"error": ..., "message": ...}` shape. They're registered as global handlers in `main.py`.
- **Raw Motor writes need explicit `Decimal128` conversion.** Beanie's ODM-level `.save()`/`.update()` calls handle `Decimal` ↔ `Decimal128` BSON encoding automatically; a raw `collection.update_one(...)` call does not. Forgetting this is a real, previously-hit bug (see `user_service.update_active_goal`).
- **Auth**: the JWT is set by the backend as an httpOnly cookie (not readable/stored by frontend JS — `frontend/src/services/api.js` sends it via `withCredentials: true`), carrying a `tv` (token_version) claim checked against `User.token_version` in `api/dependencies.py`. Logout and password-change bump the counter, invalidating every previously issued token at once (no per-device session concept). A token/user with no `tv`/`token_version` defaults to `0` for backward compatibility.
- **Rate limiting** (`core/rate_limit.py`, `slowapi`) is scoped only to `/auth/login`, `/auth/register`, `/users/me/change-password`, and `/assistant/chat` (LLM calls cost money/quota, same reasoning as the auth-route limits) — not applied app-wide.
- **Simulation scoring is risk-tolerance-aware** (`services/simulation_service.py`). `Profile.risk_tolerance` (defaults to `MODERATE`) selects a row from `RISK_TOLERANCE_WEIGHTS` (outcome/goal-impact/confidence split) and `RISK_STRETCH_PENALTY` (a penalty on each scenario's outcome ratio, scaled by `_RawScenario.intensity` — how big an ask it is relative to the domain's max). `MODERATE` reproduces the pre-existing fixed weights exactly, so any code that doesn't pass `risk_tolerance` is unaffected. Re-weighting alone can't change which scenario wins here — every scenario set is built so `Stretch` strictly dominates `Current`/`Target` on both axes, so only the intensity penalty can flip the recommendation, and only when the marginal gain from `Target` to `Stretch` is already thin (diminishing returns) — a genuine, non-plateauing improvement still wins even for a `CONSERVATIVE` user. See the constants' own docstring for the reasoning and `tests/test_simulation_service.py`'s `test_score_scenarios_conservative_*` tests for the proof.
- **`PATCH /api/v1/habits/daily-log/{log_id}`** edits an existing habit log's fields without touching its `log_date` (the unique `(user_id, log_date)` index means changing the date here would collide with, or silently create, a different day's log — delete and re-log instead). See `schemas/habit_schema.py`'s `HabitUpdateRequest`.

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

**`tests_integration/` is a second, deliberately separate suite** — real HTTP requests through the real FastAPI app (via `httpx.AsyncClient` + `ASGITransport`, no live uvicorn process needed) against a real, disposable, **local-only** MongoDB (`mongodb://localhost:27017`, database `digital_twin_ai_contract_sweep_test` — never the Atlas cluster in `.env`, and dropped before every test function so tests can't see each other's data). This exists because the mocked-DB unit suite structurally cannot catch a broken query, a wrong response shape, or a real cross-tenant data leak — see `docs/TEST_PLAN.md`'s Phase 1 for what it's proving and why. `pytest.ini`'s `testpaths = tests` keeps a bare `pytest` from picking this up by accident (it needs a reachable local Mongo and takes ~30s, vs. ~16s for the whole unit suite):

```bash
brew services start mongodb-community   # or: docker run -d -p 27017:27017 mongo:7
cd backend && python3 -m pytest tests_integration/ -q
```

Follow this pattern for anything that needs to exercise real routing/response-shape/cross-tenant behaviour rather than a single service function — not by adding a real DB dependency to `tests/`.

**`frontend/tests_e2e/` is a Playwright suite** — a real browser against the real
built app, real seeded data, both themes. Covers what neither backend suite can:
a page that renders while silently throwing in the console looks identical to a
clean one at every other layer. See `frontend/tests_e2e/README.md` for exact run
instructions (it needs a backend running against a seeded local database, and
`npx playwright install` or the cached-Chromium `CHROME_EXE` override — a plain
`npm run dev`/`pip install` does not pull this in). `playwright.config.js` and
`tests_e2e/**` run under Node, not the browser+React ESLint config the rest of
`frontend/` uses — see `eslint.config.js`'s second block for why (Playwright's
own `use` fixture parameter false-positives against `eslint-plugin-react-hooks`'
naming heuristic otherwise). Dark mode here is not `prefers-color-scheme` —
Playwright's `colorScheme` emulation does nothing; see `tests_e2e/fixtures.js`'s
`setTheme` for how theme testing actually works in this app.

## Known gaps (deliberately not fixed, see conversation history for context)

- `GET /simulation/{simulation_id}` exists on the backend but has no frontend caller.
- Several service-layer functions in the frontend (`forecastService.js`, `trendService.js`, etc.) are unused today but kept deliberately as documented "API-surface completeness" bindings — not dead code to prune.
