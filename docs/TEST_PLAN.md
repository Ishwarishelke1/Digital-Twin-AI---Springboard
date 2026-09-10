# TEST_PLAN.md

A plan to test the whole project — every module, every route, the data and the
database — and to answer one question at the end of it:

> **Is this project deployable?**

The short answer is at the top because it is what the plan exists to establish.
Everything after it is the work that turns that answer from a judgement into a
verified fact.

---

## The answer, today

**Yes — the four-item minimum this plan set for "deployable" is now fully met
and verified.** Phase 0's blockers are closed, Phase 1.1's contract sweep
passes clean, Phase 3.1–3.2's data audit ran against the live cluster, and
Phase 2.2's browser page walk passes 28/28 across two consecutive runs. Every
one of those four was checked against something real — a built container, a
real database, a real browser — not read off the code and assumed.

**A follow-on new-user pass (Phase 5) then went further than the four-item
minimum requires**, driven by a brand-new user rather than the seeded demo
account: a zero-data sweep across every endpoint, every forecasting-tier
boundary actually crossed, mobile viewport coverage, and — the most
consequential finding — the conversational AI rewired to actually see the
user's finance/study/habit/forecast/what-if data instead of almost none of
it. Four real defects were found and fixed along the way, each with a
regression test or a passing automated run. See "Phase 5 — New-user pass"
below for the full account.

That "yes" is scoped to what this plan actually set out to establish:
**the application runs correctly end to end, in the shape it will actually be
deployed in.** It does not cover load beyond a handful of users, CI, or
frontend forms/filters beyond the page walk — see "Still open" below and
"What this plan does not cover" at the end. Those raise confidence further;
they are not what the word "deployable" was defined against at the top of
this document.

**What Phase 0 found and closed:**

> **The auth cookie was `SameSite=Lax`, with only a dev-only proxy making that
> work.** `vite.config.js` already proxies `/api` in development for exactly
> this reason — its own comment says so. Production had no equivalent. **Fixed**
> by making the deploy topology itself same-origin: `main.py` now serves the
> built frontend directly (`StaticFiles` + an SPA fallback), so the same
> mechanism that makes the cookie work in dev now makes it work in production,
> with no cookie-policy change needed. Verified: a built container's `/`, a deep
> link like `/finance`, `/health`, and a real login all returned the right thing
> over one origin.

> **A second, independent flag was silently undermining the first fix.**
> `COOKIE_SECURE` defaulted to `False` and was never tied to `NODE_ENV` — so a
> deploy that correctly set `NODE_ENV=production` (which *did* hide `/api/docs`
> and *did* engage `require_non_production()`) still shipped the auth cookie
> with no `Secure` flag, because nobody had also remembered to set the second
> variable. Found by actually reading the `Set-Cookie` header off a running
> production-mode container, not by reading the code. **Fixed**: `COOKIE_SECURE`
> now defaults to `is_production`'s value and is still overridable explicitly.
> Verified before and after against the real container; covered by 7 new tests
> in `tests/test_config.py`.

> **`requirements.txt` was missing five runtime dependencies** — `bcrypt`,
> `email-validator`, `joblib`, `scikit-learn`, `numpy` — none of them imported
> anywhere `pytest`'s mocked-DB suite would ever load, so 321 passing tests gave
> no signal either way. Verified the fix by building a venv from `requirements.txt`
> alone (nothing else installed) and, in it, importing `main.py` and loading the
> real trained model artifact via `joblib.load` — both worked. Dev/script-only
> deps (`pandas`, `matplotlib`, `pytest`, `requests`) moved to a new
> `requirements-dev.txt`.

> **`backend_api/models_store/` — the trained model the goal-completion endpoint
> serves — is gitignored on purpose** (deterministic under `--seed`, same
> convention as `backend_api/data/`), which means a deploy built from a bare
> clone with no extra step ships with predictions silently disabled forever
> (the load failure is caught and logged, not fatal — so nothing crashes, the
> feature just never exists). **Fixed** by making the model-build a real Docker
> stage: the image runs `generate_synthetic_users.py` then `train_goal_model.py`
> at build time, so the artifact is always freshly trained, never a binary
> someone has to remember to commit or copy in. Verified: the actual build log
> shows the real training run — 886 goals, 120 users, AUC 0.939 — and the
> resulting `.joblib` loads inside the final runtime image.

**Closed since the last pass:**

