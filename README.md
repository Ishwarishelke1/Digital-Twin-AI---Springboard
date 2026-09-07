# Digital Twin AI

A full-stack personal life dashboard that tracks finance, study, and daily habits, then layers analytics and forward-looking predictions on top of that data. Built with **FastAPI** + **MongoDB Atlas** on the backend and **React (Vite) + Tailwind CSS v4** on the frontend.

---

## Documentation

| File | Covers | Describes |
| :--- | :--- | :--- |
| `README.md` | Project overview, setup, features | Current state |
| `CLAUDE.md` | Code conventions and non-obvious behavior | Current state |
| `SKILLS.md` | The design-review workflow frontend changes go through | Current state |
| `REMEDIATION_PLAN.md` | Defects found by auditing the codebase, and how each was fixed | Current state |
| `IMPLEMENTATION_PLAN.md` | Architecture roadmap — event sourcing, memory, causal reasoning, simulation, decision engine | **Mostly planned, not built** |

`IMPLEMENTATION_PLAN.md` is a forward-looking plan derived from an engineering design review.
Two parts of it have since been built — the staging database (Phase 0.1) and the goal-completion
model (Model 2, all three steps). Everything else in it is unbuilt, and is marked as such. Treat
the code and the other documents as the authority on how the system behaves today.

---

## Repository Structure

```text
Digital-Twin-AI---Springboard/
├── backend_api/          FastAPI application (the live backend)
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
```

---

## Quick Start

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

`backend_api/core/config.py` resolves this file's path relative to its own location, and `frontend/vite.config.js` sets `envDir` to the repo root — so this works regardless of which directory you run either app from. There's no per-app `.env`/`.env.example` anymore; only `VITE_`-prefixed vars ever reach client-side code, so backend secrets stay server-only even though the file is shared.

### Staging vs. production data

`MONGODB_DB_NAME` selects the database. It currently defaults to `digital_twin_ai_prod`, so a
**missing** env var fails *toward* production rather than away from it — set it explicitly.

Scripts that delete or overwrite data (`scripts/seed_zohaib.py`, and any future backfill) call
`core/db_guard.py`'s `require_non_production()` before touching the database. It refuses to run
when `NODE_ENV=production` or when the database name contains `prod` / `production` / `live`:

```bash
# Blocked — refuses and explains why
python3 scripts/seed_zohaib.py

# Intended usage: point at a throwaway/staging database first
MONGODB_DB_NAME=digital_twin_ai_staging python3 scripts/seed_zohaib.py

# Deliberate production run — must name the database exactly, and prints a warning
DESTRUCTIVE_WRITE_ALLOW_DB=digital_twin_ai_prod python3 scripts/seed_zohaib.py
```

**Setting up staging** (one-time, and a prerequisite for the work in `IMPLEMENTATION_PLAN.md`):

1. Create a second database on the existing Atlas cluster — or better, a separate free-tier
   cluster, so a mistake cannot touch production at all.
2. Point `MONGODB_DB_NAME` (and `MONGODB_URI`, if a separate cluster) at it.
3. Seed it: `MONGODB_DB_NAME=digital_twin_ai_staging python3 scripts/seed_zohaib.py`
4. **Verify a restore actually works** before relying on it — an untested backup is not a backup.

Until step 4 is done, treat every migration as unrehearsed and irreversible.

### 1. Backend (FastAPI)

