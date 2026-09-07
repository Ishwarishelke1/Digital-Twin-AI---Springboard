# Digital Twin AI — Capstone Report

A personal analytics system for finance, study and habits, with two calibrated predictive
models — and an account of what broke, what the numbers do and do not establish, and what
was deliberately left unbuilt.

| | |
| :--- | :--- |
| Backend | ~14.7k lines (FastAPI + MongoDB Atlas + Beanie) |
| Frontend | ~10.3k lines (React 19 + Vite + Tailwind v4) |
| Endpoints | 66 across 12 routers |
| Tests | 322 passing |
| Models | 2, both calibrated and evaluated |

A formatted version of this report is published at
<https://claude.ai/code/artifact/fc375837-0477-4553-840a-6d099662023f>.

---

## Contents

1. [Summary](#1-summary)
2. [Problem](#2-problem)
3. [System architecture](#3-system-architecture)
4. [The label problem](#4-the-label-problem)
5. [Synthetic data](#5-synthetic-data)
6. [Model 1 — goal completion](#6-model-1--goal-completion)
7. [Model 2 — habit failure](#7-model-2--habit-failure)
8. [Robustness of the assumptions](#8-robustness-of-the-assumptions)
9. [Serving, and knowing when to refuse](#9-serving-and-knowing-when-to-refuse)
10. [Engineering rigour: what broke](#10-engineering-rigour-what-broke)
11. [Limitations](#11-limitations)
12. [Future work](#12-future-work)
13. [Conclusion](#13-conclusion)

---

## 1. Summary

Digital Twin AI tracks a person's finances, study and daily habits, computes analytics over
that history, and predicts two things: whether a goal will be met by its deadline, and
whether a habit streak is about to break. It is a FastAPI and MongoDB backend with a React
frontend, 66 endpoints, and 322 tests.

Both models are calibrated and beat their baselines. Both are trained on synthetic data,
which is stated plainly throughout because it bounds what the results mean: they demonstrate
the pipeline is correct, not that the models predict real people.

| Model | Baseline | Model | AUC | ECE | Headline |
| :--- | ---: | ---: | ---: | ---: | :--- |
| **Goal completion** | 52.1% | 83.7% | 0.939 | 0.069 | +31.6pp over base rate |
| **Habit failure** | 77.6% | 84.6% | 0.783 | 0.014 | 99.1% precision on the riskiest 5% of days |

Three findings are worth more than the accuracy figures:

1. **The first model was confidently wrong the first time it saw real data**, for a reason
   offline evaluation is structurally incapable of detecting (§10).
2. **The conclusions survive varying every generative assumption** — 36 configurations, AUC
   never leaving 0.893–0.962 (§8).
3. **Neither model class won twice.** Logistic regression calibrated better on goals;
   gradient boosting on habits. The lesson is that the choice must be measured, not
   assumed (§7).

---

## 2. Problem

People track goals and habits in apps that record what happened but say nothing about what
is likely to happen. A savings goal showing "₹13,200 of ₹30,000" tells you where you are; it
does not tell you whether you are going to make it. The judgement — am I on track, and if not
what is it costing me — is left entirely to the user, at exactly the moment they are least
placed to be objective about it.

This project asks whether that judgement can be made explicit, quantified, and shown
honestly. "Honestly" is load-bearing: a system that predicts confidently and wrongly about
someone's money or study time is worse than one that says nothing, because it will be
believed.

Two predictions were built:

- **Goal completion** — will this goal reach its target by its deadline?
- **Habit failure** — will this streak break within seven days?

They differ in an instructive way. The first informs a decision the user makes at their own
pace. The second drives a notification, which spends the user's attention whether or not it
was warranted — and that difference changes which metric matters (§7).

---

## 3. System architecture

```
┌──────────────────────────────────────────────────────────────┐
│  React 19 + Vite + Tailwind v4 · 13 pages · design tokens    │
└───────────────────────────┬──────────────────────────────────┘
                            │ httpOnly JWT cookie (token-version claim)
┌───────────────────────────▼──────────────────────────────────┐
│  FastAPI · 66 endpoints · domain exceptions · rate limiting  │
└──┬────────────┬─────────────┬──────────────┬─────────────────┘
   │            │             │              │
┌──▼───────┐ ┌──▼──────────┐ ┌▼───────────┐ ┌▼────────────────┐
│ Domain   │ │ Analytics   │ │ ML serving │ │ AI assistant    │
│ finance  │ │ forecast    │ │ goal compl.│ │ Gemini → Groq   │
│ study    │ │ productivity│ │ + OOD guard│ │ grounded on the │
│ habits   │ │ habit-anal. │ │            │ │ twin snapshot   │
│ goals    │ │ trends, sim │ │            │ │                 │
└──┬───────┘ └──┬──────────┘ └─────┬──────┘ └─────────────────┘
   │            │                  │
┌──▼────────────▼──────────────────▼───────────────────────────┐
│  MongoDB Atlas via Beanie ODM · prod + staging               │
└──────────────────────────────────────────────────────────────┘
```

Two conventions shaped the backend. **Analytics engines compose rather than reimplement**:
services built on top of the base engines call their public methods rather than re-querying
Mongo, even where that means duplicating small arithmetic. And **forecasts degrade
explicitly** — each engine selects its method from how much history exists
(`insufficient_data` → `naive_last_value` → `moving_average` → `linear_regression`) and
reports which one it used, so a projection from three data points is never presented like one
from thirty.

### Operational work

Beyond the application, three pieces of infrastructure proved necessary rather than optional:

- A **production write guard**. The repository's seeding script opens by deleting three
  collections against whichever database the environment points at — which was production. It
  now refuses unless the target is explicitly named.
- A **scripted backup and restore drill**. The cluster is Atlas M0, which has no automated
  backup, so a manual dump is the entire recovery strategy. The drill dumps, restores into a
  scratch database, and compares per-collection counts — verifying the backup rather than
  assuming it.
- A **staging database**, so migrations are rehearsed before they touch real data.

---

## 4. The label problem

The first obstacle was not modelling. It was that the thing to be predicted had never been
recorded.

Three properties of the existing schema made the goal-completion label unrecoverable:

1. **No failure state.** `GoalStatus` was `ACTIVE | COMPLETED`. A goal past its deadline and
   unfinished was still `ACTIVE` — indistinguishable from one legitimately in progress.
2. **No completion timestamp.** So even for a completed goal, there was no way to know whether
   it finished before or after its deadline — which is precisely the label.
3. **Status was derived, not recorded.** Recomputed on every write as
   `COMPLETED if current >= target`, and therefore reversible: deleting a linked transaction
   silently reverted a completed goal.

> **The consequence.** Existing goals yielded **zero** usable training rows, and no backfill
> could recover them — the information had never been written. The label was only capturable
> *going forward*. So `completed_at` was designed and shipped well before any model existed to
> consume it, because every week without it was training data permanently lost.

It is stamped once on the first `ACTIVE → COMPLETED` transition and never cleared. Status
remains reversible; the timestamp does not, because the completion happened and a later
reversal is a separate fact.

> **A bug found while building it.** Adding the timestamp revealed that goals *never
> auto-completed at all*. Status was derived only in the manual-edit path, while the function
> that applies progress from a linked transaction, study session or habit log — called from 14
> sites — only incremented the value. A goal funded exactly as intended sat at `ACTIVE` forever
> with `current_value >= target_value`.

---

## 5. Synthetic data

The production database holds five users. Nothing is trainable at that size, and — more
limiting — nothing is *evaluable*: no held-out set, no calibration curve, no baseline
comparison. Both models are therefore trained on generated data.

### Process simulation, not label sampling

The obvious approach is to sample the label directly from a logistic function of the
features. That bakes the answer in: the model then recovers exactly the relationship the
generator was told to use, and the evaluation is circular — it measures nothing but the
arithmetic.

Instead both generators simulate the **underlying process**. For goals, a user contributes
day by day at a rate driven by latent traits, and completion emerges from whether the total
reaches the target in time. For habits, daily biometrics follow an effort level that walks
with momentum, and a break emerges when the composite score falls below the app's own
threshold. The feature–label relationship is a *consequence* of the simulation rather than an
assumption, which is what makes the evaluation mean anything.

> **Matching the product's own definitions.** The habit generator scores each day using the
> same equal-weighted composite over sleep, exercise, water and screen time that the dashboard
> uses, with the same threshold of 70. A break is a logged day below that, or two consecutive
> days with no log — mirroring the streak logic already in the codebase, which keeps a streak
> alive if today *or* yesterday has an entry. Had the model learned a different notion of
> failure than the dashboard displays, its predictions would have contradicted the rest of the
> application.

Both generators encode their mechanisms as explicit named constants — category difficulty,
competition dilution, adherence decay, deadline sprints, disruption, momentum, logging
behaviour — which is what makes the sensitivity analysis in §8 possible at all.

---

## 6. Model 1 — goal completion

886 goals across 120 users. Held out 25% **by user**, not by row: goals belonging to one
person share that person's habits, so a random row split lets the model learn the individual
rather than the pattern, inflating scores that then collapse on anyone new. The split is
asserted in code rather than assumed.

| Model | Accuracy | Lift | AUC | Brier | ECE |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Base rate | 52.1% | — | 0.500 | 0.254 | 0.066 |
| **Logistic regression** ← ships | **83.7%** | **+31.6pp** | **0.939** | **0.105** | **0.069** |
| Gradient boosting | 84.7% | +32.6pp | 0.918 | 0.128 | 0.109 |

Gradient boosting takes accuracy by one point and loses on everything else, including a
calibration error 58% worse that fails the <0.10 target outright. Since the output is shown to
a user as a probability, calibration outranks which side of 0.5 it lands on. **Logistic
regression ships.**

### Parameter recovery

Because the generator's mechanisms were written down, the fitted coefficients can be checked
against them. Every sign matches:

```
progress_ratio            +2.098   further along ⇒ more likely            ✓
required_rate_multiple    -1.919   more catching up needed ⇒ less likely  ✓
duration_days             -1.048   longer goals fail more                 ✓
time_elapsed_ratio        -0.975   later with the same progress ⇒ worse   ✓
competing_goals           -0.785   dilution, encoded at 0.08 per goal     ✓
cat_FINANCE               +0.334   easiest category, encoded 1.10         ✓
cat_FITNESS               -0.284   hardest category, encoded 0.80         ✓
```

The category ordering recovers its endpoints exactly. The three middle categories land within
±0.06 of one another and swap relative order — their true effects are close enough that 886
goals cannot separate them, which is the honest reading rather than a failure.

---

## 7. Model 2 — habit failure

18,240 prediction-days across 120 users, again split by user. Predicts whether a streak
breaks within seven days.

> **Why precision, not accuracy or recall.** This model drives a proactive nudge — "you look
> like you're about to slip." A false positive spends the user's attention and, repeated,
> teaches them to ignore the app. A false negative costs almost nothing: they simply don't get
> a message they may not have needed. So the operating metric is **precision among the alerts
> you would actually send**, not overall accuracy.

| Model | Accuracy | AUC | Brier | ECE | P@5% | P@10% |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Base rate | 77.6% | 0.500 | 0.185 | 0.105 | 2.2% | 11.0% |
| Logistic regression | 83.9% | 0.798 | 0.124 | 0.024 | 97.4% | 80.5% |
| **Gradient boosting** ← ships | **84.6%** | 0.783 | **0.122** | **0.014** | **99.1%** | **84.4%** |

Against a test-set break rate of 22.4%, **99.1% precision on the riskiest 5% of days** means
almost every nudge would have been warranted. That is the number that decides whether this
feature is worth shipping.

> **The most useful cross-model result.** Gradient boosting wins here on nearly everything,
> having lost on the goal model. So "the simpler model wins" would have been the wrong lesson
> to draw from Model 1. The right one is that model choice must be *measured per problem*, on
> the metric that matches how the output is used — and that comparing on accuracy alone would
> have picked the wrong model in one of these two cases.

### Why coefficients were discarded here

The fitted logistic coefficients showed `adherence_14d` at `+1.74` against `adherence_7d` at
`−1.53`, and crushed `current_streak` to roughly zero. That is not a finding about habits; it
is multicollinearity. The three adherence windows are nested over the same days, so the fit
splits their shared signal into large opposing weights and starves genuinely predictive
features.

Reporting those numbers would have implied the model ignores streak length, which it does not.
Permutation importance on held-out data — how much the score degrades when a feature is
shuffled — survives collinearity and gives the real picture:

```
missed_logs_30d        0.0330   ███████
mean_score_7d          0.0232   █████
mean_sleep_7d          0.0187   ████
mean_exercise_7d       0.0181   ████
score_volatility_7d    0.0165   ███
```

The strongest single signal is **missed logs** — people stop recording before they stop
trying, so the gap in the record precedes the break in the habit. That is deliberately built
into the generator as informative missingness, and it is the kind of relationship that would
be lost by imputing missing days as zeros.

---

## 8. Robustness of the assumptions

Training on generated data means every result rests on beliefs written into the generator:
that fitness goals are harder than finance goals, that competing goals dilute effort, that
adherence decays. Those beliefs are explicit constants, so they can be varied and the whole
pipeline re-run. Each mechanism was swept across a range — **36 configurations** in total.

The question is not "is the model good" but "does the conclusion survive if the assumption is
wrong?"

| Assumption varied | Range | AUC swing |
| :--- | ---: | ---: |
| Abandoned-goal share | 0 → 35% | 0.057 |
| Competition penalty per goal | 0 → 0.16 | 0.056 |
| Disruption severity | 0 → 0.70 | 0.051 |
| Disruption probability | 0 → 85% | 0.050 |
| Adherence half-life | 25 d → none | 0.034 |
| Deadline sprint strength | 0 → 1.4 | 0.018 |
| **Category effort ordering** | ordered / flat / reversed | 0.012 |
| Manually-tracked share | 0 → 60% | 0.003 |

> **Result.** Across all 36 configurations **AUC stays within 0.893–0.962** and **ECE within
> 0.041–0.106**, and logistic regression calibrated better than gradient boosting in **35 of
> 36**. The single exception sets adherence decay to effectively infinite — adherence never
> fading at all — which is not a plausible model of behaviour.

The most useful distinction the sweep draws is between **class balance** and
**discrimination**. Completion rate is highly sensitive, moving from 26.7% to 66.4%. AUC barely
moves. So the assumptions strongly determine *how many* goals succeed, and barely determine
*whether the model can tell which ones will*.

Two beliefs turn out to carry almost nothing. Reversing the category difficulty ordering
entirely — asserting fitness goals are the *easiest* — changes AUC by 0.001. Varying the
manually-tracked share from 0 to 60% changes it by 0.003.

This supports saying the conclusions are not an artefact of any single assumption. It does not
show the models work on real people: every configuration is still synthetic, and sweeping a
wrong model still yields a wrong model. The sweep is also one-at-a-time; interactions would
need a Sobol analysis.

---

## 9. Serving, and knowing when to refuse

The goal-completion model is served through the application. Its artifact carries the model,
the feature names, **and the 1st–99th percentile range of every feature seen in training**. At
request time the service rebuilds the feature vector from a real goal and checks it against
those ranges.

It returns no probability — and a specific reason instead — when the goal is under three days
old, when the deadline has passed, or when any feature falls materially outside the trained
range.

> **Refusing is the accurate answer, not a limitation.** A linear model extrapolates past its
> training range silently and with high confidence: it computes `w·x + b` and squashes the
> result regardless of whether `x` resembles anything it has seen. When the model has no basis
> for an input, saying so is correct behaviour. The interface shows the reason in place of a
> figure, so the refusal is legible rather than an error state.

The same reasoning shapes the interface elsewhere. Predicted values render in a colour the
design system reserves for model output, distinct from measured figures — on goal cards, and
as dashed projection lines continuing the solid recorded history on the savings and expense
charts.

---

## 10. Engineering rigour: what broke

Nine defects were found and fixed. They are reported because the pattern connecting them is
the substantive finding: **every one was invisible to the checks that were passing at the
time.**

### 99.8% on a goal at 30% progress — *out-of-distribution*

Offline evaluation was excellent — AUC 0.978. The first real goal returned 99.8% a third of the
way to its deadline. Not an arithmetic bug: `contribution_count` was 0, and training had only
ever seen 3–105, because a real goal can be tracked with no linked transactions.

**Fix:** feature ranges ship inside the artifact; the service refuses out-of-range inputs.
**Why it could not have been caught offline:** a held-out test set is drawn from the training
distribution, so it contains no out-of-distribution inputs by construction. No amount of
careful splitting would have surfaced this.

### Predictions ran backwards — *train/serve mismatch*

The generator modelled daily accrual with partial logging, so training-time `progress_ratio`
reflected a fraction of true progress while the served feature reflected all of it. Goals
*behind* pace scored higher than goals ahead of them.

**Fix:** progress became a cumulative series independent of the contribution log, matching how
the application's `current_value` actually behaves.

### Three of four real goals refused — *narrow feature space*

With the guard in place, most real goals were rejected. The guard was right; the training data
was too narrow — durations drawn from six fixed values topping out at 180 days against a real
330-day goal, and prediction snapshots only between 25% and 65% of a goal's life against a real
one at 76%.

**Fix:** continuous durations from 14 to 400 days, snapshots across 5–95%, plus abandoned and
manually-tracked goals. Coverage tests now fail if the space narrows again.

### Study and habit goals reported zero activity — *silent feature corruption*

The serving path counted contributions from financial records only. Study and habit goals draw
progress from sessions and logs through the same mechanism, so an actively-worked study goal
reported `contribution_count = 0` — which the model reads as abandoned.

**Fix:** count all three sources. **Why it hid:** finance goals were unaffected, and every test
written until then used a finance goal.

### Half the interface rendered in default colours — *design system*

The theme defined only three shades per colour family while the interface used twenty more.
Tailwind resolves an undefined shade to its own default silently — so every input focus ring,
every primary button ring, every form error border and the KPI accent bars were rendering
outside the design system.

**Fix:** all shades defined and contrast-verified; a guard script now fails the build on an
undefined shade. **Why it hid:** a search for stale hex values passes cleanly — the defect was a
missing definition, which produces no error at all.

### Sign-up was unreachable by direct navigation — *user-facing*

The auth context probes the session on mount for every route; with no session that returns 401,
and the interceptor redirected any 401 to the login page. Opening the sign-up or password-reset
page from a link, bookmark or refresh therefore bounced. Password reset is used by definition by
people who cannot log in.

**Fix:** a public-route allowlist plus an opt-out for the session probe, where a 401 is a valid
answer rather than an expired session. **Why it hid:** clicking through from the login page never
remounts the context, so the only path anyone tested worked fine.

### The others

Goals never auto-completing (§4); projections drawn identically to recorded data on one chart,
making estimates indistinguishable from measurements; hardcoded currency symbols showing dollars
to a rupee account; a legacy type mismatch that made one account unloadable; and an endpoint
returning 500 on every call, unnoticed because the frontend read the same data elsewhere.

> **The pattern.** Lint, unit tests and offline metrics were passing throughout. Each defect
> surfaced only from exercising the system somewhere it had not been exercised before — a real
> goal instead of a constructed one, a study goal instead of a finance goal, a direct URL
> instead of a click-through, a rupee account instead of a dollar one. **The checks were not
> weak; they were aimed at the paths already known to work.**

Full detail on each, including the fix as landed, is in [`REMEDIATION_PLAN.md`](REMEDIATION_PLAN.md).

---

## 11. Limitations

1. **Both models are trained on synthetic data.** The results demonstrate the implementation is
   correct — the models recover signal that genuinely exists, are calibrated, and beat their
   baselines. They do *not* establish that either predicts real human behaviour. Only real
   longitudinal data can, and it is now accruing.
2. **The generators encode assumptions about people.** Quantified in §8 and robust across a wide
   sweep, but assumptions nonetheless, and the sweep is one-at-a-time rather than factorial.
3. **Discrimination is likely optimistic.** The sweep never drove AUC below 0.893; real data
   almost certainly would, since a simulated process is more regular than a life.
4. **No temporal validation.** Split by user, not by time. A production system should also
   confirm the model holds on periods after training.
5. **Calibration measured once.** It should be monitored continuously against realised outcomes,
   with drift widening intervals rather than passing unnoticed.
6. **The assistant has no tool access.** It is grounded on a summary of the twin state, so it
   answers summary-level questions and cannot retrieve or compute. It will say so rather than
   invent, but its ceiling is low.
7. **Single-user scale.** Rate limiting is in-process and would need shared state behind more
   than one instance.

---

## 12. Future work

An architecture review produced a phased plan; most of it was deliberately not built, and the
reasoning matters more than the list. The full plan is
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

| Phase | Why not yet |
| :--- | :--- |
| **Event sourcing** with bitemporal timestamps | The foundation for reconstructing past state and detecting drift. Invisible to a user, so it lost to work that could be demonstrated. |
| **Tool-calling assistant** | The largest capability gain available — the engines exist, it is mostly wiring — but too large to land safely in the time remaining. |
| **Causal DAG and Monte Carlo simulation** | Answering "what if I changed X" requires causal structure, not correlation. With one person's observational data this is not reliably solvable; it needs n-of-1 experiments. |
| **Decision and optimization engine** | Depends on the causal layer. Its most valuable output would be proving a set of goals is *infeasible* — usually the real reason someone falls behind. |
| **Hierarchical personalization** | Turns the hardcoded thresholds into per-user learned parameters, starting from population priors. Needs real longitudinal data. |
| **Reinforcement learning** | *Deliberately rejected.* One episode per day gives ~365 samples a year against the 10³–10⁶ RL needs; the dynamics are non-stationary; and exploration means deliberately giving a real person worse advice. Contextual bandits over recommendation variants are the defensible subset. |

The nearest-term item is unglamorous: **capture more labels.** Every day the system runs adds
resolved goals and habit sequences, and real data is the only thing that converts these results
from "the pipeline works" into "the model works."

---

## 13. Conclusion

The system does what it set out to do: it tracks three domains, computes analytics over them,
and makes two predictions that are calibrated, beat their baselines, and know when to decline.
It is verified end-to-end — 322 tests, every page and endpoint exercised against a staging copy
of real data.

The more durable outcomes are methodological.

**Calibration, not accuracy, is the metric that matters when the output is a probability.**
Judged on accuracy alone, gradient boosting would have been chosen for goal completion — where
its calibration error is 58% worse and fails the target. Judged the same way, logistic
regression would have been chosen for habits. Measuring the right thing changed the decision in
both directions.

**Offline evaluation has a structural blind spot.** A held-out test set is drawn from the
training distribution, so it cannot contain the inputs that break a model in production. The
99.8% prediction was found by connecting the model to one real goal — not by any amount of
additional cross-validation.

**Stating what the numbers do not establish is part of the result.** These models are trained on
generated data. That bounds the claim to "the implementation is correct," and the sensitivity
analysis is what makes even that claim defensible. Saying so is not a weakness in the work;
leaving it unsaid would have been.

---

## Reproducing the figures

All figures reproduce deterministically from a fixed seed. From `backend_api/`:

```bash
# Model 1 — goal completion (§6)
python3 scripts/generate_synthetic_users.py
python3 scripts/train_goal_model.py

# Model 2 — habit failure (§7)
python3 scripts/generate_synthetic_habits.py
python3 scripts/train_habit_failure_model.py

# Robustness sweep (§8) — 36 configurations, slow
python3 scripts/sensitivity_analysis.py
```

Metrics land in `backend_api/data/model_eval/` as JSON alongside reliability diagrams and
precision-at-k charts.
