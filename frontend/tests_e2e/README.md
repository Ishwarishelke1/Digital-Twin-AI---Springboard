# tests_e2e/ — Playwright, docs/TEST_PLAN.md Phase 2

Drives the app through a real browser. This is the layer neither the backend's
`tests/` (mocked DB) nor `tests_integration/` (real HTTP, no browser) can
cover — a page that renders while silently throwing in the console looks
identical to a clean one at every other layer.

## Before running

Two things have to already be running — Playwright's `webServer` only starts
the Vite dev server, not the backend or a database:

```bash
# 1. A backend, pointed at a database with real data in it (never digital_twin_ai_prod
#    for a repeated local test run — see Phase 3's own reasoning for why this
#    project keeps write-heavy test runs off the real cluster):
cd backend_api
python3 -c "from pymongo import MongoClient; MongoClient('mongodb://localhost:27017').drop_database('digital_twin_ai_playwright_test')"
MONGODB_URI="mongodb://localhost:27017" MONGODB_DB_NAME="digital_twin_ai_playwright_test" \
  JWT_SECRET_KEY="playwright-local-secret" python3 -m scripts.seed_playwright_user

MONGODB_URI="mongodb://localhost:27017" MONGODB_DB_NAME="digital_twin_ai_playwright_test" \
  JWT_SECRET_KEY="playwright-local-secret" NODE_ENV="development" \
  python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 &

# 2. Playwright itself, from frontend/:
cd frontend
npx playwright test
```

**If `npx playwright install` can't reach the download**, point at a Chromium
build already on disk instead of installing a new one:

```bash
export CHROME_EXE="$HOME/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
npx playwright test
```

## Why dark mode isn't `colorScheme`

This app's theme is not `prefers-color-scheme` — `AuthContext` writes
`document.documentElement.dataset.theme` from the account's own
`preferences.dark_mode`, and `index.css` matches against that attribute via
`@custom-variant dark`. Playwright's `colorScheme: "dark"` project option does
nothing here. `fixtures.js`'s `setTheme` fixture flips the preference for real,
server-side (`PATCH /users/me/preferences`), then reloads — see its docstring.

## What's here

- `global-setup.js` — logs in once (the seeded demo account), saves the
  resulting cookie as `storageState`, reused by every spec so a 13-page,
  2-theme run doesn't trip `/auth/login`'s rate limit.
- `fixtures.js` — the noise-detection `page` fixture (fails a test on any
  console error, uncaught exception, or 4xx/5xx from `/api/`) and `setTheme`.
- `page-walk.spec.js` — Phase 2.2: all 13 pages, direct URL, both themes.

## What isn't here yet

Forms, table filters, and the cross-cutting checks (color tokens, currency
formatting, keyboard operability) from docs/TEST_PLAN.md's Phase 2.3–2.7 —
the page walk is the Phase 4 minimum; the rest raises confidence beyond it.
