# REMEDIATION_PLAN.md

Fixes for defects that exist in the codebase **today**. Distinct from `IMPLEMENTATION_PLAN.md`,
which is a forward-looking architecture roadmap for capabilities that don't exist yet — this file
is about things that are currently broken, wrong, or missing.

Every finding below was verified against the code, not inferred from the design review. Line
references were checked at the time of writing.

---

## Findings summary

| # | Severity | Finding | Verified by | Status |
|---|---|---|---|---|
| 1 | **HIGH** | `/signup` and `/forgot-password` bounce to `/login` when opened directly | Reproduced in a headless browser | ✅ **Fixed** |
| 2 | **HIGH** | 20 color shades used in JSX are undefined in `@theme` → render in stock Tailwind | `comm` diff of used vs. defined tokens | ✅ **Fixed** |
| 3 | MEDIUM | Dark-mode contrast failure on accent text (~9 sites), 2.5–2.8:1 vs. 4.5:1 required | Computed WCAG ratios | ✅ **Fixed** |
| 4 | MEDIUM | `simulations` / `recommendations` collections have no indexes despite per-user queries | `models/simulation.py`, query sites | ✅ **Fixed** |
| 5 | MEDIUM | `confidence_score` is presented as confidence but is a data-volume heuristic | `simulation_service.py:392` | ✅ **Fixed** (relabelled) |
| 6 | MEDIUM | `burnout_risk_cluster` is declared, typed, and surfaced — but written by nothing | Documented in the code itself | ⏸ **Needs a decision** — see §6 |
| 7 | LOW | `ProtectedRoute` renders unstyled `<h2>Loading...</h2>` | `utils/ProtectedRoute.jsx` | ✅ **Fixed** |
| 8 | LOW | `goal_progress_service` (money-adjacent) and `activity_service` have no tests | Test-file sweep | ◐ **Partial** — `goal_progress_service` done, `activity_service` outstanding |

### What shipped

- **#1** — public-route allowlist in `services/api.js` plus a `skipAuthRedirect` opt-out used by
  `AuthContext`'s mount-time session probe. Verified in a browser: all three public routes load
  directly while logged out, and `/dashboard` still redirects.
- **#2** — 30 new shades added to `index.css`'s `@theme`, interpolated on the warm ramp and
  contrast-checked in both themes (including alpha-composited badge backgrounds). Guard script
  added at `frontend/scripts/check-color-tokens.sh` so an undefined shade fails loudly.
