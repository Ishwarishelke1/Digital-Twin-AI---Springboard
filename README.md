# Digital Twin AI

## Name
**Digital Twin AI** — a full-stack personal life dashboard that tracks finance, study, and daily habits, then layers analytics and forward-looking predictions on top of that data.

## Description
Digital Twin AI is built with **FastAPI + MongoDB Atlas** (via async Motor + Beanie ODM) on the backend and **React 19 (Vite) + Tailwind CSS v4** on the frontend. It consolidates a user's finances, study sessions, and daily habits into one place, then runs analytics engines (productivity, focus, consistency, completion-percentage scores) and forecasting models on top — including a trained classifier that estimates the probability of a goal being completed by its deadline, and a scenario simulator.

**Repository structure:**

```text
Digital-Twin-AI---Springboard/
├── backend/          FastAPI application (the live backend)
│   ├── api/v1/            REST endpoints: auth, users, finance, study,
│   │                       habits, habit-analytics, productivity, trends,
│   │                       forecast, activity
│   ├── core/               Settings, MongoDB (Motor/Beanie) connection, JWT
│   │                       security, exception handlers
│   ├── models/              Beanie ODM document models
│   ├── schemas/             Pydantic request/response schemas
│   ├── services/            Business logic, analytics aggregations, and the
│   │                         goal-completion model's serving path
│   ├── scripts/             Training, backup/restore drill, data repair, seeding
│   ├── tests/ + test_regression.py
│   └── main.py               App entry point
│
├── frontend/              React 19 + Vite single-page app
│   └── src/
│       ├── pages/           Dashboard, Finance, Study, Habits, Prediction,
│       │                     Assistant, Activity, Profile, Settings,
│       │                     Login/Signup/ForgotPassword
│       ├── components/      Feature components (charts, forms, tables)
│       ├── components/ui/   Shared design-system primitives (Button, Card,
│       │                     Modal, Drawer, Badge, Skeleton, ProgressList, ...)
│       ├── context/         Auth context / global state
│       ├── services/        Axios API clients (one per backend resource)
│       └── routes/          React Router route tree
│
└── docs/                  Capstone report, remediation log, design-review
                            workflow, architecture roadmap, legacy design system
```

**Documentation map:**

| File | Covers | Describes |
| :--- | :--- | :--- |
| `README.md` | Project overview, setup, features | Current state |
| `CLAUDE.md` | Code conventions and non-obvious behavior | Current state |
| [`docs/CAPSTONE_REPORT.md`](docs/CAPSTONE_REPORT.md) | The project written up end to end: architecture, both ML models, results, the defects found, limitations | Current state |
| [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) | A plan to test every module, route, page and collection, and the deployability verdict | **Phase 0 done, Phases 1–3 in progress** |
| [`docs/REMEDIATION_PLAN.md`](docs/REMEDIATION_PLAN.md) | Defects found by auditing the codebase, and how each was fixed | Current state |
| [`docs/SKILLS.md`](docs/SKILLS.md) | The design-review workflow frontend changes go through | Current state |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Architecture roadmap — event sourcing, memory, causal reasoning, simulation, decision engine | **Mostly planned, not built** |
| [`docs/DESIGN.md`](docs/DESIGN.md) | The "Field Notes" visual design system | **Superseded by "Studio"** |

Everything but `README.md` and `CLAUDE.md` lives in [`docs/`](docs/), which has its own [index](docs/README.md).

## Visuals
No screenshots or demo GIFs are checked into the repo yet. Run the app locally (see **Installation**) to see the "Studio" design system — a warm-paper visual identity (Fraunces display serif, Inter body, JetBrains Mono for every number) defined as design tokens in `frontend/src/index.css`.

## Installation

### Prerequisites
- Node.js 20+
- Python 3.10+
- A MongoDB Atlas cluster (or local MongoDB 7.0+)

### 0. Environment variables (shared)

Both apps read from a **single `.env` at the repo root** — copy the template and fill in real values:

```bash
cp .env.example .env
```

```env
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=digital_twin_ai_prod
JWT_SECRET_KEY=<a-securely-generated-secret>
VITE_API_URL=/api/v1
# Optional — AI assistant (Gemini primary, Groq fallback)
GEMINI_API_KEY=
GROQ_API_KEY=
```

`backend/core/config.py` resolves this file's path relative to its own location, and `frontend/vite.config.js` sets `envDir` to the repo root — so this works regardless of which directory you run either app from. Only `VITE_`-prefixed vars ever reach client-side code, so backend secrets stay server-only even though the file is shared.

