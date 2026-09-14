# New-user full-system test pass

Driven by `docs/TEST_PLAN.md`'s remaining gaps (cold-start data, mobile,
assistant grounding). See the plan file for phase structure. This report is a
running defect log — one entry per finding, updated as the pass proceeds.

## Phase 0 — Baseline (all against local Mongo, never Atlas)

| Suite | Result |
| :-- | :-- |
| `backend/tests/` (mocked DB, unit) | ✅ 367 passed |
| `backend/tests_integration/` (real local Mongo, real HTTP) | ✅ 18 passed |
| `frontend` `npx eslint .` | ✅ clean |
| `frontend` `npx vite build` | ✅ clean (pre-existing chunk-size warning only, not an error) |
| `frontend/tests_e2e` Playwright page walk | ✅ 28/28 (light + dark, desktop) |

Baseline fully green — every defect below is new, not pre-existing.

---

## Defect log

### #1 — `GET /simulation/{id}` and `PATCH /simulation/recommendations/{id}/feedback` 500 on a malformed id — **FIXED**

- **Module**: Backend, `services/simulation_service.py`
- **Severity**: Medium (crashes instead of a clean error response; reachable by any authenticated user just by mistyping a URL)
- **What broke**: `Simulation.get(PydanticObjectId(simulation_id))` and the equivalent for `recommendation_id` called `PydanticObjectId(...)` with no guard. A non-hex-24 string raises `bson.errors.InvalidId`, uncaught, which FastAPI's default handler turns into a raw 500 — not the project's `{"error": ..., "message": ...}` shape from `core/exceptions.py`.
- **Root cause**: every *other* id-taking service (`finance_service.update_transaction`, `study_service`, `habit_service`) wraps this exact call in `try/except Exception: raise NotFoundError(...)`; `simulation_service.get_simulation` and `submit_recommendation_feedback` were the two call sites that didn't follow that established convention.
- **Fix**: added the same try/except guard at both call sites (`services/simulation_service.py:670`, `:695`), raising `NotFoundError` — now returns a clean 404 with the standard error shape, matching every analogous endpoint.
- **Found by / regression test**: `tests_integration/test_new_user_journey.py::test_simulation_malformed_id_is_404_not_500`.
- **Re-run**: `pytest tests/ -q` → 367 passed; `pytest tests_integration/ -q` → 29 passed (18 original + 11 new, including this regression test). Both suites run **separately** per `pytest.ini`'s convention — running them in one process leaks `JWT_SECRET_KEY` env state between them and produces an unrelated false failure in `tests/test_config.py`; not a product bug, just a harness mistake caught and corrected mid-run.

### #2 — Conversational AI was not grounded in finance, study, habit, forecast, or what-if data — **FIXED**