- **#3** — `dark:` overrides added at every unconditional accent-text site.
- **#4** — compound indexes on both collections, plus one for the `user_feedback` aggregation.
- **#5** — user-facing copy now reads "data sufficiency"; the `confidence_score` API field name is
  unchanged (it's the contract) and the internal scoring weight is untouched.
- **#7** — themed full-page loading state with `role="status"`.
- **#8** — `tests/test_goal_progress_service.py`, 5 tests, asserting the `Decimal128` conversion
  and positional-`$` atomicity specifically.

**Verification:** 253 backend tests pass (up from 248), eslint clean, build clean, token guard
clean, and browser-verified for #1, #2, #3.

**Clean — audited and found no issues:** backend auth (only `register`/`login` are unauthenticated,
correctly, and `tests/test_routes_auth_enforcement.py` sweeps the surface); no raw `HTTPException`
anywhere; no bare `except:`; rate limits present on all four cost/abuse-sensitive routes.

---

## 1 — HIGH · Signup and password reset are unreachable by direct navigation

### The bug

`AuthContext` calls `getUser()` on mount for **every** route (`context/AuthContext.jsx:31–44`).
When there is no session, that request 401s. The axios interceptor
(`services/api.js:45–51`) redirects to `/login` on any 401 unless the path already contains
`/login`.

Net effect: a logged-out visitor who opens `/signup` or `/forgot-password` **directly** — from a
shared link, a bookmark, or a page refresh — is bounced to `/login` before the page renders.

The only reason this isn't caught in normal use: clicking "Sign Up" from `/login` is a
client-side route change, so `AuthContext` never remounts, no 401 fires, and the page loads fine.

**Reproduced:** `page.goto('/signup')` in a headless browser lands on `/login` with two 401s in
the console.

**Impact:** the new-user acquisition path is broken for every entry point except one. Password
reset — which by definition is used by people who cannot log in — is unreachable.

### Fix

- [ ] `services/api.js` — do not redirect when already on a public/unauthenticated route.
      Replace the `/login`-only check with a public-route allowlist:
      `["/login", "/signup", "/forgot-password"]`.
- [ ] `context/AuthContext.jsx` — treat a 401 during `restoreSession()` as "logged out", which it
      already does correctly; the problem is purely the interceptor's global redirect. Consider
      marking the session-restore request so the interceptor can skip it entirely
      (e.g. a `config.__skipAuthRedirect` flag set by `getUser()` when called from mount).
- [ ] Prefer React Router navigation over `window.location.href` where possible — the current
      approach triggers a full page reload and discards React state.
- [ ] **Regression test:** direct navigation to each public route renders that route.
      This is exactly the kind of bug a browser-level smoke test catches and unit tests don't.

---

## 2 — HIGH · The Studio design system is only partially applied

### The bug

`index.css`'s `@theme` block defines these shades only:

- `slate`: 50, 100, 200, 300, 400, 500, 600, 700, 800, 900 ✅ complete
- `indigo`: **100, 600, 700 only**
- `violet`: 100, 300, 500, 600, 700
- `emerald` / `amber` / `red`: **100, 600, 700 only**

But the JSX uses **20 shades that are never defined**, so they fall through to **stock Tailwind
colors** — cool blue-purple indigo, cool red — which clash with the warm Studio palette:

```
amber-300  amber-500   emerald-50  emerald-300  emerald-400  emerald-500
indigo-50  indigo-200  indigo-300  indigo-400   indigo-500   indigo-800
indigo-900 indigo-950  red-200     red-300      red-400      red-500
red-900    red-950
```

**Highest-impact instances:**

| Site | Class | Consequence |
|---|---|---|
| `ui/Field.jsx:5` | `focus:border-indigo-500`, `focus:ring-indigo-500/20` | **Every input in the app** has a stock blue-purple focus ring instead of the teal accent |
| `ui/Field.jsx:147` | `focus-within:border-indigo-500` | Same, for every custom `Select` |
| `ui/Field.jsx:8` | `border-red-500` (`errorClasses`) | **Every form error state** uses stock Tailwind red, not Studio `#BE123C` |
| `ui/Button.jsx:2,4` | `focus-visible:ring-indigo-500`, `ring-red-500` | Primary and danger button focus rings |
| `ui/StatTile.jsx:4,5,6` | `border-t-emerald-500 / red-500 / amber-500` | KPI tile accent bars on Dashboard and Finance |
| `GoalTrendList.jsx:5` | `border-t-emerald-500 / red-500` | Goal status borders |

### Honest note

This is a gap in the Studio redesign work, not a pre-existing issue I merely found. The
verification sweep at the time checked for *stale hex values* and confirmed none remained — but it
never checked that every **class shade in use** is actually defined in `@theme`. The old
"Field Notes" palette had the same shade coverage, so the fall-through predates the redesign; the
redesign did not fix it and the sweep should have caught it.

### Fix

- [ ] Define every used shade in `index.css`'s `@theme`, interpolating within each family so the
      warm palette stays coherent (e.g. `indigo-500` sits between `indigo-100` and `indigo-600` on
      the teal ramp, not on Tailwind's blue ramp).
- [ ] **Contrast-verify each new value in both themes before committing** — several are used as
      text (`dark:text-indigo-400`, `dark:text-emerald-300`, `dark:text-red-300`) and must clear
      4.5:1 against the surface behind them.
- [ ] Respect the `CLAUDE.md` dual-purpose warning: check every usage of a shade (light border,
      dark text, fill) before assigning it a value.
- [ ] Mirror any new semantic values into `utils/chartColors.js` if charts use them.
- [ ] **Add a guard so this cannot recur:** a script that diffs color classes used in `.jsx`
      against tokens defined in `index.css` and fails on any undefined shade. Wire into the
      existing lint/build gate.

```bash
# the check that found this — make it permanent
grep -rhoE "(bg|text|border|border-t|ring|from|to|fill|stroke|divide)-(slate|indigo|violet|emerald|amber|red)-[0-9]{2,3}" \
  --include="*.jsx" src/ | sed -E 's/^[a-z-]+-//' | sort -u > /tmp/used.txt
grep -o -- "--color-[a-z]*-[0-9]*" src/index.css | sed 's/--color-//' | sort -u > /tmp/defined.txt
comm -23 /tmp/used.txt /tmp/defined.txt   # must be empty
```

---

## 3 — MEDIUM · Dark-mode contrast failure on accent text

### The bug

Roughly nine call sites render `text-indigo-600` or `text-violet-600` with **no `dark:` override**,
so the light-mode value is used on dark cards:

`ProfileCard.jsx` · `StudyTable.jsx` · `TransactionTable.jsx` · `HabitTable.jsx` ·
`Activity.jsx` (active sort icons) · `Dashboard.jsx:302` ("AI Recommendation" heading) ·
`IncomeProjectionCard.jsx:17,22` · `PredictionCards.jsx:24` · `ui/StatTile.jsx:24,27`
(`predicted` variant)

Measured contrast on the dark card (`#292524`):

| Value | Ratio | WCAG AA (4.5:1) |
|---|---|---|
| Studio accent `#0F766E` | 2.77:1 | ❌ |
| Studio plum `#8B4B8A` | 2.51:1 | ❌ |
| *(previous palette, for reference)* `#2F6F5E` | 2.56:1 | ❌ |

This predates the redesign — the old palette failed identically — so it is **not a regression**,
but it is a live accessibility defect. Visually confirmed in a browser screenshot: the plum
"✦ AI Recommendation" heading reads noticeably dimmer than surrounding text on the dark card.

### Fix

- [ ] Add `dark:` overrides at each site using the lighter family shades defined in fix #2
      (e.g. `text-indigo-600 dark:text-indigo-400`, `text-violet-600 dark:text-violet-300`).
- [ ] Verify each pairing computes ≥ 4.5:1 against `--color-slate-800` (`#292524`).
- [ ] Do fix #2 **first** — these `dark:` shades must exist before they can be used.

---

## 4 — MEDIUM · Missing indexes on `simulations` and `recommendations`

### The bug

`models/simulation.py` declares no `indexes` in either `Settings` class, but both collections are
queried per-user:

- `simulation_service.py:655` — `Simulation.find(query, sort=[("created_at", -1)]).limit(limit)`
- `feedback_service.py:57` — `Recommendation.find(Recommendation.user_feedback != None)`
- `user_service.py:364–365` — delete-by-`user_id` on both (account deletion)

Every one is a collection scan. Harmless at current data volume, degrades linearly, and account
deletion scanning the full collection is the worst case.

Compare `models/activity.py`, which correctly declares
`[("user_id", ASCENDING), ("timestamp", DESCENDING)]`.

### Fix

- [ ] `Simulation.Settings.indexes` → `[[("user_id", ASCENDING), ("created_at", DESCENDING)]]`
- [ ] `Recommendation.Settings.indexes` → `[[("user_id", ASCENDING), ("created_at", DESCENDING)]]`,
      plus an index supporting the `user_feedback` filter if that aggregation stays app-wide.
- [ ] Confirm Beanie creates these on `init_beanie` startup; verify with `explain()` on staging.

---

## 5 — MEDIUM · `confidence_score` is not confidence

### The bug

`simulation_service.py:392`:

```python
confidence = round(min(0.95, 0.2 + 0.15 * min(days_logged, 5)), 2)
```

This is a **data-volume proxy** — it rises with how many days the user logged and caps at 0.95. It
has never been validated against a realised outcome, and cannot be, because predictions aren't
persisted. It is surfaced to the UI as `confidence_score` and weighted into scenario scoring at
`CONFIDENCE_WEIGHT = 0.2`.

Presenting an unvalidated heuristic as "confidence" is the most misleading thing in the current
system: a user reallocating money or months of study time reasonably reads 0.95 as "95% sure".

### Fix

- [ ] **Rename in the API and UI to "data sufficiency"** — accurate, and the number is genuinely
      useful under that name.
- [ ] Keep the internal scoring weight as-is; only the label is wrong.
- [ ] Restore a real confidence figure only once predictions are persisted and calibration is
      measured (`IMPLEMENTATION_PLAN.md` Phase 3).
- [ ] Audit every other user-facing use of the word "confidence" for the same problem —
      `forecast_service._compute_confidence()` and `trend_prediction_service._compute_confidence()`
      are method-tier heuristics with the same issue.

---

## 6 — MEDIUM · `burnout_risk_cluster` is a dead field

### The bug

The field is fully wired and permanently empty:

- Declared on `User.digital_twin_state` (`models/user.py:75`) and `HabitTracking`
  (`models/habit.py:44`)
- Typed with a four-level `BurnoutRisk` enum
- Exposed in `schemas/user_schema.py:90` and `schemas/habit_schema.py:44`
- Returned by `api/v1/users.py:82`

…and written by nothing. The code says so itself: `api/v1/habits.py:93` — *"`HabitTracking.
burnout_risk_cluster` is written by nothing"* — and `services/user_service.py:148` — *"burnout_
risk_cluster is intentionally left untouched"*. It is always `UNKNOWN`.

Users see a burnout indicator that never changes.

### Decision — hidden, and the clustering model is **not** recommended

✅ **Done:** the badge in `DigitalTwinCard.jsx` now renders only when the value is not `UNKNOWN`.
Kept as a conditional rather than deleted, so it returns automatically if the field is ever
populated.

**On implementing it as clustering — recommendation reversed.** An earlier draft of
`IMPLEMENTATION_PLAN.md` called this the highest-value ML work, on the grounds that the slot exists,
every consumer is wired, and unsupervised learning needs no labels. All true, and all outweighed by
two problems:

1. **Cluster *what*?** Clustering *users* into risk tiers is impossible — there is ~1 real user plus
   seeded accounts; you cannot partition n≈2 into four bands. Clustering *time windows within one
   user* (weeks) is viable at n≈20–50, but then the output is inherently **relative** — "your
   harder weeks" — not absolute risk.
2. **`CRITICAL_BURNOUT` is a quasi-clinical claim.** The enum asserts absolute severity about
   someone's mental state, derived from sleep/screen/study logs, validated against no clinical
   instrument. The only statistically viable formulation (relative, within-user) is precisely the
   one that cannot support that language. Asserting "critical burnout" to a stressed user on an
   unvalidated k-means assignment is indefensible and potentially harmful.

Implementing clustering because the field is *named* `_cluster` would be inheriting the original
design decision rather than evaluating it.

**If revisited later**, reformulate rather than build as specified: cluster weekly windows within a
user, gate behind ≥ 8 weeks of logs, and rename the user-facing concept to something descriptive
("load pattern") that makes no claim the data can't support.

**Better ML target:** goal-completion probability — supervised, evaluable with real calibration
metrics, no clinical claim. See `IMPLEMENTATION_PLAN.md` → *Model 2*, including a correction: its
labels are **not** free as originally written, and step 1 (capturing `completed_at` and a status-
change event) is urgent because the label is only capturable going forward.

---

## 7 — LOW · Unstyled loading state

`utils/ProtectedRoute.jsx` renders a bare `<h2>Loading...</h2>` — no layout, no styling — on every
app load while the session is validated. It flashes unstyled content before the shell appears, and
it ignores the `Skeleton` primitives that already exist in `components/ui/Skeleton.jsx`.

- [ ] Replace with a themed full-page loading state using the existing skeleton components.

---

## 8 — LOW · Untested services

- `services/goal_progress_service.py` — **money-adjacent**: adjusts goal progress by a `Decimal`
  delta, and sits on the path that had a real `Decimal128` bug before (`CLAUDE.md` documents it).
- `services/activity_service.py` — audit-log writes.

- [ ] Add `tests/test_goal_progress_service.py` — priority, given the money path and the known
      `Decimal128` failure mode.
- [ ] Add `tests/test_activity_service.py`.
- [ ] Follow the existing zero-DB pattern in `tests/conftest.py` — mock I/O individually.

---

## Suggested order

Ordered by user impact per unit of effort, and by dependency.

| Step | Fix | Why here |
|---|---|---|
| 1 | **#1** signup redirect | Highest user impact, small contained change |
| 2 | **#2** undefined tokens | Blocks #3; affects every form and button in the app |
| 3 | **#3** dark-mode contrast | Depends on #2's new shades existing |
| 4 | **#5** confidence rename | Small, and it is actively misleading users now |
| 5 | **#4** indexes | Small, prevents future degradation |
| 6 | **#6** burnout field | Decide (a) or (b); (a) is a real project |
| 7 | **#7**, **#8** polish and tests | Low risk, do alongside |

---

## Verification for every step

- [ ] `cd backend_api && python3 -m pytest tests/ -q` — green
- [ ] `cd frontend && npx eslint . && npx vite build` — clean
- [ ] The token-diff guard from #2 returns empty
- [ ] Contrast recomputed for any changed color, in **both** themes
- [ ] For #1: direct navigation to `/login`, `/signup`, `/forgot-password` each render correctly
      while logged out, and protected routes still redirect
- [ ] Visual check of both themes on Login, Dashboard, Finance before calling any UI fix done —
      lint and build verify code correctness, not visual correctness