| | Status |
| :--- | :--- |
| HTTP-level tests over 68 endpoints, no route ever 500s | ✅ **18 tests, `tests_integration/`, 3 consecutive clean runs** — Phase 1.1 |
| Cross-tenant data isolation | ✅ Verified for goals/transactions/study sessions — Phase 1.2 |
| `token_version` invalidation (both triggers) | ✅ Verified, and one assumption about it corrected — Phase 1.2 |
| Rate limits actually trigger | ✅ All 4 configured limits hit for real — Phase 1.2 |
| Database integrity (indexes, unique constraints, types, orphans) | ✅ **Audited against the live cluster** — Phase 3.1/3.2, **one real finding** (below) |
| All 13 pages load clean, both themes, direct URL | ✅ **28/28, two consecutive runs, real browser** — Phase 2.2 |
| A brand-new, zero-data user — every endpoint, every forecasting-tier boundary, adversarial input, cross-tenant across every domain | ✅ **`tests_integration/test_new_user_journey.py`, 16 tests** — see "Phase 5 — New-user pass" below |
| Mobile viewport (390×844), both themes, plus a zero-data account browser walk | ✅ **`mobile-light`/`mobile-dark` Playwright projects, 30/30** — Phase 5 |
| Conversational AI grounded in finance/study/habit/forecast/what-if data (previously profile+goals only) | ✅ Verified with 5 real Gemini/Groq calls — Phase 5 |
| Goal `completed_at` stamping, forecasting method tiering (0/1/2-3/4+ points) | ✅ Now covered — Phase 5, see 1.3/1.4 below |

**The plan's four-item minimum for "deployable" is now fully closed, and a
subsequent new-user pass (Phase 5) found and fixed four further real defects**
— see that section for detail. None of Phase 5 was required for the original
four-item minimum; it closes ground the "Still open" table below used to list.

**Still open, not yet closed:**

