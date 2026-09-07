# IMPLEMENTATION_PLAN.md

Implementation plan derived from the Digital Twin engineering design document. Covers every
change required to move this codebase from a deterministic life-tracking scorecard to a
probabilistic, causal, decision-support system — including the ML models, the external-data
strategy, and the reinforcement-learning decision.

**Design document:** https://claude.ai/code/artifact/45409286-8650-4cde-ac56-23a2241949ce

**How to use this file:** phases are strictly ordered — each depends on the one before. Within a
phase, tasks are ordered but many are parallelisable. Every phase ends with a verification gate
that must pass before the next phase starts. Nothing here is a suggestion to be skipped silently;
if a phase is deferred, record why.

**Conventions this plan inherits** (see `CLAUDE.md`): engines compose rather than reimplement;
domain exceptions from `core/exceptions.py`, never raw `HTTPException`; raw Motor writes need
explicit `Decimal128` conversion; backend tests run with zero live DB connection; frontend
changes go through the `SKILLS.md` workflow and end with `npx eslint . && npx vite build`.

---

## Table of contents

- [Phase 0 — Foundations](#phase-0--foundations)
- [Phase 1 — Twin MVP + first ML model](#phase-1--twin-mvp--first-ml-model)
- [Phase 2 — Memory & conversational interface](#phase-2--memory--conversational-interface)
- [Phase 3 — Prediction engine + supervised ML](#phase-3--prediction-engine--supervised-ml)
- [Phase 4 — Causal DAG & probabilistic simulation](#phase-4--causal-dag--probabilistic-simulation)
- [Phase 5 — Decision & optimization](#phase-5--decision--optimization)
- [Phase 6 — Experiments & contextual bandits](#phase-6--experiments--contextual-bandits)
- [Phase 7 — External integrations](#phase-7--external-integrations)
- [Phase 8 — Learned personalization](#phase-8--learned-personalization)
- [ML model specifications](#ml-model-specifications)
- [External dataset strategy](#external-dataset-strategy)
- [Dependencies to add](#dependencies-to-add)
- [What NOT to build](#what-not-to-build)

---

## Phase 0 — Foundations

No user-visible change. Everything later depends on this.

### 0.1 — Staging database (BLOCKER, do first)

**This blocks every other task in this file.** `CLAUDE.md` records that `MONGODB_URI` points at
one live Atlas cluster with no test/staging separation. Phase 0 dual-writes and backfills touch
production data with no rehearsal and no tested restore path.

- [ ] Provision a second Atlas cluster (free tier is sufficient) as `digital_twin_ai_staging`.
- [ ] Add `MONGODB_DB_NAME` switching via env; confirm `core/config.py` resolves it correctly.
- [ ] Verify point-in-time recovery / snapshot restore actually works — perform one restore drill.
- [ ] Document both connection strings and the restore procedure in `README.md`.
- [ ] Update `CLAUDE.md` to remove the "no separate test/staging database" warning once true.

### 0.2 — Event log

New append-only collection. The spine of the whole system.

- [ ] `models/event.py` — new `Event` Document:
  - `user_id: PydanticObjectId`
  - `seq: int` — per-user monotonic sequence
  - `event_type: str` — e.g. `FINANCE_TRANSACTION_CREATED`
  - `payload: dict`
  - `occurred_at: datetime` — **valid time** (when it happened in the world)
  - `recorded_at: datetime` — **transaction time** (when the system learned it)
  - `source: str` — `MANUAL | CHAT | INTEGRATION_<name> | BACKFILL`
  - `provenance: str` — `OBSERVED | DERIVED | INFERRED | PREDICTED | ASSUMED | DECLARED`
  - `idempotency_key: str` — unique index with `user_id`
  - `schema_version: int`
  - Indexes: `[(user_id, seq)]`, `[(user_id, occurred_at)]`, `[(user_id, event_type, occurred_at)]`,
    unique `[(user_id, idempotency_key)]`
- [ ] Register `Event` in `core/database.py`'s `document_models=[...]` list.
- [ ] `services/event_service.py` — `append_event()`, `get_events(user_id, since, until, types)`,
      `next_seq(user_id)`. Sequence allocation must be atomic (`find_one_and_update` with `$inc`
      on a per-user counter document).
- [ ] **Dual-write**: every existing mutation in `finance_service`, `study_service`,
      `habit_service`, `user_service` (goals) appends an event alongside its current document
      write. Existing read paths are untouched — documents remain the read model.
- [ ] Backfill script `scripts/backfill_events.py` — synthesise events from existing
      `FinancialRecord`, `StudyActivity`, `HabitTracking`, and `UserActivity` documents with
      `source=BACKFILL`, `recorded_at=now`, `occurred_at` from the record's own date field.
      **Must be idempotent and must run against staging first.**

> **Why dual-write and not full event sourcing:** rewriting every read path is a large, risky
> migration on a system whose reads already work. Documents stay as the read model (zero API
> churn); the log is added alongside.

### 0.3 — Twin state snapshots

- [ ] `models/twin_snapshot.py` — `TwinSnapshot` Document: `user_id`, `as_of: date`,
      `state: dict`, `event_seq_high_water: int`, `created_at`. Index `[(user_id, as_of)]`.
- [ ] Register in `core/database.py`.
- [ ] `services/twin_state_service.py`:
  - `build_snapshot(user_id, as_of)` — fold events up to `as_of` into a state dict.
  - `reconstruct_state(user_id, as_of)` — nearest snapshot ≤ `as_of`, then replay delta events.
  - `current_state(user_id)` — reconstruct at now; this eventually replaces direct reads of
    `User.digital_twin_state`.
- [ ] `scripts/build_snapshots.py` — nightly job. Retention: daily for 90 days, then weekly,
      then monthly.

### 0.4 — Epistemic tagging

- [ ] `models/enums.py` — add `EpistemicStatus` enum: `OBSERVED`, `DERIVED`, `INFERRED`,
      `PREDICTED`, `ASSUMED`, `DECLARED`.
- [ ] `models/user.py` — extend `DigitalTwinState` so each metric carries status + `as_of`.
      Introduce a `TaggedValue` submodel (`value`, `status`, `as_of`, `confidence: Optional`).
      **Backward compatibility:** untagged legacy values default to `DERIVED` (matching the
      `token_version` / `GoalStatus` default pattern already used in this codebase).
- [ ] `schemas/user_schema.py` — surface status in API responses.
- [ ] `services/ai_assistant_service.py` — `_build_context()` must render the tag, not flatten it.
      Today `predicted_exam_score` (a projection) and `savings_rate_pct` (arithmetic) appear in
      the same sentence with identical framing; the model cannot distinguish them.

### 0.5 — Verification gate

- [ ] `pytest tests/ -q` green.
- [ ] New tests: event append idempotency, sequence monotonicity, snapshot reconstruction
      correctness (reconstruct at T equals state computed live at T), bitemporal query
      (backdated entry lands in the right valid-time bucket).
- [ ] Backfill executed on staging, row counts reconciled against source collections.

---

## Phase 1 — Twin MVP + first ML model

First user-visible value.

### 1.1 — User-declared parameters (highest value / lowest cost in the whole plan)

Removes the "same twin for every user" defect without any ML.

- [ ] `models/user.py` — new `TwinParameters` subdocument on `User`:
  - `target_sleep_hours: Decimal = 8.0`
  - `sleep_healthy_range: tuple[Decimal, Decimal] = (7.0, 9.0)`
  - `target_exercise_minutes: Decimal = 30.0`
  - `target_water_liters: Decimal = 2.0`
  - `screen_time_max_hours: Decimal = 6.0`
  - `study_session_benchmark_hours: Decimal = 2.0`
  - `productivity_weights: dict = {attendance .30, focus .25, performance .25, hours .20}`
    (validated to sum to 1.0)
  - `parameter_source: EpistemicStatus = ASSUMED` → becomes `DECLARED` on user edit
- [ ] **Replace the hardcoded constants with lookups** at these exact sites:
  - `services/habit_analytics_service.py` — `SLEEP_HEALTHY_RANGE`, `EXERCISE_TARGET_MINUTES`,
    `WATER_TARGET_LITERS`, `SCREEN_TIME_HEALTHY_MAX` (lines ~63–66)
  - `services/productivity_service.py` — `PRODUCTIVITY_WEIGHTS`, `STUDY_HOURS_BENCHMARK` (~57–58)
  - `services/simulation_service.py` — `EXERCISE_TARGET_MINUTES`, `SLEEP_HEALTHY_RANGE`,
    `WATER_TARGET_LITERS`, `SCREEN_TIME_HEALTHY_MAX`, `WEEKLY_STUDY_HOURS_BENCHMARK` (~61–70)
  - Keep the module constants as **defaults** — they become the fallback when the user has not
    declared a value. No behaviour change for existing users.
- [ ] `api/v1/users.py` — `GET`/`PATCH /users/me/twin-parameters`.
- [ ] Frontend: settings section for these values (goes through the `SKILLS.md` workflow).
- [ ] Tests: scores change when parameters change; defaults reproduce today's exact numbers.

### 1.2 — Burnout risk clustering (ML model #1)

See [full spec](#model-1--burnout-risk-clustering). The field already exists and is written by
nothing — `api/v1/habits.py:93` documents this, and `services/user_service.py:148` notes it is
"intentionally left untouched."

- [ ] `services/ml/burnout_clustering.py`
- [ ] `scripts/train_burnout_model.py`
- [ ] Wire into `services/user_service.py`'s twin-state refresh to populate
      `digital_twin_state.burnout_risk_cluster`.
- [ ] `api/v1/habit_analytics.py` — expose cluster + contributing factors.
- [ ] Frontend: surface on the Habits page. Must state it is `INFERRED`, not a diagnosis.

### 1.3 — Data-sufficiency surfacing

- [ ] Every analytics response already carries a method tier (`insufficient_data`,
      `naive_last_value`, `moving_average`, `linear_regression`). Propagate this to the API and
      the UI instead of silently degrading to a naive number that looks authoritative.
- [ ] Frontend: an explicit "not enough data yet — needs N more entries" state distinct from
      "zero".

### 1.4 — Assumption ledger on simulations

- [ ] `models/simulation.py` — add to `ScenarioResult`: `assumptions: list[str]`,
      `evidence_level: str`, `valid_horizon_days: int`.
- [ ] `services/simulation_service.py` — emit assumptions explicitly (currently implicit in
      code): sustained adherence, linear effect, no confounding change, stable income, etc.
- [ ] **Stop presenting `confidence_score` as "confidence" in the UI.** It is
      `0.2 + 0.15 · min(days_logged, 5)` — a data-volume proxy that has never been validated
      against outcomes. Relabel to "data sufficiency" until Phase 3 produces a calibrated number.

### 1.5 — Verification gate

- [ ] Default parameters reproduce pre-change scores exactly (regression test).
- [ ] Burnout clusters are stable across reruns (fixed seed) and silhouette ≥ 0.35.
- [ ] `pytest tests/ -q` green; `npx eslint . && npx vite build` clean.

---

## Phase 2 — Memory & conversational interface

Largest perceived capability gain per unit of work.

### 2.1 — Tool-calling assistant

Today `services/ai_assistant_service.py` sends one flat context string and has **no tools, no
retrieval, no memory**.

- [ ] `services/tools/` — typed tool registry wrapping existing services. Each tool declares a
      JSON schema, executes deterministically, returns structured output with provenance:
  - `get_metrics(domain, window)` → existing analytics services
  - `get_goals(status)` → `user_service`
  - `forecast(target, horizon)` → `forecast_service` / `trend_prediction_service`
  - `simulate(domain, params)` → `simulation_service`
  - `get_transactions(filters)` / `get_study_sessions` / `get_habit_logs`
  - `search_memory(query)` / `write_memory(content)` / `delete_memory(id)`
  - `reconstruct_state(as_of)` → `twin_state_service`
- [ ] `services/orchestrator_service.py` — intent detection → clarify gate → tool planning →
      parallel execution → sufficiency gate → synthesis.
- [ ] **Numeric guardrail:** post-generation validator extracts every numeric token from the LLM
      response and cross-checks it against the tool-output set. Unmatched figure ⇒ regenerate
      once, then fail closed. This is the structural defence against hallucinated numbers.
- [ ] `api/v1/assistant.py` — keep `@limiter.limit(...)`; raise the limit budget for multi-tool
      turns. Stream tokens.
- [ ] Keep the existing Gemini → Groq fallback in place.

### 2.2 — Structured memory

- [ ] `models/memory.py` — `Memory` Document: `user_id`, `kind` (`SEMANTIC | PREFERENCE |
      PROCEDURAL | REFLECTIVE | DECISION`), `content`, `embedding: Optional[list[float]]`,
      `importance`, `confidence`, `source_event_id`, `superseded_by`, `deleted_at`,
      `created_at`. Register in `core/database.py`.
- [ ] `services/memory_service.py` — create, supersede (**never mutate in place**), retrieve,
      soft-delete with cascade.
- [ ] Vector search **only** for `REFLECTIVE` (journal/free text). Everything else is a typed
      query. Use MongoDB Atlas Vector Search — no new datastore.
- [ ] "Remember this" / "forget this" intents wired to `write_memory` / `delete_memory`.
- [ ] Deletion must cascade to derived beliefs and cached snapshots — a memory deleted but still
      baked into a posterior is a privacy violation with extra steps.

### 2.3 — Journal entries

- [ ] `models/journal.py` — `JournalEntry` Document (`user_id`, `content`, `entry_date`,
      `embedding`, `created_at`). Register in `core/database.py`.
- [ ] `api/v1/journal.py` — CRUD.
- [ ] Frontend: journal page.
- [ ] Embedding generation on write (background). **Requires explicit user consent** before any
      journal text leaves the system (see design doc §20).

### 2.4 — Explanation framework

- [ ] `models/explanation.py` — `Explanation` Document: `user_id`, `request_id`,
      `question`, `tools_called[]`, `inputs_used[]`, `assumptions[]`, `confidence`,
      `what_would_change_it[]`, `created_at`.
- [ ] Every recommendation/prediction response carries an `explanation_id`.
- [ ] `GET /explanations/{id}` answers "why did you say that?" offline.

### 2.5 — Golden evaluation set

- [ ] `tests/golden/` — ~100 real questions with known-correct answers/expected tool calls.
- [ ] `scripts/run_golden_set.py` — reports intent accuracy, tool-selection accuracy,
      hallucination rate, refusal correctness.
- [ ] **Build this before shipping conversational features** — it cannot be retrofitted honestly
      once behaviour has drifted (you end up encoding current behaviour as "correct").

### 2.6 — Verification gate

- [ ] Golden set: intent ≥ 90%, tool selection ≥ 85%, hallucinated figures < 1%.
- [ ] Numeric validator provably rejects a response containing a fabricated figure (test with a
      forced-hallucination fixture).

---

## Phase 3 — Prediction engine + supervised ML

### 3.1 — Persist every prediction

Without this, calibration is unmeasurable **in principle**.

- [ ] `models/prediction.py` — `Prediction` Document: `user_id`, `target`, `made_at`,
      `horizon_days`, `point_estimate`, `interval_low`, `interval_high`, `model_id`,
      `model_version`, `features_hash`, `method_tier`, `realised_value: Optional`,
      `realised_at: Optional`, `error: Optional`. Register in `core/database.py`.
- [ ] `services/prediction_registry_service.py` — `record_prediction()`, `resolve_prediction()`.
- [ ] Every call in `forecast_service`, `trend_prediction_service`, `productivity_service`
      records its prediction.
- [ ] `scripts/score_predictions.py` — worker that resolves matured predictions against actuals.

### 3.2 — Prediction intervals

- [ ] Replace point-estimate returns with intervals derived from residual variance in
      `_linear_regression_forecast` / `_moving_average_forecast`.
- [ ] **Consolidate the duplicated tier logic** now, before each tier carries a fitted model.
      `_select_method`, `_naive_forecast`, `_moving_average_forecast`,
      `_linear_regression_forecast`, `_compute_confidence` are currently triplicated across
      `forecast_service`, `trend_prediction_service`, `productivity_service`. Extract to
      `services/forecasting/core.py`. **This changes a documented `CLAUDE.md` convention
      ("intentionally duplicated per-engine") — update that file in the same PR with the
      reasoning: duplication was acceptable for 30 lines of arithmetic, not for fitted models.**
- [ ] Replace `_compute_confidence()`'s heuristic with empirical interval coverage once ≥ 30
      resolved predictions exist per target.

### 3.3 — Goal completion probability (ML model #2)

See [full spec](#model-2--goal-completion-probability).

### 3.4 — Habit failure prediction (ML model #3)

See [full spec](#model-3--habit-failure-prediction).

### 3.5 — Calibration & drift monitoring

- [ ] `services/ml/calibration.py` — Brier score, ECE, reliability curves over resolved
      predictions.
- [ ] `scripts/calibration_report.py`.
- [ ] Drift monitors: input drift (feature distribution shift), outcome drift (rolling error),
      calibration drift (ECE increase). On drift ⇒ **widen intervals and lower stated
      confidence**, do not silently continue.
- [ ] **Every model must beat a stated naive baseline** (persistence / personal mean) on held-out
      data or it does not ship. Reframe `ACCURACY_THRESHOLD_PCT = 85.0` in
      `scripts/backtest_forecast_accuracy.py` as **lift over baseline**, not absolute accuracy —
      85% absolute is meaningless if "same as last month" scores 84%.

### 3.6 — Verification gate

- [ ] ECE < 0.10 on each shipped probabilistic model.
- [ ] 80% intervals empirically cover ~80%.
- [ ] Every model documented with its baseline and measured lift.

---

## Phase 4 — Causal DAG & probabilistic simulation

**Highest-risk phase.** Do not start before Phase 3's calibration infrastructure exists.

### 4.1 — Causal graph

- [ ] `models/causal.py` — `CausalEdge` Document: `user_id`, `cause`, `effect`, `strength`,
      `ci_low`, `ci_high`, `evidence_type` (`DECLARED | OBSERVATIONAL | EXPERIMENTAL`),
      `n_observations`, `confounders_adjusted[]`, `status`, `last_evaluated_at`.
- [ ] `services/causal_service.py`:
  - Seed the DAG with **declared** edges (user- or designer-asserted structure).
  - Discover candidate associations from user data.
  - **Eligibility guards before any edge reaches T1:** temporal precedence, ≥ 20 observations per
    condition, no obvious reverse-causation path, stability across a held-out time split. Edges
    failing these stay T0 permanently regardless of correlation strength.
  - Multiple-comparison correction (Benjamini–Hochberg) on discovery.
- [ ] **Evidence tiers are enforced in the API contract**, not left to prompt discipline. A T0
      edge is structurally incapable of producing a causal sentence.

### 4.2 — Monte Carlo simulation

- [ ] `services/simulation/dag_engine.py` — topological propagation with `do()` semantics
      (sever inbound edges to the intervened node — this is what makes it an intervention rather
      than a conditional observation).
- [ ] **Vectorise with NumPy**: sample all N draws simultaneously as arrays. Naive looping is
      ~5.4M node evaluations for N=2000 × 30 nodes × 90 steps and will miss the 5 s budget by an
      order of magnitude; the vectorised form reduces to ~90 × 30 array ops and fits comfortably.
- [ ] Adherence decay as an explicit, surfaced assumption — a 3-month daily commitment is rarely
      sustained at 100%, and a simulation assuming it is will overstate outcomes substantially.
- [ ] Sensitivity analysis (one-at-a-time, or Sobol on the dominant few inputs).
- [ ] Horizon truncation: refuse to project beyond where the evidence supports.
- [ ] Keep the existing deterministic path as a fast fallback when the DAG is too sparse.
- [ ] Extend `scripts/benchmark_simulation.py` to cover the Monte Carlo path against the 5 s
      criterion.

### 4.3 — Verification gate

- [ ] Simulation p95 < 5 s at N=2000.
- [ ] Monte Carlo convergence check (results stable across seeds).
- [ ] A T0-only DAG produces association language, never causal language (assert in tests).

---

## Phase 5 — Decision & optimization

### 5.1 — Decision engine

- [ ] `services/decision_service.py` — frame → generate options → filter infeasible →
      simulate each → score by expected utility → rank → explain.
- [ ] Utility: `E[U] = Σ w_g · progress_g − λ · risk_penalty − opportunity_cost`, with `w_g`
      from **user-declared** goal priority and `λ` from the existing
      `profile.risk_tolerance` (`CONSERVATIVE | MODERATE | AGGRESSIVE`) already on the User model.
- [ ] Report **worst case (5th percentile)** and "what would flip this", not just the winner —
      for irreversible or cash-constrained decisions the downside matters more than the mean.
- [ ] Extend the existing `Recommendation` Document: add `options_considered[]`, `assumptions[]`,
      `expected_outcome`, `realised_outcome`, `explanation_id`. Relax the currently-required
      `recommended_scenario_name` / `simulation_id` coupling so recommendations can originate
      outside the simulation engine. **Do not break
      `feedback_service.get_satisfaction_summary()`**, which aggregates
      `Recommendation.user_feedback`.

### 5.2 — Goal priority & constraints

- [ ] `models/user.py` — add `priority: int` to `ActiveGoal`.
- [ ] `models/constraint.py` — `Constraint` Document: hard limits (weekly hours available, cash
      floor, fixed commitments, exam dates). Distinct from preferences: violating a constraint
      invalidates a plan; violating a preference only costs utility.

### 5.3 — Optimization

- [ ] `services/optimization_service.py` — MILP over weekly time allocation (PuLP or OR-Tools).
- [ ] **Infeasibility is a first-class, valuable output**: *"no feasible allocation exists; you
      are over-committed by 23 h/week; here are the three smallest goal relaxations that restore
      feasibility."* The most common real cause of falling behind is that the declared goals were
      never simultaneously achievable — the current system cannot express this because it has no
      concept of a time budget.
- [ ] Greedy priority-fill fallback when MILP is infeasible or too slow.

### 5.4 — Override learning

- [ ] Record when the user chooses against a recommendation; ask once, non-naggingly, why.
- [ ] Repeated overrides in a consistent direction update preference memory — treat as signal
      that the utility weights are wrong, not as user error.

---

## Phase 6 — Experiments & contextual bandits

### 6.1 — n-of-1 experiment framework

- [ ] `models/experiment.py` — `Experiment` Document: `user_id`, `hypothesis`, `metric`,
      `intervention`, `baseline_window`, `assignment_schedule[]`, `washout_days`,
      `mde` (minimum detectable effect), `adherence_log[]`, `result`, `conclusion`,
      `status`, `created_at`.
- [ ] `services/experiment_service.py`:
  - **Power check gate** — given the user's historical variance in the metric, what effect size
    is detectable in the available days? If MDE > plausible effect, **refuse to run** and say so.
    "This test can't detect a realistic effect in 14 days" is a correct and valuable answer.
  - **Randomised block assignment** (`A B B A B A A B`), never "2 weeks of A then 2 weeks of B" —
    the latter confounds the intervention with time, which carries exams, seasons, mood cycles
    and novelty effects.
  - Washout days where carryover is plausible.
  - Adherence tracked **separately from outcome** — low adherence invalidates the result, it does
    not become a negative finding.
  - Bayesian effect estimate + credible interval. Report the interval, never a p-value dichotomy.
- [ ] On completion: promote/demote the causal edge (T0/T1 → T3) and update twin beliefs.
- [ ] **Guardrails:** one active experiment at a time; nothing touching health, medication, or
      finances beyond a user-set cap without explicit confirmation; abortable instantly with no
      guilt framing; negative results explicitly framed as real results.

### 6.2 — Contextual bandit (the only appropriate RL)

See [full spec](#model-5--recommendation-selection-bandit).

- [ ] `services/ml/recommendation_bandit.py` — Thompson sampling over recommendation
      variants. Reward = follow-through, observable within a day.
- [ ] Reuses `Recommendation.user_feedback`, which **already collects the reward signal**.
- [ ] Shares machinery with 6.1 — a bandit is the adaptive-allocation version of the same
      experiment framework.

---

## Phase 7 — External integrations

In value order. Each replaces self-reported data with measurement.

- [ ] **Calendar** (Google/CalDAV) — ground truth for time availability. Highest value; unblocks
      real feasibility checks and daily planning. Webhook + 15-min batch.
- [ ] **Bank / finance aggregator** — replaces the weakest self-reported data. **Requires MFA
      first (non-negotiable).** Daily batch.
- [ ] **GitHub** — objective project-progress signal. Webhook.
- [ ] **Wearable** — turns sleep from self-report into measurement, which materially improves
      every sleep-related causal edge. Daily batch.

**Ingestion requirements for all:** idempotency key `hash(source, external_id)`; provenance
ranking (bank > manual); conflict surfacing above a materiality threshold rather than silent
resolution; user corrections always win and create a `DECLARED` override.

**Never build:** email content, browser history, keystroke/screen monitoring. See
[What NOT to build](#what-not-to-build).

---

## Phase 8 — Learned personalization

Only after Phases 3 and 6 have produced real longitudinal data.

- [ ] `models/belief.py` — `Belief` Document: `user_id`, `parameter`, `posterior` (distribution +
      params), `n_observations`, `prior_source`, `updated_at`.
- [ ] `services/ml/hierarchical.py` — per-user posteriors with population priors.
- [ ] Priors come from Phase 1's user-declared values, or from external datasets
      ([strategy below](#external-dataset-strategy)).
- [ ] Twin parameters resolve in order: **learned posterior → user-declared → hardcoded default.**
      At n=0 behaviour is identical to today; the transition is continuous with no cutover.
- [ ] `scripts/refresh_posteriors.py` — scheduled worker.

---

## ML model specifications

### Model 1 — Burnout risk clustering

| | |
|---|---|
| **Type** | Unsupervised — K-Means or Gaussian Mixture |
| **Why this first** | The slot already exists and is empty. `User.digital_twin_state.burnout_risk_cluster` and `HabitTracking.burnout_risk_cluster` are declared, typed, surfaced in `schemas/user_schema.py` and `schemas/habit_schema.py`, and returned by `api/v1/users.py:82` — but `api/v1/habits.py:93` documents that it "is written by nothing" and `services/user_service.py:148` leaves it "intentionally untouched". The field is literally named *cluster*. |
| **Labels** | None required — this is why it can ship first |
| **Features** | Rolling 14/30-day windows: mean + variance of sleep hours; exercise minutes; screen time; study hours; habit-score volatility; streak breaks; missed-log ratio (informative missingness); study-hours trend slope; weekend/weekday delta |
| **Target output** | Assign to existing `BurnoutRisk` enum: `LOW_RISK`, `MODERATE_RISK`, `HIGH_RISK`, `CRITICAL_BURNOUT`, `UNKNOWN` |
| **Cluster→label mapping** | Order clusters by a composite severity score (low sleep + high screen + high volatility + rising missed-logs). **Mapping must be reviewed by a human, not auto-assigned** — the enum names imply clinical meaning the model cannot justify |
| **Cold start** | `UNKNOWN` until ≥ 14 days of habit logs. Never guess |
| **Evaluation** | Silhouette ≥ 0.35; cluster stability across bootstrap resamples; face-validity review of exemplar members |
| **Uncertainty** | Report distance-to-centroid as assignment confidence; borderline members ⇒ `UNKNOWN` |
| **Retraining** | Weekly, per-user population pooled |
| **Safety** | Present as `INFERRED` behavioural pattern, **never** as a clinical or diagnostic claim. Copy must avoid medical framing entirely |
| **Files** | `services/ml/burnout_clustering.py`, `scripts/train_burnout_model.py`, `tests/test_burnout_clustering.py` |

### Model 2 — Goal completion probability

| | |
|---|---|
| **Type** | Binary classification — logistic regression with hierarchical prior → gradient boosting at n ≥ 200 |
| **Labels** | ⚠️ **CORRECTION — labels are *not* free, and cannot be reconstructed.** An earlier draft of this file claimed they were; that was wrong. See "Label availability" below before planning any work here |
| **Features** | Current progress ratio; elapsed vs total time; required-rate vs observed-rate ratio; goal category (`FINANCE`/`STUDY`/`HABIT`/`FITNESS`/`CAREER`); target magnitude; days to deadline; user's historical completion base rate; count of competing active goals; recent contribution frequency (`linked_goal_id` transactions for finance goals) |
| **Baseline to beat** | User's historical base completion rate |
| **Evaluation** | Brier score, reliability diagram, ECE, AUC. **Calibration matters more than accuracy** — a probability is only useful if 70% means 70% |
| **Uncertainty** | Native predicted probability; widen when feature support is thin |
| **Cold start** | Population prior until the user has ≥ 5 resolved goals |
| **Files** | `services/ml/goal_completion.py`, `scripts/train_goal_model.py`, `tests/test_goal_completion.py` |

#### Label availability — read this first

The target label is *"did this goal complete by its deadline?"* Three facts about the current
schema make that label unrecoverable today:

1. **There is no failure state.** `GoalStatus` is `ACTIVE | COMPLETED` only (`models/enums.py`). A
   goal whose `target_date` passed without completion is still `ACTIVE` — indistinguishable from
   one legitimately still in progress.
2. **There is no completion timestamp.** `ActiveGoal` carries `created_at` and `target_date` but no
   `completed_at`. So even for a `COMPLETED` goal you cannot tell whether it finished before or
   after its deadline — which is precisely the label.
3. **Status is derived and reversible, not historical.** `user_service.py:313` recomputes it on
   every write: `COMPLETED if merged_current >= merged_target else ACTIVE`. Deleting a linked
   transaction reverses progress through `goal_progress_service`, so a `COMPLETED` goal can silently
   revert to `ACTIVE`. The field is a snapshot of a comparison, not a record of an event.

Net: **existing goals yield zero usable training rows**, and no backfill can recover them — the
information was never written. Current real volume is also ~3 goals on 1 seeded user.

#### Actual scope — three steps, training is last

**Step 1 — start capturing the label (do this now; it is cheap and every day of delay costs data).**

- [ ] Add `GoalStatus.MISSED` — or, better, derive missed-ness from a timestamp rather than adding
      a third reversible state.
- [ ] Add `completed_at: Optional[datetime]` to `ActiveGoal`, set once on the `ACTIVE → COMPLETED`
      transition and **not cleared** if progress later dips (the event happened; a subsequent
      reversal is a separate event).
- [ ] Emit a `GOAL_STATUS_CHANGED` event (Phase 0's event log) carrying `from`, `to`, `occurred_at`,
      `current_value`, `target_value`. This is the durable record; the field is the convenience.
- [ ] Backward compatibility: existing goals get `completed_at = None` and are **excluded from
      training**, not imputed. An imputed completion date is a fabricated label.

**Step 2 — make the model trainable and evaluable.** Even with step 1 shipped, one user producing
a few goals a month will not reach a trainable n for a long time. Two options, not mutually
exclusive:

- [ ] **Synthetic goal histories** (`scripts/generate_synthetic_users.py`, see External dataset
      strategy). This is what makes the model *evaluable* — you can hold out, measure calibration,
      and produce a reliability diagram. For a capstone this is the load-bearing piece, and it must
      be clearly labelled as synthetic in any writeup.
- [ ] **Population priors** from a public goal/habit-adherence dataset, used as the prior only.

**Step 3 — train, calibrate, ship.** Only once steps 1–2 exist.

- [ ] Baseline first: the user's historical base completion rate. The model must beat it.
- [ ] Report Brier score, reliability diagram, ECE — **not** accuracy. A goal tracker where 70% of
      goals complete gets 70% "accuracy" from a constant predictor.
- [ ] Do not surface a probability until calibration is measured (same discipline as
      `confidence_score`, see `REMEDIATION_PLAN.md` §5).

> **Why step 1 is urgent even though step 3 is far away:** the label is only capturable *going
> forward*. Every week without `completed_at` and the status-change event is a week of training
> data permanently lost. This is the cheapest high-value change in the whole plan — a field, a
> transition hook, and an event.

### Model 3 — Habit failure prediction

| | |
|---|---|
| **Type** | Binary classification — logistic → GBM |
| **Target** | P(habit streak breaks within next 7 days) |
| **Labels** | Free — derived from logged adherence history in `HabitTracking` |
| **Features** | Current streak length; 7/14/30-day adherence rate; day-of-week; sleep hours (lagged 1–3 days); study/work load; recent missed-log pattern; screen time trend; time since last break |
| **Baseline** | Base rate of breaks in any 7-day window |
| **Evaluation** | Brier, precision@k (only the top-k alerts get shown), calibration |
| **Product constraint** | This drives proactive nudges — **precision matters far more than recall.** A false "you're about to fail" alert is corrosive to trust; a missed one costs little |
| **Files** | `services/ml/habit_failure.py`, `tests/test_habit_failure.py` |

### Model 4 — Forecast intervals (upgrade, not new model)

| | |
|---|---|
| **Type** | Extend existing linear/MA forecasters |
| **Change** | Return prediction intervals from residual variance instead of a point estimate plus the `_compute_confidence()` heuristic |
| **Note** | `_linear_regression_forecast()` is *already* a learned model — it fits a slope from user data. The defect is output shape, not determinism |
| **Evaluation** | Empirical interval coverage: an 80% interval should contain the realised value ~80% of the time |
| **Files** | `services/forecasting/core.py` (consolidated from three duplicated copies) |

### Model 5 — Recommendation selection bandit

| | |
|---|---|
| **Type** | Contextual bandit, Thompson sampling |
| **Why this is the *only* appropriate RL** | Full RL fails here on five counts: **(1)** one episode = one day ⇒ ~365 samples/year vs the 10³–10⁶ episodes RL needs — a 3–4 order-of-magnitude shortfall, not a tuning gap; **(2)** non-stationary dynamics (semesters, jobs, illness) violate the MDP assumption; **(3)** model-based RL needs a simulator, but the simulator's fidelity is the entire open question, so the agent would optimise against its own errors; **(4)** exploration means deliberately giving a real person worse financial/study advice to reduce policy uncertainty — not an acceptable trade; **(5)** one trajectory, no resets, no counterfactual ⇒ no credit assignment. Bandits avoid all five: no long-horizon credit assignment, orders of magnitude fewer samples, and a fast reward |
| **Arms** | Recommendation variants — framing, timing, granularity |
| **Context** | Twin state features, time of day, recent adherence |
| **Reward** | Follow-through within 24h. **`Recommendation.user_feedback` already collects this** |
| **Evaluation** | Cumulative regret vs. a fixed-policy baseline |
| **Relationship to Phase 6.1** | Same machinery as the n-of-1 framework; the only difference is whether allocation is fixed in advance (trial) or updated online (bandit) |
| **Files** | `services/ml/recommendation_bandit.py` |

---

## External dataset strategy

Public datasets (Kaggle, UCI) have three sound uses and one that must be avoided.

### ✅ Use 1 — Derive priors for hierarchical models (Phase 8)

Fit a population-level relationship on public data; use its coefficients as the prior mean and
variance for each user's per-user posterior. This is exactly what hierarchical modelling wants:
real population evidence, then shrinkage toward the individual as their own data accumulates.

### ✅ Use 2 — Give the hardcoded constants provenance (Phase 1)

`STUDY_HOURS_BENCHMARK = 2.0` and `SLEEP_HEALTHY_RANGE = (7.0, 9.0)` are currently invented
numbers. Derived from a real dataset and cited, they become defensible defaults. Same code,
actual justification. Document the source dataset next to the constant.

### ✅ Use 3 — Synthetic histories for testing (Phase 0 onward)

Generate realistic multi-month user timelines to exercise the analytics engines, backtest the
forecast tiers, and validate the simulation pipeline — without needing real users and without a
live DB (matching the existing `tests/conftest.py` pattern). Highly practical here.

- [ ] `scripts/generate_synthetic_users.py`
- [ ] `tests/fixtures/synthetic/` — committed, seeded, deterministic

### ❌ Anti-use — Train on public data, serve predictions about *this* user

**Construct mismatch + distribution shift.** A public "student performance" set measures
different variables, on a different population, with different instruments; its "study hours" is
not this app's self-logged "study hours". A model trained on it will produce confident,
well-formed, invalid numbers about a specific person — worse than having no model, because it is
not obviously wrong.

**Rule:** external data may set *priors and defaults*; only the user's own data may drive
*predictions about the user*.

---

## Dependencies to add

Current `requirements.txt` has **no numerical or ML stack at all** — no numpy, scipy, pandas, or
scikit-learn. Add per phase, not upfront:

| Phase | Package | Purpose |
|---|---|---|
| 1 | `numpy`, `scikit-learn` | Burnout clustering |
| 3 | `scipy` | Residual variance, interval computation, statistical tests |
| 3 | `scikit-learn` | Logistic regression, gradient boosting, calibration curves |
| 4 | `numpy` (vectorised) | Monte Carlo propagation |
| 5 | `pulp` *or* `ortools` | MILP time allocation |
| 6 | `scipy.stats` | Bayesian effect estimation, Thompson sampling |
| 8 | `numpyro` *or* `pymc` | Hierarchical Bayesian posteriors — **evaluate whether conjugate updates in numpy suffice first**; a full PPL may be unnecessary weight |
| 2 | Atlas Vector Search | Journal embeddings — no new datastore required |

Pin exact versions, matching the existing file's convention.

---

## What NOT to build

Explicit non-goals. Revisit only with a documented reason.

| Item | Why not |
|---|---|
| **Full reinforcement learning** | Five independent blockers — see [Model 5](#model-5--recommendation-selection-bandit). Contextual bandits only |
| **Deep learning** | Data volume is 10²–10⁴ points per user. Nothing here justifies it |
| **Neo4j / dedicated graph DB** | A personal causal DAG is ~10² nodes; it fits in a document and traverses in microseconds |
| **Dedicated time-series DB** | Mongo time-series collections cover ~10³–10⁴ points/user/year |
| **Feature store** | Justified only with several models sharing features. A versioned feature module suffices |
| **Redis** | Not until app instance #2 — but note in-process `slowapi` **silently breaks** when horizontally scaled, so this arrives *with* scaling, not after |
| **Kafka** | Not until multiple independent event consumers exist |
| **Email / browser / keystroke / screen ingestion** | Highest sensitivity, lowest reliability. The signal does not justify the surveillance relationship it creates |
| **Autonomous action** | "Proposes, never disposes" is a permanent constraint, not a temporary limitation. Nothing consequential executes without user confirmation, at any phase |
| **The 11 agents that should be services** | Goal/Study/Finance/Habit/Prediction/Simulation/Optimization/Memory/Decision/Research/Analyst are deterministic functions. Only Orchestrator, Reflection, and Experiment-designer are genuine agents |

---

## Cross-cutting requirements

Apply to every phase:

- [ ] **Refusal path.** "I don't have enough information — I'd need at least three weeks of sleep
      logs" is a first-class, well-crafted response, not an error state.
- [ ] **Never present uncertain output as certain.** Every estimate carries an interval; every
      simulation carries its assumptions and evidence level.
- [ ] **Financial hard rules** the LLM cannot override: never recommend depleting the emergency
      fund below the user's declared floor; never present a forecast as guaranteed; flag
      irreversible downside for explicit confirmation.
- [ ] **Staleness.** Every surfaced figure carries `as_of`; past a per-metric threshold it is
      labelled stale rather than shown as current.
- [ ] **Feedback-loop tagging.** The system's own recommendations change behaviour, which becomes
      training data. Tag recommendation-influenced periods so models can distinguish organic from
      induced behaviour — otherwise the system learns from its own echo.
- [ ] **Tests follow the existing pattern** — zero live DB, mock I/O individually per
      `tests/conftest.py`.
- [ ] **Every phase ends with** `pytest tests/ -q` green and, for any frontend change,
      `npx eslint . && npx vite build` clean.

---

## Open questions to resolve before starting

1. **Is this a single-user personal system or multi-tenant product?** Changes the priority of
   Redis, MFA, per-user model training cost, and secret management substantially.
2. **What is the real deadline and evaluation criteria?** If this is assessed as a capstone,
   Phases 0–3 plus Models 1 and 2 form a defensible, complete story with genuine ML. Phases 4–8
   are a research programme, not a deliverable.
3. **Is there budget for a second Atlas cluster?** Free tier suffices for staging; confirm before
   Phase 0.
4. **Consent model for journal text leaving the system?** Blocks Phase 2.3's embedding work.
