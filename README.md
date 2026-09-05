# Digital Twin AI

A full-stack personal life dashboard that tracks finance, study, and daily habits, then layers analytics and forward-looking predictions on top of that data. Built with **FastAPI** + **MongoDB Atlas** on the backend and **React (Vite) + Tailwind CSS v4** on the frontend.

---

## Documentation

| File | Covers | Describes |
| :--- | :--- | :--- |
| `README.md` | Project overview, setup, features | Current state |
| `CLAUDE.md` | Code conventions and non-obvious behavior | Current state |
| `SKILLS.md` | The design-review workflow frontend changes go through | Current state |
| `IMPLEMENTATION_PLAN.md` | Architecture roadmap — event sourcing, ML models, causal reasoning, simulation, decision engine | **Planned, not built** |

`IMPLEMENTATION_PLAN.md` is a forward-looking plan derived from an engineering design review. Nothing in it has been implemented yet — treat the other three files and the code itself as the authority on how the system behaves today.

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
│   ├── services/            Business logic and analytics aggregations
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

- **Auth** — JWT bearer authentication with automatic token attachment and refresh-on-401 handling via Axios interceptors.
- **Finance** — income/expense/savings tracking, category breakdowns, and savings-goal progress.
- **Study** — session logging, weekly study-hours chart, subject performance breakdown.
- **Habits** — daily sleep/water/exercise/screen-time logging with weekly habit-score trend.
- **Analytics** — productivity score, focus score, consistency score, and completion-percentage engines that power the dashboards.
- **Prediction** — trend-based forecasts for savings, study, and fitness scores, goal-completion estimates, and an illustrative what-if simulator.
- **Assistant** — a canned-response preview of an in-app assistant (not yet backed by a real model).
- **Activity** — a unified audit log of create/update/delete actions across the app.
- **Dark mode** — a manual toggle (stored in user preferences), applied consistently across the whole UI via a `data-theme` attribute.
- **Design system** — "Studio": a warm-paper visual identity (Fraunces display serif, Inter body, JetBrains Mono for every number) defined as design tokens in `frontend/src/index.css`, so it cascades to every page and component with no per-file styling. See `SKILLS.md` for the design-review workflow this was built through.

---

## Tech Stack

| Layer | Tools |
| :--- | :--- |
| Frontend | React 19, Vite, React Router 7, Tailwind CSS v4, Recharts, Axios, lucide-react, react-toastify (fonts: Fraunces / Inter / JetBrains Mono) |
| Backend | FastAPI, Motor + Beanie (async MongoDB ODM), Pydantic v2, python-jose (JWT), passlib (bcrypt) |
| Database | MongoDB Atlas |