### Staging vs. production data

`MONGODB_DB_NAME` selects the database. It currently defaults to `digital_twin_ai_prod`, so a **missing** env var fails *toward* production rather than away from it — set it explicitly.

Scripts that delete or overwrite data (`scripts/seed_zohaib.py`, and any future backfill) call `core/db_guard.py`'s `require_non_production()` before touching the database. It refuses to run when `NODE_ENV=production` or when the database name contains `prod` / `production` / `live`:

```bash
# Blocked — refuses and explains why
python3 scripts/seed_zohaib.py

# Intended usage: point at a throwaway/staging database first
MONGODB_DB_NAME=digital_twin_ai_staging python3 scripts/seed_zohaib.py

# Deliberate production run — must name the database exactly, and prints a warning
DESTRUCTIVE_WRITE_ALLOW_DB=digital_twin_ai_prod python3 scripts/seed_zohaib.py
```

**Setting up staging** (one-time, and a prerequisite for the work in `docs/IMPLEMENTATION_PLAN.md`):

1. Create a second database on the existing Atlas cluster — or better, a separate free-tier cluster, so a mistake cannot touch production at all.
2. Point `MONGODB_DB_NAME` (and `MONGODB_URI`, if a separate cluster) at it.
3. Seed it: `MONGODB_DB_NAME=digital_twin_ai_staging python3 scripts/seed_zohaib.py`
4. **Verify a restore actually works** before relying on it — an untested backup is not a backup.

Until step 4 is done, treat every migration as unrehearsed and irreversible.

### 1. Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
export PYTHONPATH=$(pwd)
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- API docs: `http://localhost:8000/api/docs`

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

- App: `http://localhost:5173`

### 3. Deployment (one image, one origin)

Frontend and API are deployed as **one origin**, not two services behind CORS — this is the deployment topology this project has settled on, and it's not incidental. The httpOnly auth cookie is `SameSite=Lax`; a Lax cookie is not sent on a cross-site request, so a frontend and backend on different domains (a Vercel frontend calling a Render backend, the common free-tier split) would silently 401 every authenticated call. `vite.config.js` already proxies `/api` to the backend in development for exactly this reason — same-origin deploy just extends that same shape to production. See `docs/TEST_PLAN.md` Phase 0.1 for the full reasoning, and Phase 0's checklist for what was verified rather than assumed.

```bash
docker build -t digital-twin-ai .
docker run -d -p 8000:8000 --env-file .env -e NODE_ENV=production digital-twin-ai
```

What the image does, in three stages (see `Dockerfile` for the full commentary):

1. **Builds the frontend** — no `VITE_API_URL` is set; the same-origin deploy means its relative `/api/v1` default (`frontend/src/services/api.js`) is already correct, so there's no build-time secret to pass in.
2. **Trains the goal-completion model** — `backend/models_store/` is gitignored on purpose (deterministic under `--seed`, so regenerated rather than committed, same convention as `backend/data/`). The build runs `generate_synthetic_users.py` then `train_goal_model.py` so the image always ships with a real, working model rather than depending on someone having a binary checked out locally.
3. **Assembles a slim runtime image** from both stages' outputs — no Node, pandas, or matplotlib in the final image, and `main.py` serves the built frontend directly (`StaticFiles` + an SPA fallback) whenever `frontend/dist` is present, so the same `main.py` runs unchanged in local dev (`--reload`, no build present) and in the container.

**No secrets are ever baked into the image** — `.dockerignore` excludes `.env` explicitly. `MONGODB_URI`, `JWT_SECRET_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `NODE_ENV=production` all reach the container via `--env-file` (or your platform's own env-var mechanism) at *run* time.

**`NODE_ENV=production` is the one variable that matters most** — it hides `/api/docs`/`/api/redoc`, engages `require_non_production()`'s guard on destructive scripts, and now also flips `COOKIE_SECURE` on by default, so the auth cookie ships with `Secure` without that needing to be remembered as a second, separate variable.

**Single instance, single worker, by design** (`Dockerfile`'s `CMD`) — the rate limiter (`core/rate_limit.py`) keeps its counters in-process, so more workers or more instances silently divides `/auth/login`'s protection by however many there are. Raise the worker/instance count only alongside moving the limiter to shared storage (Redis-backed slowapi storage, for instance) — not before.

### 3a. Running the whole stack locally with `docker-compose.yml`

The plain `docker build`/`docker run` above needs a real `MONGODB_URI` you supply yourself (normally the Atlas cluster in `.env`). `docker-compose.yml` is the alternative for local use — it brings up the app **and** a local MongoDB together, one command:

```bash
docker compose up --build
```

- App: `http://localhost:8000`
- MongoDB: `mongodb://localhost:27017` (also reachable directly, e.g. from Compass or `mongosh`, if you want to inspect what landed there)

