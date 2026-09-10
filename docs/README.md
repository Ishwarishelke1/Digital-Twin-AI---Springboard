# Documentation

Everything here describes the project in depth. Start with the root
[`README.md`](../README.md) for setup, and [`CLAUDE.md`](../CLAUDE.md) for code conventions —
both stay at the repository root because that is where a new contributor and the tooling
look for them.

| File | Covers | Describes |
| :--- | :--- | :--- |
| [`CAPSTONE_REPORT.md`](CAPSTONE_REPORT.md) | The project written up end to end: architecture, both ML models, results, the defects found, limitations | Current state |
| [`TEST_PLAN.md`](TEST_PLAN.md) | A plan to test every module, route, page and collection — and the deployability verdict it exists to establish | **Phase 0 done, Phases 1–3 in progress** |
| [`REMEDIATION_PLAN.md`](REMEDIATION_PLAN.md) | Defects found by auditing the codebase, and how each was fixed | Current state |
| [`SKILLS.md`](SKILLS.md) | The design-review workflow frontend changes go through | Current state |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Architecture roadmap — event sourcing, memory, causal reasoning, simulation, decision engine | **Mostly planned, not built** |
| [`DESIGN.md`](DESIGN.md) | The "Field Notes" visual design system | **Superseded** — see note below |

## Two documents that are not descriptions of today's code

**`IMPLEMENTATION_PLAN.md`** is a forward-looking plan derived from an engineering design
review. Two parts of it have since been built — the staging database (Phase 0.1) and the
goal-completion model (Model 2, all three steps) — and a second model (habit failure) was added
beyond it. Everything else is unbuilt and marked as such. Read it as a plan, never as a
description of how the system behaves.

**`DESIGN.md`** documents "Field Notes", the visual identity the app carried before the
ground-up redesign. The app now runs on **"Studio"** — warm paper, Fraunces display serif, Inter
body, JetBrains Mono for every figure — defined as design tokens in `frontend/src/index.css`.
The file is kept for the reasoning it records about spacing, iconography and component states,
much of which carried forward; its specific colour and type values did not. `SKILLS.md` covers
the workflow the redesign went through.

Where any document here disagrees with the code or `CLAUDE.md`, the code wins.
