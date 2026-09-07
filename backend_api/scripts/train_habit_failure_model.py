"""
scripts/train_habit_failure_model.py — Trains and evaluates the habit-failure model.

Predicts: will this user's habit streak break within the next 7 days?

WHY PRECISION MATTERS MORE THAN RECALL HERE
Unlike the goal-completion model, this one is meant to drive a proactive nudge —
"you look like you're about to slip." A false positive spends the user's
attention and, repeated, teaches them to ignore the app. A false negative costs
almost nothing: they simply don't get a nudge they might not have needed. So the
headline operating metric is precision at the top of the ranking, not accuracy
or recall, and the report below shows precision@k for the alerts you would
actually send.

Calibration still matters for the same reason it does elsewhere: the output is a
probability, and a probability that does not mean what it says is worse than no
number.

Method otherwise mirrors train_goal_model.py — split by user (never by row,
since days from one person share that person's habits), base-rate baseline,
Brier and ECE alongside AUC.

Usage (from backend_api/):
    python3 scripts/generate_synthetic_habits.py    # first
    python3 scripts/train_habit_failure_model.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.inspection import permutation_importance
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

LABEL = "breaks_within_7d"
DROP = ["user_id", "day_index", LABEL]


def expected_calibration_error(y_true, y_prob, bins=10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (y_prob > lo) & (y_prob <= hi)
        if m.any():
            ece += m.mean() * abs(y_true[m].mean() - y_prob[m].mean())
    return float(ece)


def precision_at_k(y_true, y_prob, k_frac: float) -> tuple[float, int]:
    """Precision among the highest-risk k fraction — the alerts you would send."""
    k = max(1, int(len(y_prob) * k_frac))
    idx = np.argsort(y_prob)[::-1][:k]
    return float(y_true[idx].mean()), k


def reliability_points(y_true, y_prob, bins=10):
    edges = np.linspace(0.0, 1.0, bins + 1)
    xs, ys = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (y_prob > lo) & (y_prob <= hi)
        if m.sum() >= 20:
            xs.append(y_prob[m].mean()); ys.append(y_true[m].mean())
    return np.array(xs), np.array(ys)


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the habit-failure model.")
    ap.add_argument("--data", default="data/synthetic/habits.csv")
    ap.add_argument("--out", default="data/model_eval")
    ap.add_argument("--seed", type=int, default=20260908)
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    X = df.drop(columns=DROP)
    y = df[LABEL].to_numpy()
    groups = df["user_id"].to_numpy()
    names = list(X.columns)

    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25,
                                   random_state=args.seed).split(X, y, groups))
    X_tr, X_te = X.iloc[tr].to_numpy(float), X.iloc[te].to_numpy(float)
    y_tr, y_te = y[tr], y[te]

    print(f"{len(df):,} prediction-days, {df.user_id.nunique()} users")
    print(f"  train: {len(y_tr):>6,} days / {len(set(groups[tr])):>3} users   break rate {y_tr.mean():.1%}")
    print(f"  test : {len(y_te):>6,} days / {len(set(groups[te])):>3} users   break rate {y_te.mean():.1%}")
    assert not (set(groups[tr]) & set(groups[te])), "user leaked across the split"
    print("  ✓ no user appears in both splits\n")

    dummy = DummyClassifier(strategy="prior").fit(X_tr, y_tr)
    p_base = dummy.predict_proba(X_te)[:, 1]
    base_acc = float(((p_base >= 0.5) == y_te).mean())

    logreg = Pipeline([("s", StandardScaler()),
                       ("c", LogisticRegression(max_iter=2000, random_state=args.seed))]).fit(X_tr, y_tr)
    p_lr = logreg.predict_proba(X_te)[:, 1]

    gbm = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                         max_leaf_nodes=15, random_state=args.seed).fit(X_tr, y_tr)
    p_gb = gbm.predict_proba(X_te)[:, 1]

    rows = []
    for name, p in [("baseline (base rate)", p_base), ("logistic regression", p_lr),
                    ("gradient boosting", p_gb)]:
        acc = float(((p >= 0.5) == y_te).mean())
        rows.append({
            "model": name, "accuracy": acc,
            "lift_over_baseline_pp": (acc - base_acc) * 100,
            "roc_auc": float(roc_auc_score(y_te, p)) if len(set(y_te)) > 1 else float("nan"),
            "brier": float(brier_score_loss(y_te, p)),
            "ece": expected_calibration_error(y_te, p),
            "precision_at_5pct": precision_at_k(y_te, p, 0.05)[0],
            "precision_at_10pct": precision_at_k(y_te, p, 0.10)[0],
        })

    print(f"{'model':<24}{'acc':>7}{'lift':>9}{'AUC':>7}{'Brier':>8}{'ECE':>7}{'P@5%':>8}{'P@10%':>8}")
    print("-" * 78)
    for r in rows:
        auc = "  n/a" if np.isnan(r["roc_auc"]) else f"{r['roc_auc']:>6.3f}"
        print(f"{r['model']:<24}{r['accuracy']:>6.1%}{r['lift_over_baseline_pp']:>+8.1f}pp{auc}"
              f"{r['brier']:>8.3f}{r['ece']:>7.3f}{r['precision_at_5pct']:>8.1%}{r['precision_at_10pct']:>8.1%}")

    print(f"\n  Base rate on the test set is {y_te.mean():.1%}, so precision above that is real lift.")
    print("  P@5% is what matters operationally: of the riskiest 5% of days — the ones")
    print("  you would actually nudge on — how many genuinely broke.\n")

    coefs = dict(zip(names, logreg.named_steps["c"].coef_[0]))

    # Raw coefficients are NOT a valid attribution here. adherence_7d/14d/30d are
    # strongly collinear by construction — each is a longer window over the same
    # days — so the fit splits their shared signal into large opposing weights
    # (+1.74 against -1.53 in one run) and starves genuinely predictive features
    # like current_streak down to ~0. Permutation importance measures how much
    # the held-out score actually degrades when a feature is shuffled, which
    # survives collinearity in a way single coefficients do not.
    print("feature importance (permutation, on held-out data)")
    perm = permutation_importance(gbm, X_te, y_te, n_repeats=8,
                                  random_state=args.seed, scoring="roc_auc")
    order = np.argsort(perm.importances_mean)[::-1]
    importances = {}
    for i in order[:8]:
        importances[names[i]] = float(perm.importances_mean[i])
        bar = "█" * max(1, round(perm.importances_mean[i] * 200))
        print(f"    {names[i]:<26}{perm.importances_mean[i]:>7.4f} ± {perm.importances_std[i]:.4f}  {bar}")

    print("\n  Raw logistic coefficients are omitted deliberately: the three adherence")
    print("  windows are collinear by construction, so individual weights are unstable")
    print("  and uninterpretable even though the model as a whole is sound.")

    # ── charts ───────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot([0, 1], [0, 1], "--", color="#8C8580", lw=1, label="perfect calibration")
    for p, lbl, col in [(p_lr, "logistic regression", "#0F766E"), (p_gb, "gradient boosting", "#8B4B8A")]:
        xs, ys = reliability_points(y_te, p)
        ax1.plot(xs, ys, "o-", color=col, label=lbl, lw=1.8, ms=5)
    ax1.set_xlabel("predicted probability of a break")
    ax1.set_ylabel("observed break rate")
    ax1.set_title("Reliability diagram — habit failure")
    ax1.legend(frameon=False, fontsize=9); ax1.set_xlim(0, 1); ax1.set_ylim(0, 1); ax1.grid(alpha=.15)

    best = p_lr if rows[1]["ece"] <= rows[2]["ece"] else p_gb
    ks = np.linspace(0.02, 0.5, 25)
    ax2.plot(ks * 100, [precision_at_k(y_te, best, k)[0] for k in ks], color="#0F766E", lw=2)
    ax2.axhline(y_te.mean(), ls="--", color="#8C8580", lw=1, label=f"base rate ({y_te.mean():.0%})")
    ax2.set_xlabel("alert on the riskiest k% of days")
    ax2.set_ylabel("precision")
    ax2.set_title("Precision at k — nudge quality")
    ax2.legend(frameon=False, fontsize=9); ax2.grid(alpha=.15); ax2.set_ylim(0, 1)

    fig.tight_layout()
    chart = out_dir / "habit_failure_evaluation.png"
    fig.savefig(chart, dpi=150)

    (out_dir / "habit_failure_metrics.json").write_text(json.dumps({
        "n_rows": len(df), "n_users": int(df.user_id.nunique()),
        "test_break_rate": float(y_te.mean()),
        "results": rows,
        "logistic_coefficients": {k: float(v) for k, v in coefs.items()},
        "permutation_importance": importances,
        "note": ("Coefficients are collinear (adherence 7/14/30d overlap); "
                 "permutation importance is the valid attribution."),
    }, indent=2))

    print(f"\nwrote {chart}")
    print(f"wrote {out_dir / 'habit_failure_metrics.json'}")
    print("\nNOTE: synthetic data. This validates the implementation, not the")
    print("model's fidelity to real behaviour.")


if __name__ == "__main__":
    main()