**This never touches the real Atlas cluster.** `MONGODB_URI` is hardcoded in `docker-compose.yml` to the local `mongo` service, not read from `.env`, so it can't accidentally resolve to production even though compose auto-loads the same root `.env` for `JWT_SECRET_KEY`/`GEMINI_API_KEY`/`GROQ_API_KEY` (reusing your real values there is intentional — the assistant degrades cleanly to Groq or "no provider" if either key is blank). Data lands in a `digital_twin_ai_docker_local` database, in a named Docker volume that persists across `docker compose down`/`up` but not `docker compose down -v`.

## Usage

Once both the backend and frontend are running (see **Installation**), open `http://localhost:5173` (dev) or the container's port 8000 (deployed) and sign up for an account. From there:

- **Finance** — log income/expense/savings, see category breakdowns and savings-goal progress.
- **Study** — log study sessions, view the weekly study-hours chart and subject performance breakdown.
- **Habits** — log daily sleep/water/exercise/screen-time, see the weekly habit-score trend.
- **Prediction** — view trend-based forecasts for savings, study, and fitness scores, run the scenario simulator, and see goal-completion probability estimates.
- **Assistant** — chat with an AI assistant grounded in your own profile, goals, and twin state.
- **Activity** — review a unified audit log of create/update/delete actions across the app.

### Backend tests (no live DB needed)

```bash
cd backend && python3 -m pytest tests/ -q
```

### Integration tests (needs local MongoDB)

```bash
brew services start mongodb-community   # or: docker run -d -p 27017:27017 mongo:7
cd backend && python3 -m pytest tests_integration/ -q
```

### Frontend lint/build

```bash
cd frontend && npx eslint . && npx vite build
```

### End-to-end tests (Playwright)

See `frontend/tests_e2e/README.md` for exact run instructions — it needs a backend running against seeded local data and a Chromium install.

### Training the goal-completion model

```bash
cd backend
python3 scripts/generate_synthetic_users.py   # training data
python3 scripts/train_goal_model.py           # train, evaluate, save artifact
```

This writes `data/model_eval/evaluation.png` (reliability diagram + coefficients), `data/model_eval/metrics.json`, and `models_store/goal_completion.joblib`, which `services/goal_completion_service.py` loads to serve `GET /users/me/goals/predictions`. All three are gitignored and regenerate deterministically from the seed.

**Results** — logistic regression, held out by *user* rather than by row, since goals from one person share that person's habits and a random row split leaks:

| | Accuracy | Lift over baseline | AUC | Brier | ECE |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Base rate | 52.1% | — | 0.500 | 0.254 | 0.066 |
| **Logistic regression** | **83.7%** | **+31.6pp** | **0.939** | **0.105** | **0.069** |
| Gradient boosting | 84.7% | +32.6pp | 0.918 | 0.128 | 0.109 |

Logistic regression ships despite the marginally lower accuracy: the output is shown to a user as a probability, so calibration matters more than whether it lands on the right side of 0.5, and its expected calibration error is substantially better (0.069 vs 0.109, against a target of < 0.10).

Two deliberate constraints:

- **It refuses rather than guessing.** Goals with too little history, or whose inputs fall outside the range the model was trained on, return a reason instead of a number.
- **It is trained on synthetic data.** Good numbers here demonstrate the pipeline is correct, not that it predicts real human behaviour.

### Maintenance scripts

All live in `backend/scripts/` and are dry-run by default where they change data.

| Script | Purpose |
| :--- | :--- |
| `backup_restore_drill.py` | Dumps the database, restores it into a scratch copy, and compares per-collection counts. Atlas M0 has no automated backup, so this *is* the backup strategy. |
| `cleanup_test_accounts.py` | Removes accounts left by tests and QA. Deletion is opt-in by pattern; `--orphans` finds records whose user no longer exists. |
| `fix_legacy_goal_ids.py` | Repairs `ObjectId` values in fields the models declare as `str`. |
| `backtest_forecast_accuracy.py` | Walk-forward accuracy check for the finance forecast. |
| `benchmark_simulation.py` | Latency check for the scenario simulator. |
| `seed_zohaib.py` | Rebuilds the demo account's data. **Destructive** — guarded. |

