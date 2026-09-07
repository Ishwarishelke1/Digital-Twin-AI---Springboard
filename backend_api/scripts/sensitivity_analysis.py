"""
scripts/sensitivity_analysis.py — How much do the generator's assumptions drive
the model's results?

The goal-completion model is trained on synthetic data, so every number it
produces rests on assumptions written into scripts/generate_synthetic_users.py:
that fitness goals are harder than finance goals, that competing goals dilute
effort, that adherence decays, that people sprint before deadlines. Those are
plausible, and they are deliberately explicit — but they are assumptions, not
findings.

This sweeps each one across a range, regenerates the data, retrains, and
re-measures. The question it answers is not "is the model good" but "does the
conclusion survive if the assumption is wrong?" A metric that barely moves under
a large change to a parameter is not resting on that parameter. A metric that
swings is, and the report should say so.

Method mirrors train_goal_model.py: same features, same split by user (never by
row), same metrics. Kept self-contained rather than importing that script, since
it is a CLI entry point rather than a library.

Usage (from backend_api/):
    python3 scripts/sensitivity_analysis.py
    python3 scripts/sensitivity_analysis.py --users 150 --out data/model_eval
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_spec = importlib.util.spec_from_file_location(
    "generate_synthetic_users", Path(__file__).resolve().parent / "generate_synthetic_users.py"
)
gen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gen
_spec.loader.exec_module(gen)

LABEL = "completed_by_deadline"
DROP = ["goal_id", "user_id", LABEL]


def ece(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (y_prob > lo) & (y_prob <= hi)
        if m.any():
            total += m.mean() * abs(y_true[m].mean() - y_prob[m].mean())
    return float(total)


def evaluate(users: int, seed: int) -> dict:
    """Generate, split by user, fit both models, return metrics."""
    rows, meta = gen.generate(users=users, seed=seed)
    df = pd.DataFrame(rows)

    # A sweep can push completion to an extreme where a split has one class and
    # AUC is undefined. Report it rather than crashing.
    if df[LABEL].nunique() < 2:
        return {"completion": float(df[LABEL].mean()), "degenerate": True}

    X = pd.get_dummies(df.drop(columns=DROP), columns=["category"], prefix="cat", dtype=float)
    y = df[LABEL].to_numpy()
    groups = df["user_id"].to_numpy()

    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed).split(X, y, groups))
    X_tr, X_te = X.iloc[tr].to_numpy(float), X.iloc[te].to_numpy(float)
    y_tr, y_te = y[tr], y[te]

    if len(set(y_te)) < 2 or len(set(y_tr)) < 2:
        return {"completion": float(df[LABEL].mean()), "degenerate": True}

    lr = Pipeline([("s", StandardScaler()), ("c", LogisticRegression(max_iter=2000, random_state=seed))]).fit(X_tr, y_tr)
    p_lr = lr.predict_proba(X_te)[:, 1]
    gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
                                        random_state=seed).fit(X_tr, y_tr)
    p_gb = gb.predict_proba(X_te)[:, 1]

    base_acc = max(y_te.mean(), 1 - y_te.mean())
    return {
        "completion": float(df[LABEL].mean()),
        "degenerate": False,
        "auc": float(roc_auc_score(y_te, p_lr)),
        "ece": ece(y_te, p_lr),
        "brier": float(brier_score_loss(y_te, p_lr)),
        "acc": float(((p_lr >= 0.5) == y_te).mean()),
        "lift_pp": float((((p_lr >= 0.5) == y_te).mean() - base_acc) * 100),
        # Does the headline conclusion — logistic calibrates better than GBM —
        # survive this configuration?
        "lr_beats_gbm_on_ece": bool(ece(y_te, p_lr) < ece(y_te, p_gb)),
    }


# (label, attribute, values). Each sweep varies one mechanism, holding the rest.
SWEEPS = [
    ("Disruption probability", "DISRUPTION_PROBABILITY", [0.0, 0.25, 0.45, 0.65, 0.85]),
    ("Disruption severity", "DISRUPTION_EFFORT_MULTIPLIER", [0.0, 0.15, 0.40, 0.70]),
    ("Competition penalty / goal", "COMPETITION_PENALTY", [0.0, 0.04, 0.08, 0.16]),
    ("Adherence half-life (days)", "ADHERENCE_HALF_LIFE_DAYS", [25.0, 75.0, 200.0, 1e6]),
    ("Deadline sprint strength", "SPRINT_STRENGTH", [0.0, 0.35, 0.7, 1.4]),
    ("Abandoned-goal share", "ABANDONED_GOAL_PROBABILITY", [0.0, 0.09, 0.18, 0.35]),
    ("Manually-tracked share", "MANUAL_TRACKING_PROBABILITY", [0.0, 0.15, 0.30, 0.60]),
    ("Effort intercept", "EFFORT_INTERCEPT", [0.75, 0.85, 0.95, 1.10]),
]

# Category effort is a dict, so it gets its own sweep: ordered (as encoded),
# flat (no category effect at all), and reversed (the opposite belief).
ORDERED = dict(gen.CATEGORY_EFFORT)
FLAT = {k: 1.0 for k in ORDERED}
REVERSED = dict(zip(ORDERED.keys(), reversed(list(ORDERED.values()))))


def main() -> None:
    ap = argparse.ArgumentParser(description="Sensitivity of model results to generator assumptions.")
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20260906)
    ap.add_argument("--out", default="data/model_eval")
    args = ap.parse_args()

    originals = {attr: getattr(gen, attr) for _, attr, _ in SWEEPS}
    originals["CATEGORY_EFFORT"] = copy.deepcopy(gen.CATEGORY_EFFORT)

    base = evaluate(args.users, args.seed)
    print(f"baseline (as shipped)   completion {base['completion']:.1%}   "
          f"AUC {base['auc']:.3f}   ECE {base['ece']:.3f}   lift {base['lift_pp']:+.1f}pp\n")

    results = {"baseline": base, "sweeps": {}}
    swings = []

    for label, attr, values in SWEEPS:
        print(f"{label}   (shipped: {originals[attr]:g})")
        print(f"  {'value':>10}{'completion':>13}{'AUC':>8}{'ECE':>8}{'lift':>9}   LR>GBM")
        rows = []
        for v in values:
            setattr(gen, attr, v)
            r = evaluate(args.users, args.seed)
            r["value"] = v
            rows.append(r)
            shown = "1e6" if v >= 1e5 else f"{v:g}"
            if r["degenerate"]:
                print(f"  {shown:>10}{r['completion']:>12.1%}   (degenerate — one class only)")
            else:
                mark = "✓" if r["lr_beats_gbm_on_ece"] else "✗"
                print(f"  {shown:>10}{r['completion']:>12.1%}{r['auc']:>8.3f}"
                      f"{r['ece']:>8.3f}{r['lift_pp']:>+8.1f}pp     {mark}")
        setattr(gen, attr, originals[attr])
        results["sweeps"][label] = rows

        aucs = [r["auc"] for r in rows if not r["degenerate"]]
        if len(aucs) > 1:
            swings.append((label, max(aucs) - min(aucs)))
        print()

    # ── category effort ──────────────────────────────────────────────────────
    print("Category effort ordering")
    print(f"  {'variant':>10}{'completion':>13}{'AUC':>8}{'ECE':>8}{'lift':>9}   LR>GBM")
    cat_rows = []
    for name, mapping in [("ordered", ORDERED), ("flat", FLAT), ("reversed", REVERSED)]:
        gen.CATEGORY_EFFORT = mapping
        r = evaluate(args.users, args.seed)
        r["value"] = name
        cat_rows.append(r)
        mark = "✓" if r.get("lr_beats_gbm_on_ece") else "✗"
        print(f"  {name:>10}{r['completion']:>12.1%}{r['auc']:>8.3f}{r['ece']:>8.3f}"
              f"{r['lift_pp']:>+8.1f}pp     {mark}")
    gen.CATEGORY_EFFORT = originals["CATEGORY_EFFORT"]
    results["sweeps"]["Category effort ordering"] = cat_rows
    aucs = [r["auc"] for r in cat_rows]
    swings.append(("Category effort ordering", max(aucs) - min(aucs)))

    # ── summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("AUC swing by assumption (largest first) — how much the result rests")
    print("on each belief being right:\n")
    for label, swing in sorted(swings, key=lambda kv: -kv[1]):
        bar = "█" * max(1, round(swing * 120))
        print(f"  {label:<30}{swing:.3f}  {bar}")

    all_auc = [r["auc"] for rows in results["sweeps"].values() for r in rows if not r.get("degenerate")]
    all_ece = [r["ece"] for rows in results["sweeps"].values() for r in rows if not r.get("degenerate")]
    held = sum(1 for rows in results["sweeps"].values() for r in rows
               if not r.get("degenerate") and r["lr_beats_gbm_on_ece"])
    total = sum(1 for rows in results["sweeps"].values() for r in rows if not r.get("degenerate"))

    print(f"\nAcross all {total} configurations:")
    print(f"  AUC   {min(all_auc):.3f} – {max(all_auc):.3f}")
    print(f"  ECE   {min(all_ece):.3f} – {max(all_ece):.3f}")
    print(f"  logistic calibrated better than gradient boosting in {held}/{total} "
          f"({held/total:.0%}) of configurations")

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "sensitivity.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out / 'sensitivity.json'}")


if __name__ == "__main__":
    main()