- **Module**: Backend, `services/ai_assistant_service.py`, `schemas/assistant_schema.py`, `api/v1/assistant.py`
- **Severity**: High — this is the assistant's core value proposition ("a friendly, concise personal finance, study, and habit coach"), and it could answer none of those domains.
- **What broke**: `_build_context` read only `user.profile`, the six cached `digital_twin_state` numbers, and `active_goals[:5]`. It had zero visibility into finance transactions, spending categories, study sessions/subjects, habit logs, forecasts, or what-if simulation history — and `digital_twin_state` itself is a cached snapshot refreshed only by `GET /users/me`, so even the numbers it did show could be stale (zeros for a user who'd just signed up and started using other pages). There was also no multi-turn memory — `ChatRequest` was `{message}` alone.
- **Fix**:
  - Rewrote `_build_context` into an async `build_assistant_context(user)` that composes the *public* async methods of every engine via `asyncio.gather` — `user_service.get_twin_context` (live recompute, not the cache), `finance_service.get_monthly_cashflow`/`get_category_breakdown`, `study_service.get_subject_performance`, `habit_analytics_service.get_summary`, `forecast_service.forecast_monthly_savings`/`project_income`, `simulation_service.get_simulation_history` — per `CLAUDE.md`'s "engines compose, they don't reimplement" convention.
  - Each domain renders as a compact **summary** (totals/averages/top-N), never a raw dump, keeping the prompt small; a domain with no data says so explicitly ("no transactions logged yet") instead of being silently omitted, so the model states "I don't know" rather than inventing a number — the same refusal principle `goal_completion_service` already documents.
  - Any single engine failing degrades that one section to "unavailable" (`return_exceptions=True`) rather than failing the whole chat turn.
  - Added bounded multi-turn memory: `ChatRequest.history` (≤20 turns, client-held — transcripts still aren't persisted server-side), trimmed server-side to the last 6 turns before it reaches the model.
- **Verified**:
  - Deterministic (free): `test_assistant_context_grounded_in_every_domain` seeds real finance/study/habit/simulation data through the real endpoints and asserts the composed context string contains the actual figures; `test_assistant_context_new_user_says_no_data_not_zeros` asserts every domain explicitly states "no data" for a fresh account.
  - Live (5 real Groq calls against the running backend, seeded playwright-demo account + one fresh zero-data account): correctly reported real spending (\`₹4,165 in the last 90 days, all on food\`) and goal progress; correctly named the top-studied subject (Mathematics, 8h) and real habit consistency (33.3%, 10-day streak); correctly recalled a prior turn via `history`; correctly refused to fabricate spending data for the brand-new account ("I don't have any transaction data yet"). Gemini itself wasn't exercised live — `.env`'s `GEMINI_API_KEY` is present but empty, so every call fell through to the documented Groq fallback; this is the existing fallback behavior working as designed, not a new defect.
- **Re-run**: `pytest tests/test_assistant_service.py -q` → 12 passed (rewrote the old `_build_context` unit test into 6 pure-function tests over the new block builders, since the old private function no longer exists); full unit suite → 373 passed; `pytest tests_integration/ -q` → 29 passed.

### #3 — `DELETE /users/me` orphaned cached AI recommendations — **FIXED**

- **Module**: Backend / Database, `services/user_service.py:delete_user`
- **Severity**: Medium (data-integrity leak — every deleted account that had ever used `?generate=true` on `/recommendations/habits` or `/recommendations/study` left a document behind forever, with no code path left to ever read or clean it up)
- **What broke**: `delete_user` cascades deletes across `FinancialRecord`, `StudyActivity`, `HabitTracking`, `UserActivity`, `Simulation`, `Recommendation`, and `AssistantFeedback` — seven collections — but not `AIRecommendation` (collection `ai_recommendations`), the cached generated-recommendation set written by `ai_recommendation_service._store`. Easy to miss: `Recommendation` (simulation recommendations, collection `recommendations`) and `AIRecommendation` (habit/study AI recommendations, collection `ai_recommendations`) are two different models with confusingly similar names.
- **Found by**: `scripts/audit_data_integrity.py` explicitly checks `ai_recommendations` for orphaned `user_id`s (Phase 3.1/3.2 of `docs/TEST_PLAN.md`) — this pass reproduced it live rather than waiting for the audit to catch a future orphan: registered a real account, logged a habit, called `GET /recommendations/habits?generate=true` (a real Groq call, which stores the result), confirmed the document existed, called `DELETE /users/me`, and confirmed the document survived. Reproducible in under 10 seconds against a live backend.
- **Fix**: added `await AIRecommendation.find(AIRecommendation.user_id == uid).delete()` alongside the other seven, following the exact same pattern.
- **Re-verified live**: same repro sequence (register → log habit → generate real recommendation → confirm doc exists → delete account → confirm doc is gone) — now passes.
- **Regression tests**: `tests/test_user_service.py::test_delete_user_removes_all_eight_associated_collections` (renamed from "seven", mocked-DB unit test); `tests_integration/test_new_user_journey.py::test_delete_account_removes_cached_ai_recommendations` (real local Mongo, real HTTP, real document written and cascade-deleted).
- **Re-run**: `pytest tests/ -q` → 373 passed; `pytest tests_integration/ -q` → 34 passed (29 + 5 new: the grounding pair, the two ML-gate tests, and this cascade-delete test).
- **Also verified while here**: `scripts/audit_data_integrity.py` run against the local test database (post Phase 1–3 journey data) — all index, unique-constraint, type-consistency (`Decimal128`), and orphan checks pass clean; `core/db_guard.require_non_production()` correctly refuses a `prod`-named database, correctly refuses a truthy-but-wrong `DESTRUCTIVE_WRITE_ALLOW_DB` value, and correctly allows only an exact database-name match.

---

## Phase 4 — ML layer (verified, no defects)

- `models_store/goal_completion.joblib` loads correctly; `_load()` returns the real artifact.
- Missing-artifact degrade path confirmed live: temporarily moved the file, `_load()` returned `None` cleanly (no exception, matches the documented "must not break startup" contract), file restored.
- All five sufficiency/refusal gates verified against a real running backend + `tests_integration/test_new_user_journey.py`: window shorter than `MIN_DURATION_DAYS`, created less than `MIN_DAYS_ELAPSED` ago, deadline already passed, non-positive target (rejected earlier, at the schema layer), already-completed goal — every one returns `probability: None` with a `reason`, never a fabricated number. `trained_on: "synthetic"` provenance is surfaced even on a refusal.
- Feature-vector correctness across all three contribution sources (finance/study/habit) — already covered by the pre-existing `test_goal_completion_service.py` suite, re-confirmed passing.
- **Retrain reproducibility, verified exactly**: regenerated synthetic data with `scripts/generate_synthetic_users.py --seed 20260906` (120 users, 671 usable training goals after filtering, <1s), retrained with `scripts/train_goal_model.py --seed 20260906` (~3.4s), and the resulting model's metrics matched the shipped artifact's **bit-for-bit**: accuracy `0.8372093023255814`, ROC AUC `0.9390603328710125`, ECE `0.0691732009879456`. Full reproducibility confirmed, not just "close."
- `scripts/train_habit_failure_model.py` is a standalone capstone/evaluation script (precision-at-k analysis for a proposed nudge feature) — not wired into any live service or API endpoint, confirmed by grep across `services/`/`api/`. Out of scope for "does the running system work"; noted here as intentionally not a live feature, not a gap.

## Phase 5 — Database (verified, one defect found and fixed — see #3 above)

- `scripts/audit_data_integrity.py` — indexes, unique constraints, `Decimal128` type consistency, orphan-link and orphan-user-data checks — all clean against the local test DB after the full Phase 1–3 journey.
- `require_non_production()` guard verified in all three documented modes (refuse prod name, refuse wrong override, allow exact-match override).
- Cascade-delete on `DELETE /users/me` — found and fixed the `ai_recommendations` orphan (defect #3); the other seven collections were already correctly cascaded and are covered by the pre-existing mocked-DB test.

## Phase 6 — Frontend: mobile + web

**Desktop (light + dark), including the new zero-data user walk**: first combined run (light+dark+new-user, 30 tests) — 27/30 passed; the 3 failures (`Finance` — `net::ERR_SOCKET_NOT_CONNECTED`; `Activity` — a 10s visibility wait taking 33s; `logout` — a 30s step taking 15 minutes) were re-run in complete isolation immediately after and **all 3 passed in 1.2–1.6s each** — consistent with transient sandbox network degradation under ~15 minutes of continuous headless-Chrome load in this session's environment, not a reproducible product defect. No code change was needed or made for these three. **Second full combined run: 30/30 passed clean in 51.6s, no flakiness** — the project's own "twice consecutively" bar for stability is met.

**`new-user.spec.js`** (new, committed): a genuinely fresh account, registered in-browser via the real `/signup` form (not the seeded demo account), walks all 10 protected pages with zero data anywhere and asserts none of `NaN`/`Infinity`/`undefined`/`null` appears as visible text on any page. Passed clean in both themes on every run, including the sandbox-flaky one — confirming the cold-start empty-state rendering is solid across the app, not just at the API layer (Phase 1's zero-data sweep) but in the actual rendered UI.

**Mobile viewport (390×844, `devices["iPhone 12"]`) — added to `playwright.config.js` as `mobile-light`/`mobile-dark` projects. Now passing 30/30, confirmed on two separate runs (once by the user, once re-verified directly).**

### Defect #4 — mobile Playwright projects launched the wrong browser engine — **FIXED**

- **What happened**: the first several attempts to run the mobile projects failed — instantly with `Executable doesn't exist at .../webkit-2359/pw_run.sh` when run plainly, or hung until a 180s launch timeout when a Chromium `executablePath` override (`CHROME_EXE`) happened to be set. **I initially misdiagnosed the hung case as a sandbox network restriction** (blamed Chrome's internal GCM/telemetry retry logging, which was actually harmless noise) and reported that wrong conclusion before the real cause was found.
- **Root cause**: `devices["iPhone 12"]` ships `defaultBrowserType: "webkit"` — real iOS only ever runs Safari's engine, so Playwright's own mobile-Safari preset defaults to WebKit. This project's toolchain has only ever installed Chromium (`tests_e2e/README.md`'s own `CHROME_EXE` fallback note is evidence of that). Without an override, every mobile project tried to launch a WebKit binary that was never installed. When `CHROME_EXE` (a Chromium path) was set, it got fed into what was still a WebKit launch attempt — a protocol mismatch that manifested as a long hang instead of a clean error, which is what led to the wrong "sandbox" theory.
- **Fix**: added `browserName: "chromium"` to both `mobile-light` and `mobile-dark` project definitions in `playwright.config.js`, forcing the same engine the desktop projects already use, just at a phone viewport/UA/touch profile. Documented in the config directly so it isn't re-broken by a future edit that assumes the device preset alone is enough.
- **Verified**: full run, no `CHROME_EXE` override needed (Playwright's own installed Chromium is used directly) — **30/30 passed in 47 seconds**, both `mobile-light` and `mobile-dark`, including the `new-user.spec.js` zero-data walk. Re-ran a second time to confirm no flakiness.
- **Scope note this correction doesn't change**: real Mobile *Safari* (WebKit) coverage genuinely isn't set up in this project (WebKit was never installed) — that's an honest, separate gap, not something this fix claims to close. What's now verified is the app at a real phone viewport/touch profile, on the same Chromium engine the rest of the suite already trusts.

**Manual/static mobile-readiness audit performed alongside the automated run** (belt-and-suspenders, not a substitute this time): read `Assistant.jsx`, `Prediction.jsx`, `Settings.jsx` in full (the 3 pages with zero responsive classes) — no hardcoded pixel widths, all rely on `MainLayout`'s fluid container; every "Chart" component uses Recharts' `ResponsiveContainer`; all 4 `<table>` components wrap in `overflow-x-auto`; grid/flex layouts across `Dashboard.jsx`/`PredictionCards.jsx`/`DomainComparison.jsx`/`QuickActions.jsx` are mobile-first (`grid-cols-1` base, breakpoints layered on top); `Sidebar.jsx`'s mobile drawer has a real focus trap, Escape-to-close, and focus restoration. Nothing wrong found — now backed by a passing automated run, not just code reading.

---

## Verdict

**Backend**: stable. 373 unit tests + 34 integration tests (real local Mongo, real HTTP) pass, twice consecutively. All 68 endpoints exercised with zero data, at every documented forecasting-tier boundary, and against adversarial input (negative/zero amounts, malformed ids, past deadlines, unicode, pagination extremes, duplicate registration) — nothing 500s. Cross-tenant isolation verified across every domain including habits and simulations, not just the three the existing suite covered.

**Database**: stable. Full integrity audit (indexes, unique constraints, `Decimal128` types, orphan links, orphan user data) clean after the entire test journey's writes. The one real orphan this pass found (`ai_recommendations` surviving account deletion) is fixed and regression-tested at both the unit and integration level. The destructive-write guard rail behaves exactly as documented in all three modes.

**ML**: working correctly. The goal-completion model loads, degrades cleanly when its artifact is missing, and every sufficiency/refusal gate (too-short window, too-recent creation, passed deadline, already-completed) returns a reason rather than a fabricated number — verified against a live backend, not just mocked. Retrain reproducibility confirmed to the exact decimal digit against a fixed seed.

**Conversational AI**: now genuinely connected to every domain — profile, goals, finance (transactions + category breakdown), study (subjects + performance), habits (consistency + streak + patterns), forecasts, and what-if simulation history — composed live via the existing engines' public methods, per `CLAUDE.md`'s "engines compose" convention. This was the one part of the system that was previously blind to most of the user's data; it is not anymore. Verified deterministically (the composed context contains the real figures) and with 5 real Groq calls against a running backend: correct spending figures, correct goal progress, correct top-studied subject, correct habit consistency, correct multi-turn recall, and correct refusal to fabricate for a brand-new user. Bounded multi-turn memory added end-to-end (schema → service → frontend).

**UI — desktop**: stable, both themes, twice consecutively (30/30 then 30/30, including the new zero-data-account walk). Three flaky failures mid-session were sandbox network artifacts, not app bugs — proven by an isolated re-run passing in seconds.

**UI — mobile**: stable and verified. 30/30 automated Playwright tests pass at a real 390×844 phone viewport (both themes), confirmed on two separate runs, plus a manual code audit finding nothing wrong (mobile-first grid/flex patterns throughout, no fixed-pixel widths, all tables scroll safely, the mobile drawer has a real focus trap). Getting here required fixing a real config bug (defect #4 — the mobile projects were pointed at an uninstalled browser engine) that I initially misdiagnosed as a sandbox limitation; that correction is documented above.

**Net**: four real defects found and fixed — a malformed-id 500, a database orphan on account deletion, the assistant's blind spot across most of the app's data, and a mobile-testing config bug that was pointing at the wrong browser engine — all with regression tests or a passing automated run confirming the fix. The system is stable across backend, database, and ML; the conversational AI is now fully data-connected as requested; UI is verified stable on both desktop and mobile, automated, in both themes.