## Features

- **Auth** — JWT issued as an **httpOnly cookie** (not readable by frontend JS), carrying a token-version claim so logout and password-change invalidate every previously issued token at once.
- **Finance** — income/expense/savings tracking, category breakdowns, savings-goal progress.
- **Study** — session logging, weekly study-hours chart, subject performance breakdown.
- **Habits** — daily sleep/water/exercise/screen-time logging with weekly habit-score trend.
- **Analytics** — productivity score, focus score, consistency score, and completion-percentage engines that power the dashboards.
- **Prediction** — trend-based forecasts for savings, study, and fitness scores, and a scenario simulator. Forecasts auto-select a method from how much history exists (`insufficient_data` → `naive_last_value` → `moving_average` → `linear_regression`) and report which one was used.
- **Goal-completion model** — a trained classifier estimating the probability a goal is met by its deadline.
- **Assistant** — grounded chat over the user's own profile, goals and twin state, using Gemini with a Groq fallback. Rate-limited, since LLM calls cost quota.
- **Activity** — a unified audit log of create/update/delete actions across the app.
- **Dark mode** — a manual toggle (stored in user preferences), applied consistently across the whole UI via a `data-theme` attribute.
- **Design system** — "Studio": a warm-paper visual identity (Fraunces display serif, Inter body, JetBrains Mono for every number) defined as design tokens in `frontend/src/index.css`.

## Tech Stack

| Layer | Tools |
| :--- | :--- |
| Frontend | React 19, Vite, React Router 7, Tailwind CSS v4, Recharts, Axios, lucide-react, react-toastify (fonts: Fraunces / Inter / JetBrains Mono) |
| Backend | FastAPI, Motor + Beanie (async MongoDB ODM), Pydantic v2, python-jose (JWT), bcrypt (called directly — passlib 1.7.4 is incompatible with bcrypt ≥ 4.x, see `core/security.py`) |
| ML | scikit-learn, NumPy, pandas, Matplotlib |
| AI | Gemini (primary) with Groq fallback, via an OpenAI-compatible client |
| Database | MongoDB Atlas |

## Support
For questions or issues, check `docs/CAPSTONE_REPORT.md` and `docs/TEST_PLAN.md` first — most non-obvious behavior and known gaps are documented there or in `CLAUDE.md`. Otherwise, open an issue against this repository.

## Roadmap
`docs/IMPLEMENTATION_PLAN.md` is the forward-looking architecture roadmap — event sourcing, memory, causal reasoning, a simulation layer, and a decision engine. Two parts of it have already been built ahead of the rest: the staging database (Phase 0.1) and the goal-completion model (Model 2, all three steps), plus a second model (habit failure) added beyond the original plan. Everything else in that document is still unbuilt and marked as such — treat the code and `CLAUDE.md` as the authority on current behavior, not the plan.

Known, deliberately-not-fixed gaps:
- `GET /simulation/{simulation_id}` exists on the backend but has no frontend caller.
- Several frontend service-layer functions (`forecastService.js`, `trendService.js`, etc.) are unused today but kept as documented "API-surface completeness" bindings, not dead code.

## Contributing
This is a capstone/student project. If you'd like to contribute:

1. Read `CLAUDE.md` for code conventions and non-obvious behavior, and `docs/SKILLS.md` for the UI/UX design-review workflow frontend changes go through.
2. Run the backend unit suite (`pytest tests/ -q`) and the frontend lint/build (`npx eslint . && npx vite build`) before opening a PR.
3. Never point destructive scripts at the production database — see **Staging vs. production data** above.
4. Open a merge request/pull request describing the change and why.

## Authors and acknowledgment
Built as part of a Springboard capstone project.

## License
No license has been specified for this project yet.

## Project status
Actively developed. Core features (finance, study, habits, analytics, forecasting, the goal-completion model, and the AI assistant) are built and working; the broader architecture roadmap in `docs/IMPLEMENTATION_PLAN.md` (event sourcing, causal reasoning, simulation) is still in planning. See `docs/TEST_PLAN.md` for current test-coverage status (Phase 0 complete, Phases 1–3 in progress).