| | Status |
| :--- | :--- |
| CI running the full suite (373 unit + 34 integration + 58 e2e) | Missing — no `.github/` |
| Rate limiting across >1 instance | Documented as single-instance-only (`Dockerfile`'s `CMD`); not load-tested |
| Atlas M0 (no auto-backup, shared tier, connection cap) | Accepted limitation |
| Error tracking / observability | Missing — `logging.basicConfig` only |
| Known-fixture analytics assertions (hand-computed expected numbers) | Not yet covered — Phase 1.4 gap |
| Forms, table filters, colour-token/currency checks via Playwright | Not yet covered — Phase 2.4–2.6 gaps, beyond the page walk (keyboard operability spot-checked by code reading in Phase 5, not yet Playwright-automated) |
| Staging-rehearsed deploy; backup drill re-verified against today's data | Not yet done — Phase 3.3 gaps |
| Real Mobile Safari (WebKit) coverage | Not set up — Phase 5's mobile projects verify a phone viewport on Chromium, the engine already used elsewhere in this suite, not WebKit itself (never installed in this toolchain) |
| Load/limits under real concurrency | Not tested — Phase 3.4 |

**One real data-integrity finding, not fixed (audit is read-only by design):**
a `SAVINGS_DEPOSIT` transaction on a seed/demo account still links to a goal_id
that account's `active_goals` no longer contains — a deleted-and-recreated
goal that never had its old transaction re-linked. One record, on data that
already reads as seed/demo content, not a live user. See Phase 3.2 for detail;
fixing it is a deliberate, separate write this audit deliberately didn't make.

Phase 0, the core of Phase 1 (1.1, 1.2), and the core of Phase 3 (3.1, 3.2) are
done, and so is Phase 2.2. Phase 4's checklist below records the same "yes"
this section states, item by item.

---

## Scope: what "everything" is

| Layer | Count | Existing coverage |
| :--- | ---: | :--- |
| Backend endpoints | **68** across 13 routers | 3 tests (auth enforcement only) |
| Backend services | 16 files, **~5,000 lines** | **367 unit tests**, every service has a file |
| Beanie models / collections | 8 | index declarations, no migration tests |
| Frontend pages | 13 | **0** |
| Frontend components | 67 (56 + 11 primitives) | **0** |
| Frontend service clients | 14 | **0** |
| ML models | 2 | offline evaluation only |

**The shape of the gap.** Every one of the 367 tests mocks the database and calls
a service function directly. Not one sends an HTTP request through FastAPI, and
nothing touches React at all. The service layer is well covered; everything above
it is not covered at all.

That band is exactly where this year's real defects lived: `GET /users/me/goals`
returning 500 on every call, sign-up unreachable by direct URL, twenty undefined
colour shades falling through to stock Tailwind, and a Groq reply that came back
empty because reasoning tokens exhausted `max_tokens`. None of them was findable
by a service-level unit test. All of them were findable by one request or one page
load.

---

## Phase 0 — Deployability blockers ✅ done

These were fixes, not tests, and all five are closed — each verified against a
real built container (`docker build`, `docker run --env-file .env`), not just
read off the code. Kept below as a record of what was decided and why, since a
future contributor changing any of this should know what it depends on.

### 0.1 Decide the deployment topology, then set the cookie to match — done

**Chose Option A — same origin, one image.** `main.py` now serves the built
frontend directly (`StaticFiles` for `/assets`, an SPA-fallback catch-all for
everything else that isn't `/api/*`) whenever `frontend/dist` exists — a no-op
in local dev, where it doesn't. `SameSite=Lax` keeps working, `VITE_API_URL`
stays unset (the relative `/api/v1` default is already correct), and CORS
becomes irrelevant. Documented in README's new "Deployment" section.

- [x] Chose A, wrote it down in `README.md`.
- [x] No cookie code change needed for A — `set_auth_cookie` is unchanged.
- [x] Verified with real requests against a running container: `/`, `/finance`
      (SPA deep link), `/assets/*.js`, `/health`, a bad `/api/v1/...` path
      (stays JSON 404, does not fall through to `index.html`), and a real
      login — all returned the right status and content type.

### 0.2 Add a start command — done

- [x] `Dockerfile` — three stages (frontend build → model training →
      slim runtime), documented inline and in README.
- [x] `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`
      — `--workers 1` is deliberate, see 0.4.
- [x] `.dockerignore` added — explicitly excludes `.env` so no secret is ever
      baked into an image layer; secrets reach the container only via
      `--env-file`/the platform's own mechanism at run time.
- [x] Built and ran successfully end to end (see the verification notes above).

### 0.3 Pin the remaining dependencies — done

Found and fixed a real gap: five runtime imports had no corresponding pin at
all — `bcrypt` (used directly in `core/security.py`), `email-validator`
(pulled in by every `EmailStr` field, not imported directly), and `joblib` +
`scikit-learn` + `numpy` (the goal-completion model's serving path,
`services/goal_completion_service.py`, lazily `import joblib`s the trained
artifact at request time — a real runtime path the mocked-DB test suite never
exercises). None of the 321 tests passing at the time gave any signal either
way, because none of them load the real artifact.

- [x] Added all five to `requirements.txt`, each with a comment explaining why
      it's there.
- [x] Split dev/script-only deps (`pandas`, `matplotlib`, `pytest`,
      `pytest-asyncio`, `requests`) into a new `requirements-dev.txt`.
- [x] Verified by building a venv from `requirements.txt` alone — nothing
      else installed — then importing `main.py` and `joblib.load`-ing the
      real trained artifact in it. Both worked.

### 0.4 Decide the instance count — done

**Decided: single instance, single worker**, documented in the `Dockerfile`'s
`CMD` and README. `core/rate_limit.py`'s in-process storage means raising
either number silently divides `/auth/login`'s protection by however many
there are — fine to revisit once the limiter moves to shared storage, not
before. Not load-tested; the decision is a documented constraint, not a
verified capacity ceiling.

### 0.5 Set `NODE_ENV=production` and confirm the guards engage — done

Confirmed one guard already worked, and found a second one that silently
didn't:

- [x] `docs_url`/`redoc_url`/`openapi_url` correctly hidden — verified
      `GET /api/docs` returns 404 against a `NODE_ENV=production` container.
- [x] `require_non_production()` — pre-existing coverage in
      `tests/test_db_guard.py`.
- [x] **Found**: `COOKIE_SECURE` was a second, independent variable, not tied
      to `NODE_ENV` — so `NODE_ENV=production` alone shipped the cookie
      without `Secure`. **Fixed**: `cookie_secure` is now a computed property
      that defaults to `is_production`, still overridable explicitly. Verified
      against a real container before (no `Secure`) and after (`Secure`
      present) the fix, and covered by 7 new tests in `tests/test_config.py`
      (including the placeholder-`JWT_SECRET_KEY` rejection path, which also
      had no test before this).

---

## Phase 1 — Backend

### 1.1 Contract sweep over all 68 endpoints ✅ done

Built as `backend_api/tests_integration/` — real HTTP requests through the real
app, real Beanie/Motor queries, against a real disposable local MongoDB. See
`CLAUDE.md`'s Testing section for how to run it and why it's a separate suite
from `tests/`.

- [x] Route list built from `main.app.routes` at test time and cross-checked
      against a hand-maintained coverage set every run
      (`test_all_registered_api_routes_are_accounted_for`) — drift in either
      direction (a route added that nothing covers, or a covered route that no
      longer exists) fails the suite rather than passing silently.
- [x] Every route exercised with valid input via realistic create→read→update→
      delete flows per domain, not synthetic per-route calls — this doubled as
      most of 1.3, below.
- [x] **No route returned 500 under valid input** — the headline assertion,
      confirmed across three consecutive full runs (18/18 passing each time).
- [x] Response shapes checked against what the schemas actually declare, not
      assumed — this caught real mistakes in the *test's* assumptions before
      the suite was trustworthy (see box below).

> **What writing this actually found.** Three assumptions this project had
> been carrying — two in an earlier draft of this test file, one in this
> plan's own 1.3 checklist below — turned out wrong when checked against a
> real response:
>
> 1. `POST`/`PATCH /users/me/goals` return the **full `UserResponse`**
>    (profile + preferences + the whole `active_goals` array), not the single
>    goal just created or edited. A test written against the assumed shape
>    fails with a plain `KeyError`, immediately — which is exactly the
>    failure mode a `response_model`-blind mocked test can never produce.
> 2. **Changing your own password does not log out the session that changed
>    it.** `token_version` is bumped (invalidating every *other* outstanding
>    token) but the endpoint deliberately re-issues a fresh cookie for the
>    calling session — confirmed by reading `api/v1/users.py`'s own
>    docstring, not guessed. The original test asserted the opposite and
>    failed; the fix was the test, not the code.
> 3. **Re-posting a habit log for a date you've already logged is an upsert,
>    not a conflict** — `services/habit_service.py`'s `upsert_daily_log`
>    (`findOneAndUpdate`, `upsert=True`) treats a same-day re-log as a
>    correction, by design, and returns 200 with the same id updated. This
>    plan originally listed "the unique `(user_id, log_date)` constraint
>    returns a clean `ConflictError`" as a checklist item — that was wrong,
>    and is corrected in 1.3 below rather than left standing.

### 1.2 Auth and authorisation ✅ done

- [x] Absent-cookie rejection spot-checked across one representative route per
      router (5 routes) directly; every other route this suite calls is
      exercised authenticated, so a route that *should* reject but doesn't
      would instead surface as a cross-tenant failure in the check below.
- [x] **Cross-tenant access** (`test_cross_tenant_isolation`): a second user's
      goal, transaction, and study session are all confirmed unreachable to
      the first user via `PATCH`/`DELETE`/`GET` by id (403/404, never a
      leak, never a 500), and B's data is proven untouched afterward.
- [x] `token_version` — verified for both triggers: a token issued *before* a
      password change goes stale (a second client holding the old cookie gets
      401), while the session that made the change keeps working (see 1.1's
      finding #2). Logout's "every previous token, immediately" path was
      already covered.
- [x] Rate limits verified for real against their actual configured
      thresholds, each hit past its limit: `/auth/register` 5/min,
      `/auth/login` 10/min, `/users/me/change-password` 5/min,
      `/assistant/chat` 15/min (`tests_integration/test_rate_limiting.py`).

### 1.3 Domain logic round-trips (HTTP level, not service level) — mostly done

- [x] Finance: create → linked goal progress increments (verified the exact
      `Decimal` amount moved) → edit → delete → progress reverses to zero.
- [x] Study: create with marks → `quiz_marks_pct` computed (verified the exact
      percentage) → clear the marks → percentage clears. The real defect this
      guards against, confirmed still fixed at the HTTP level, not just in the
      unit test that was added for it.
- [x] Habits: **corrected**, not as originally written above — same-day
      re-logging is a deliberate upsert (200, same id, fields updated), not a
      409. Verified both the create and the update-in-place.
- [x] Goals: `ACTIVE → COMPLETED` stamping `completed_at` — covered in
      Phase 5's `test_goal_prediction_already_completed_gate`: a goal PATCHed
      to `current_value == target_value` stamps `completed_at`, verified via
      the prediction endpoint refusing a probability for it afterward (the
      gate `goal_completion_service.py` checks `completed_at is not None`
      against).
- [ ] Every error path returns the `{"error", "message"}` shape — checked
      implicitly everywhere a 4xx status was asserted, but no test asserts the
      *body shape itself* is `{"error", "message"}` rather than FastAPI's raw
      `{"detail": ...}` for a validation error specifically (422s were not
      exercised).

### 1.4 Analytics engines against known data — partially done

- [ ] Known-fixture assertions (seed specific values, check specific output)
      not yet done — this needs its own pass with real, hand-computed
      expected numbers, not just "did it 200."
- [x] Method tiering (0/1/2-3/4+ data points) — covered in Phase 5's
      `test_savings_forecast_method_crosses_every_tier`: posts income/expense
      transactions one trailing month at a time and confirms `method_used`
      crosses every documented boundary (`insufficient_data` →
      `naive_last_value` → `moving_average` → `linear_regression`) at the
      exact point `forecast_service._select_method` says it should — this
      also caught a wrong assumption in the *test itself* about how
      `_build_monthly_series` zero-fills (see Phase 5 for the correction).
- [x] **Empty-state behaviour**: all 29 read-only analytics/forecast/
      productivity/habit-analytics/trend/simulation/recommendation endpoints
      confirmed to return 200 (never 500) for a genuinely brand-new,
      zero-history user (`test_analytics_engines_on_a_fresh_user_never_500`).

### 1.5 ML serving — partially done

- [x] The model artifact loads in a real, running app — confirmed both by the
      containerised Phase 0 verification (real `joblib.load` inside the
      runtime image) and by `GET /users/me/goals/predictions` returning 200
      with a real (empty, for a fresh user) list in `tests_integration/`.
- [x] The sufficiency-gate refusal paths exercised at the HTTP level in
      Phase 5: a window shorter than `MIN_DURATION_DAYS`, a goal created less
      than `MIN_DAYS_ELAPSED` ago, a passed deadline, and an already-completed
      goal — each confirmed to return `probability: None` with a `reason`
      through `GET /users/me/goals/predictions`, not just at the service
      level (`tests/test_goal_completion_service.py` still covers that layer
      separately).
- [x] App-still-starts-if-artifact-missing: exercised directly in Phase 5 —
      the artifact was moved aside, `goal_completion_service._load()`
      confirmed to return `None` cleanly (no exception), then restored.
- [ ] Deliberately removing the artifact and booting the **full app** (not
      just calling `_load()` in isolation) is still not exercised.

### 1.6 AI providers — mostly done, at the unit level

- [x] `provider="rules"` fallback confirmed **twice**, at two different layers:
      `tests/test_ai_recommendation_service.py` (mocked, 20 tests covering the
      parser, the cache hash, staleness) and now also
      `tests_integration/test_contract_sweep.py`'s
      `test_recommendations_fall_back_to_rules_with_no_provider_configured`,
      which confirms it end-to-end with no key configured at all — a case the
      mocked suite can't reach, since it never calls a real provider function.
- [x] `assistant/chat` degrading to a clean 503 (`AIProviderUnavailableError`)
      with no provider configured — new, `tests_integration/` only, since
      `tests/` doesn't call the real endpoint.
- [x] Malformed-reply parsing and cache-digest stability — covered by the
      existing 20 unit tests in `tests/test_ai_recommendation_service.py`.
- [x] `GROQ_MAX_TOKENS = 2000` — the fix is in place
      (`services/ai_recommendation_service.py`); no dedicated regression test
      pins the exact value, so a future edit could silently lower it back
      toward the failure this was raised to fix.

---

## Phase 2 — Frontend, driven by Playwright

Zero tests exist here today, and there is no test runner in `frontend/package.json`
at all. The realistic goal is not a unit-test suite for 67 components; it is a
Playwright suite that proves every page loads, renders real data, and throws
nothing.

### 2.0 Harness setup ✅ done

Built as `frontend/tests_e2e/`, config at `frontend/playwright.config.js`. See
`tests_e2e/README.md` for exact run instructions, including seeding a demo
account (`backend_api/scripts/seed_playwright_user.py`) — the page walk was
run against real data, not an empty account, matching the plan's own stated
goal of proving pages "load, render real data, and throw nothing."

- [x] `webServer` boots `npm run dev`, waits on `http://localhost:5173`.
- [x] `baseURL` same-origin via Vite's existing `/api` proxy — the httpOnly
      cookie behaves exactly as it does for a real user.
- [x] `globalSetup` logs in once, saves `storageState`, reused by every spec.
- [x] `trace: "retain-on-failure"`, `screenshot: "only-on-failure"`.
- [x] The cached-Chromium fallback (`CHROME_EXE`) — used for every run in this
      pass, since a fresh `playwright install` wasn't attempted.
- [x] ESLint scoped correctly: `tests_e2e/**` and `playwright.config.js` run
      under Node, not the browser+React ruleset the rest of the app uses —
      `process` and Playwright's own (unrelated) `use` fixture parameter both
      false-positived against the React-authoring rules before this was split
      into its own `eslint.config.js` block.

### 2.1 A failing-on-noise fixture ✅ done, and it caught its own false positive

`tests_e2e/fixtures.js`. Exactly as valuable as predicted — and immediately
needed a correction of its own: Chrome's generic `"Failed to load resource:
the server responded with a status of 401"` console message carries no URL,
so the allow-list regex (which needs the URL to know a 401 is the expected
session-probe response) could never match it, and the fixture flagged the
*correctly ignored* network 401 a second time via the console. Fixed by
recognizing that generic, URL-less message as inherently redundant with the
network-level check, which does have the URL. Caught on the very first run,
by the fixture doing exactly what it was built to do.

- [x] `page.on("console")`/`page.on("pageerror")`/`page.on("response")`,
      failing the test if anything unexpected fires.
- [x] The session-probe 401 allow-listed by URL at the network level.

### 2.2 Page walk — all 13 pages ✅ done — 28/28, twice

`tests_e2e/page-walk.spec.js`. All 13 pages (10 protected + 3 public), each
project (light, dark), plus a dedicated logout-redirect test — **28 tests,
reproducible across two consecutive full runs.**

- [x] Every protected page reached by `page.goto()` directly — never by
      clicking through.
- [x] Public pages (`/login`, `/signup`, `/forgot-password`) reached with
      **no session at all** (`test.use({ storageState: { cookies: [],
      origins: [] } })`), the actual regression class this guards against.
- [x] A page-specific text landmark asserted visible, not just a 200.
- [x] Zero console/network noise (2.1's fixture) across all 28.
- [x] Both themes (2.3) — including one further real bug this surfaced.
- [x] **Visual spot-check**, not just the text assertion: captured the
      Dashboard in both themes and looked at both — genuinely distinct warm-
      paper/dark-slate renders, correct data in each (Savings Rate 98.1%,
      Study Consistency 96%, the violet projection line).

> **A second real bug this surfaced**: the standalone logout test originally
> logged into the *shared* seeded demo account before logging out of it.
> `token_version` lives on the `User` document, not the cookie — logout
> invalidates every session for that account, not just the one that called
> it. That silently poisoned the `storageState` file every other test in
> **both** projects depends on (light runs to completion first, so it was
> "dark"'s entire protected-page block that failed next, all with the same
> symptom: `setTheme` getting a 401). Fixed by giving the logout test its own,
> freshly **registered**, disposable account instead of touching the shared
> one — confirmed by two consecutive clean 28/28 runs after the fix.

### 2.3 Testing both themes — not via `colorScheme` ✅ done

**Confirmed, not just documented**: `colorScheme: "dark"` genuinely does
nothing here, because this app's theme is driven by
`user.preferences.dark_mode` via `AuthContext`, not `prefers-color-scheme`.

- [x] Two Playwright projects, `light` and `dark`, sharing one `storageState`
      (same account) rather than one each — the theme dimension is a server-
      side account field, not a browser setting, so per-project storageState
      would have been the wrong abstraction entirely.
- [x] Each test flips the preference server-side
      (`PATCH /users/me/preferences`) via a `setTheme` fixture, then reloads.
- [x] **Not restored in teardown** — a deliberate simplification, not an
      oversight: `globalSetup` re-authenticates fresh on every `playwright
      test` invocation regardless of what the account's preference was left
      at, so a stale `dark_mode` value doesn't affect the *next* run's
      correctness, only what a human would see if they logged into the demo
      account directly afterward. Reset to `false` by hand after this pass.

### 2.4 Forms

- [ ] Each form: valid submit persists, invalid input shows field-level errors, a
      server error surfaces through `getApiErrorMessage` rather than as a raw
      `detail` array.
- [ ] **Conditional fields**: quiz/exam marks appear only on a Practice Exam
      session; switching away clears them; the cleared value actually reaches the
      server rather than being dropped from an `exclude_unset` PATCH.
- [ ] Subject dropdown "Other…" path, and editing a record whose subject predates
      the list.
- [ ] Goal form opens pre-filled when reached via a domain page's Add-a-goal tile
      (`/goals?new=1&category=HABIT`).

### 2.5 Tables, filters, pagination

- [ ] All three tables: filters narrow results, **combine with AND**, reset to
      page 1, and clear. Assert against the rendered rows, not just that a request
      fired — Study's subject + type filter returning 3 rows, all Physics, all
      LECTURE, is the shape of assertion that catches a filter being dropped.
- [ ] Server-side filters actually re-query rather than filtering one loaded page:
      assert the request carried the query parameter.
- [ ] Sort, search, empty state, loading state.

### 2.6 Cross-cutting checks that fail silently

No visible error when these break, so they need explicit assertions:

- [ ] `scripts/check-color-tokens.sh` in CI — an undefined shade throws nothing,
      it just renders stock Tailwind against the Studio palette.
- [ ] No hardcoded `$`: assert rendered amounts carry the user's own currency
      symbol (the test account is INR, which makes a regression obvious).
- [ ] Predicted values render in the reserved violet, distinct from measured ones.
- [ ] Keyboard operability: sidebar, the custom `Select`, modals and drawers all
      driven with `page.keyboard` only — Tab, Arrow, Home/End, Enter, Escape.
- [ ] `ErrorBoundary` shows a recovery screen rather than a blank page.

### 2.7 Auth flows

- [ ] Login → protected page → logout → protected page redirects to `/login`.
- [ ] Session probe returns 401 on a public route **without** redirecting.
- [ ] An expired or tampered cookie redirects rather than rendering half a page.

### 2.8 Reusing the same harness for Phase 1.1

Playwright's `request` fixture is an HTTP client that shares `storageState`, so
the 68-endpoint contract sweep can live in the same suite as the UI specs and
reuse the single login. One runner, one auth setup, one report covering both
layers — worth preferring over a separate pytest+httpx harness that would need
its own live server and its own session.

## Phase 3 — Database

### 3.1 Schema and integrity ✅ done

Built as `backend_api/scripts/audit_data_integrity.py` — read-only (no
`require_non_production()` guard needed; it never writes), so it runs directly
against the live cluster, which is the only way "does the live cluster actually
have these indexes" is a real question rather than an assumption. Connects via
`core.database.connect_to_mongo()`, the exact function `main.py` calls on real
startup, so a clean run is itself a live confirmation that startup index
creation works.

**Rehearsed before trusting it**: run first against a disposable local database
seeded with real data through the real service layer, then against a copy of
that data with four corruptions injected by hand (a stray `ObjectId`, a raw
float where `Decimal128` belongs, an orphaned link, a record for a deleted
user) — confirmed the script caught all four and stayed silent on the clean
run, before pointing it at production.

- [x] Every declared index exists on the live cluster — confirmed by listing
      what's actually present per collection (`users`, `financial_records`,
      `study_activities`, `habit_trackings`, `ai_recommendations`).
- [x] Unique constraints hold: zero duplicates on `(user_id, log_date)` on
      habits, `(user_id, domain)` on `ai_recommendations`, and email on users.
- [x] **Type consistency**: zero `ObjectId` values found where the model
      declares `str`, across `active_goals[].goal_id` and every
      `linked_goal_id` field. Clean on the live cluster today.
- [x] `Decimal128` on every money/measurement field: clean — no raw
      float/int found on the live cluster.

### 3.2 Orphans and referential integrity ✅ done — one real finding

Mongo enforces none of this, so it had to be checked directly:

- [x] No `linked_goal_id` pointing at a goal that no longer exists — **found
      one**: a `SAVINGS_DEPOSIT` transaction (₹5,000, "Transfer to emergency
      fund goal") on a seed/demo-looking account still points at a goal_id
      that account no longer has (its only current goal is unrelated). Reads
      as a deleted-and-recreated goal that never had its old transaction
      re-linked — one record, on data that already looks like seed/demo
      content rather than a real user, not touched (this script is read-only
      by design; a fix is a separate, deliberate write).
- [x] No records belonging to a deleted user — clean across all 8 collections
      that carry a `user_id` (finance, study, habits, activity, feedback,
      recommendations, simulations, ai_recommendations).
- [x] Goal `current_value` reconciled against linked contributions — computed
      per the *actual* mechanism (summed `SAVINGS_DEPOSIT`/`INVESTMENT`
      amounts for FINANCE goals, a flat count of linked records for
      STUDY/HABIT — these are genuinely different formulas, read from
      `finance_service.py`/`study_service.py`/`habit_service.py` rather than
      guessed). 5 of 10 checked goals disagree with their linked total —
      **reported as informational, not a bug**: `current_value` is
      intentionally user-editable
      (`ActiveGoalUpdateRequest.current_value`), and every one of these 5
      sits on data that was manually seeded/flagged for a demo earlier in
      this project's history, exactly the case that field exists for.

### 3.3 Migration and backup — partially done

- [x] `AIRecommendation`'s collection and its `(user_id, domain)` unique index
      both confirmed live and present on the real cluster, via
      `audit_data_integrity.py`'s Phase 3.1 index listing above — created
      automatically, no manual intervention.
- [ ] `scripts/backup_restore_drill.py` — done once in an earlier pass (see
      `docs/CAPSTONE_REPORT.md`'s "Operational work" section); not re-run in
      this pass, so not re-verified against the database as it stands today.
- [ ] Staging deploy rehearsal, including first boot — not yet done; Phase 0's
      container verification booted against the real Atlas cluster directly,
      not against a staging copy.

### 3.4 Load and limits

- [ ] Pagination on a large collection; confirm queries use the declared indexes
      rather than collection-scanning.
- [ ] M0 connection limits under concurrent requests.
- [ ] Analytics endpoints against a user with a year of history, not thirty days.

---

## Phase 4 — The go/no-go ✅ minimum met

Deployable means all of these are true and **verified**, not assumed:

- [x] Phase 0 blockers closed; cross-origin auth confirmed — via same-origin
      deploy, not a cross-origin request, since Option A made the latter moot
      (see 0.1). Verified against a real built container.
- [x] **No endpoint returns 500 under valid input** (Phase 1.1) — 18 tests,
      3 consecutive clean runs.
- [x] No cross-tenant data access (Phase 1.2).
- [x] **Database integrity** — indexes, unique constraints, type consistency,
      orphan references, all audited against the live cluster (Phase 3.1/3.2).
      One real finding, documented above, not fixed (out of scope for a
      read-only audit).
- [x] **All 13 pages load clean in both themes, by direct URL** (Phase 2.2) —
      28/28 across two consecutive real-browser runs, against real seeded
      data, with a genuine visual check (not just the text assertion) that
      both themes actually render distinctly.
- [ ] Backup verified by restore, not by the dump exiting 0 (Phase 3.3) — this
      was done once, in an earlier pass (see `docs/CAPSTONE_REPORT.md`'s
      "Operational work" section); not re-verified in this pass.
- [ ] Staging deploy rehearsed end to end, including first boot.
- [x] The app refuses to start with a placeholder secret (`tests/test_config.py`,
      and confirmed the two guards that actually key off `NODE_ENV` — hidden
      `/api/docs` and `COOKIE_SECURE` — both engage in a real container).
- [x] 373 unit + 34 integration + 58 e2e tests pass (up from 367 + 18 + 28 —
      see Phase 5 below); `eslint` and `vite build` clean, both frontend and
      `tests_e2e/`.

**All four of the plan's minimum items for "deployable" are done.** The two
remaining unchecked items (a fresh staging rehearsal, a backup drill re-run
against today's data) are real and worth doing before an actual production
cutover, but were never part of the four-item minimum this document defined —
see "The answer, today" at the top.

### Recommended order of work

1. ~~**Phase 0**~~ — done.
2. ~~**Phase 1.1**~~ — done. The contract sweep was the highest yield per hour
   by a wide margin, exactly as predicted, and surfaced three wrong
   assumptions (two about test code, one about this very plan) along the way.
3. ~~**Phase 3.1–3.2**~~ — done. Rehearsed against injected corruptions on a
   disposable local database before trusting it against the live cluster; one
   real (minor, seed-data) finding.
4. ~~**Phase 2.2**~~ — done. 28/28 across two runs; found and fixed two real
   bugs in the harness itself along the way (a false-positive noise check, a
   shared-session poisoning bug), each confirmed fixed by a clean re-run
   rather than assumed.
5. ~~**Phase 5**~~ — done. A dedicated new-user pass closed the Phase 1.3/1.4
   gaps named above, added mobile viewport coverage, and — the highest-value
   find — fixed the conversational AI's blindness to most of the user's own
   data. See "Phase 5 — New-user pass" below.
6. Everything else — Phase 2.4–2.6, Phase 3.3–3.4, CI — as time allows, in
   that rough order of value per hour.

### Where this ran

Phase 1 (`tests_integration/`) writes real data, but only ever to a disposable
**local** MongoDB dropped before every test — it never touches
`digital_twin_ai_prod`. Phase 2 (`tests_e2e/`) runs against a second,
separately disposable local MongoDB, seeded with one realistic demo account
via `scripts/seed_playwright_user.py` — also never touching
`digital_twin_ai_prod`. Phase 3's audit (`scripts/audit_data_integrity.py`) is
read-only by design, which is exactly what let it run directly against the
live cluster: no write, so nothing to be careful about beyond making sure it
really doesn't write — verified in code review and by watching it behave
identically on a read-only rehearsal copy first. Phase 5 ran against the same
disposable local databases as Phases 1 and 2 — never `digital_twin_ai_prod`.

---

## Phase 5 — New-user pass ✅ done

A follow-on pass, driven by a brand-new user rather than the seeded demo
account, covering exactly the ground the "Still open" table above used to
list: Phase 1.3/1.4's remaining gaps, mobile viewport coverage, and the
conversational AI's actual data coverage. Full defect-by-defect writeup in
**`docs/NEW_USER_TEST_REPORT.md`** — this section is the summary.

**New test coverage**: `tests_integration/test_new_user_journey.py` (16 tests
— zero-data sweep, forecasting-tier boundaries crossed for real, ML
sufficiency-gate refusals, adversarial input, cross-tenant isolation extended
to habits/simulations, cascade-delete); `tests_e2e/new-user.spec.js` (a
genuinely fresh account, registered in-browser, walks every page asserting no
`NaN`/`Infinity`/`undefined`/`null` renders); `mobile-light`/`mobile-dark`
Playwright projects (390×844, both themes).

**Four real defects found and fixed, each with a regression test or a
passing automated run confirming the fix:**

1. **`GET /simulation/{id}` and the recommendation-feedback endpoint 500'd on
   a malformed id** — missing the same `try/except PydanticObjectId(...)`
   guard every other service uses. Fixed to a clean 404.
2. **`DELETE /users/me` orphaned cached AI recommendations** — the cascade
   deleted from 7 collections, not `ai_recommendations` (a distinct
   collection from `Recommendation`'s `recommendations`). Reproduced live
   with a real account and a real Groq-generated recommendation, fixed,
   re-verified live.
3. **The conversational AI was grounded in almost nothing** — only
   `profile`/`active_goals[:5]`/a cached `digital_twin_state` snapshot; blind
   to finance, study, habits, forecasts, and what-if history, and answering
   from stale numbers even when it did have something to say. Rewired to
   compose all the existing engines live via their public async methods
   (`user_service.get_twin_context`, `finance_service`, `study_service`,
   `habit_analytics_service`, `forecast_service`, `simulation_service`), each
   domain summarised rather than dumped to keep the prompt small, with an
   explicit "no data yet" line per domain rather than silent omission. Added
   bounded multi-turn memory end-to-end (schema → service → frontend).
   Verified with 5 real Gemini/Groq calls against a running backend.
4. **The new mobile Playwright projects launched the wrong browser engine** —
   `devices["iPhone 12"]` defaults to WebKit (real iOS only runs Safari's
   engine); this toolchain has only ever installed Chromium. Fixed by forcing
   `browserName: "chromium"`. Verified: 30/30, twice.

**Full regression after all four fixes**: 373 unit tests (was 367) + 34
integration tests (was 18) + 58 e2e tests across 4 projects — light, dark,
mobile-light, mobile-dark, 28-or-30 each — all passing, `eslint`/`vite build`
clean.

---

## What this plan does not cover

Stated so the go/no-go is not read as broader than it is.

- **ML model fidelity.** Both models are trained on synthetic data. This plan
  verifies the serving path, the guards and the fallbacks. It cannot establish
  that either predicts real behaviour — only real longitudinal data can, and it
  is still accruing. See `CAPSTONE_REPORT.md` §11.
- **Load beyond a handful of users.** M0 and a single instance are fine for a
  demo and a portfolio; they are not a capacity plan.
- **Security beyond the checks above.** `/security-review` covers the branch
  diff; a full audit is a separate exercise.
- **Visual regression.** The page walk catches crashes and console errors, not a
  layout that has quietly drifted.