```bash
cd backend_api
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

---

## Features

- **Auth** — JWT issued as an **httpOnly cookie** (not readable by frontend JS), carrying a token-version claim so logout and password-change invalidate every previously issued token at once. Axios sends it via `withCredentials`, retries idempotent GETs on transient failures, and redirects to `/login` on 401 — except on public routes, which must stay reachable while logged out.
- **Finance** — income/expense/savings tracking, category breakdowns, and savings-goal progress.
- **Study** — session logging, weekly study-hours chart, subject performance breakdown.
- **Habits** — daily sleep/water/exercise/screen-time logging with weekly habit-score trend.
- **Analytics** — productivity score, focus score, consistency score, and completion-percentage engines that power the dashboards.
- **Prediction** — trend-based forecasts for savings, study, and fitness scores, and a scenario simulator. Forecasts auto-select a method from how much history exists (`insufficient_data` → `naive_last_value` → `moving_average` → `linear_regression`) and report which one was used.
- **Goal-completion model** — a trained classifier estimating the probability a goal is met by its deadline. See [Machine learning](#machine-learning) below.
- **Assistant** — grounded chat over the user's own profile, goals and twin state, using Gemini with a Groq fallback. Rate-limited, since LLM calls cost quota.
- **Activity** — a unified audit log of create/update/delete actions across the app.
- **Dark mode** — a manual toggle (stored in user preferences), applied consistently across the whole UI via a `data-theme` attribute.
- **Design system** — "Studio": a warm-paper visual identity (Fraunces display serif, Inter body, JetBrains Mono for every number) defined as design tokens in `frontend/src/index.css`, so it cascades to every page and component with no per-file styling. See `SKILLS.md` for the design-review workflow this was built through.

---

## Machine learning

A classifier estimating the probability that an active goal is completed by its `target_date`.

```bash
cd backend_api
python3 scripts/generate_synthetic_users.py   # training data
python3 scripts/train_goal_model.py           # train, evaluate, save artifact
```

Writes `data/model_eval/evaluation.png` (reliability diagram + coefficients),
`data/model_eval/metrics.json`, and `models_store/goal_completion.joblib`, which
`services/goal_completion_service.py` loads to serve `GET /users/me/goals/predictions`.
All three are gitignored and regenerate deterministically from the seed.

**Results** — logistic regression, held out by *user* rather than by row, since goals from one
person share that person's habits and a random row split leaks:

| | Accuracy | Lift over baseline | AUC | Brier | ECE |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Base rate | 52.1% | — | 0.500 | 0.254 | 0.066 |
| **Logistic regression** | **83.7%** | **+31.6pp** | **0.939** | **0.105** | **0.069** |
| Gradient boosting | 84.7% | +32.6pp | 0.918 | 0.128 | 0.109 |

Logistic regression ships despite the marginally lower accuracy: the output is shown to a user as
a probability, so calibration matters more than whether it lands on the right side of 0.5, and its
expected calibration error is substantially better (0.069 vs 0.109, against a target of < 0.10).

Numbers regenerate from the seed, so re-run both scripts if you change the generator — and
re-check this table, since it is written by hand.

Two deliberate constraints:

- **It refuses rather than guessing.** Goals with too little history, or whose inputs fall outside
  the range the model was trained on, return a reason instead of a number. A linear model
  extrapolates past its training range silently and confidently — it returned 99.8% for a real goal
  before this guard existed.
- **It is trained on synthetic data.** Good numbers here demonstrate the pipeline is correct — the
  model recovers signal that genuinely exists, is calibrated, and beats a baseline. They do **not**
  establish that it predicts real human behaviour. Only real longitudinal data can.

---

## Maintenance scripts

All live in `backend_api/scripts/` and are dry-run by default where they change data.

| Script | Purpose |
| :--- | :--- |
| `backup_restore_drill.py` | Dumps the database, restores it into a scratch copy, and compares per-collection counts. Atlas M0 has no automated backup, so this *is* the backup strategy — and an untested backup is not a backup. |
| `cleanup_test_accounts.py` | Removes accounts left by tests and QA. Deletion is opt-in by pattern, so an unrecognised address is always kept. `--orphans` finds records whose user no longer exists. |
| `fix_legacy_goal_ids.py` | Repairs `ObjectId` values in fields the models declare as `str` — Beanie cannot parse those documents at all, so the affected account 500s. |
| `backtest_forecast_accuracy.py` | Walk-forward accuracy check for the finance forecast. |
| `benchmark_simulation.py` | Latency check for the scenario simulator. |
| `seed_zohaib.py` | Rebuilds the demo account's data. **Destructive** — guarded. |

---

## Tech Stack

| Layer | Tools |
| :--- | :--- |
| Frontend | React 19, Vite, React Router 7, Tailwind CSS v4, Recharts, Axios, lucide-react, react-toastify (fonts: Fraunces / Inter / JetBrains Mono) |
| Backend | FastAPI, Motor + Beanie (async MongoDB ODM), Pydantic v2, python-jose (JWT), bcrypt (called directly — passlib 1.7.4 is incompatible with bcrypt ≥ 4.x, see `core/security.py`) |
| ML | scikit-learn, NumPy, pandas, Matplotlib |
| AI | Gemini (primary) with Groq fallback, via an OpenAI-compatible client |
| Database | MongoDB Atlas |
