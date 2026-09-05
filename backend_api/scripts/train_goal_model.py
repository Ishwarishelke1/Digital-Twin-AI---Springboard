"""
scripts/train_goal_model.py — Trains and evaluates the goal-completion model.

This is Model 2, step 3 in IMPLEMENTATION_PLAN.md. Steps 1 (capture the label,
ActiveGoal.completed_at) and 2 (generate_synthetic_users.py) must have run first.

WHAT IS BEING MEASURED, AND WHY IT IS NOT ACCURACY
The output is a probability — "this goal has a 61% chance of completing". For
that to be useful it must be *calibrated*: of all the goals predicted at 60-70%,
roughly 60-70% should actually complete. Accuracy cannot detect miscalibration.
A model that says 38% for every goal has decent accuracy on this dataset and is
useless. So the headline metrics here are Brier score and expected calibration
error, with a reliability diagram; accuracy is reported only against the
base-rate baseline, which any model must beat to justify existing.

SPLITTING BY USER, NOT BY ROW
Goals belonging to one user share that user's latent diligence. A random row
split puts some of a user's goals in train and others in test, so the model can
learn the individual rather than the pattern — scores come out inflated and the
model fails on anyone new. Splitting by user is the honest test: every user in
the test set is someone the model has never seen.

WHAT THIS DOES AND DOES NOT ESTABLISH
Trained on synthetic data, good numbers here show the pipeline is correct — the
model recovers signal that genuinely exists, is calibrated, and beats a
baseline. They do NOT show the model predicts real human behaviour. Only real
longitudinal data can establish that.

Usage (from backend_api/):
    python3 scripts/generate_synthetic_users.py     # first
    python3 scripts/train_goal_model.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

LABEL = "completed_by_deadline"
DROP = ["goal_id", "user_id", LABEL]


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10) -> float:
    """Mean gap between predicted confidence and observed frequency, weighted by
    bin population. This is the number that says whether a probability means what
    it claims — the design doc's target is < 0.10."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (y_prob > lo) & (y_prob <= hi)
        if not mask.any():
            continue
        ece += mask.mean() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(ece)


def reliability_points(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10):
    edges = np.linspace(0.0, 1.0, bins + 1)
    xs, ys, ns = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (y_prob > lo) & (y_prob <= hi)
        if mask.sum() >= 5:  # ignore near-empty bins; they are noise, not signal
            xs.append(y_prob[mask].mean())
            ys.append(y_true[mask].mean())
            ns.append(int(mask.sum()))
    return np.array(xs), np.array(ys), ns


def evaluate(name: str, y_true: np.ndarray, y_prob: np.ndarray, baseline_acc: float) -> dict:
    y_pred = (y_prob >= 0.5).astype(int)
    acc = float((y_pred == y_true).mean())
    return {
        "model": name,
        "accuracy": acc,
        "lift_over_baseline_pp": (acc - baseline_acc) * 100,
        "roc_auc": float(roc_auc_score(y_true, y_prob)) if len(set(y_true)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "ece": expected_calibration_error(y_true, y_prob),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the goal-completion model.")
    parser.add_argument("--data", default="data/synthetic/goals.csv")
    parser.add_argument("--out", default="data/model_eval")
    parser.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()

    df = pd.read_csv(args.data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # dtype=float: get_dummies yields booleans by default, and .quantile() on a
    # boolean column raises rather than returning 0/1.
    X = pd.get_dummies(df.drop(columns=DROP), columns=["category"], prefix="cat", dtype=float)
    y = df[LABEL].to_numpy()
    groups = df["user_id"].to_numpy()
    feature_names = list(X.columns)

    # Split by user — see the module docstring.
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=args.seed)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_tr, X_te = X.iloc[train_idx].to_numpy(float), X.iloc[test_idx].to_numpy(float)
    y_tr, y_te = y[train_idx], y[test_idx]

    print(f"{len(df)} goals, {df.user_id.nunique()} users")
    print(f"  train: {len(y_tr):>4} goals / {len(set(groups[train_idx])):>3} users   "
          f"completion {y_tr.mean():.1%}")
    print(f"  test : {len(y_te):>4} goals / {len(set(groups[test_idx])):>3} users   "
          f"completion {y_te.mean():.1%}")
    assert not (set(groups[train_idx]) & set(groups[test_idx])), "user leaked across the split"
    print("  ✓ no user appears in both splits\n")

    # ── baseline ─────────────────────────────────────────────────────────────
    dummy = DummyClassifier(strategy="prior").fit(X_tr, y_tr)
    base_prob = dummy.predict_proba(X_te)[:, 1]
    baseline_acc = float(((base_prob >= 0.5).astype(int) == y_te).mean())

    results = [evaluate("baseline (base rate)", y_te, base_prob, baseline_acc)]

    # ── models ───────────────────────────────────────────────────────────────
    logreg = Pipeline([
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, random_state=args.seed)),
    ]).fit(X_tr, y_tr)
    p_lr = logreg.predict_proba(X_te)[:, 1]
    results.append(evaluate("logistic regression", y_te, p_lr, baseline_acc))

    gbm = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=15, random_state=args.seed
    ).fit(X_tr, y_tr)
    p_gbm = gbm.predict_proba(X_te)[:, 1]
    results.append(evaluate("gradient boosting", y_te, p_gbm, baseline_acc))

    # ── report ───────────────────────────────────────────────────────────────
    print(f"{'model':<24}{'acc':>7}{'lift':>8}{'AUC':>7}{'Brier':>8}{'ECE':>7}")
    print("-" * 61)
    for r in results:
        auc = "   n/a" if np.isnan(r["roc_auc"]) else f"{r['roc_auc']:>6.3f}"
        print(f"{r['model']:<24}{r['accuracy']:>6.1%}{r['lift_over_baseline_pp']:>+7.1f}pp"
              f"{auc}{r['brier']:>8.3f}{r['ece']:>7.3f}")
    print("\n  Brier and ECE lower is better. ECE target < 0.10 (design doc §5).")
    print("  Accuracy alone is not evidence: the baseline predicts the base rate")
    print("  for every goal and still scores what it scores.\n")

    # ── parameter recovery ───────────────────────────────────────────────────
    # The generator encoded a category effort ordering and a per-competing-goal
    # dilution penalty. If the model cannot see them, the pipeline is broken.
    coefs = dict(zip(feature_names, logreg.named_steps["clf"].coef_[0]))
    print("parameter recovery — does the model see what the generator encoded?")
    cat_coefs = {k.replace("cat_", ""): v for k, v in coefs.items() if k.startswith("cat_")}
    order = sorted(cat_coefs.items(), key=lambda kv: kv[1], reverse=True)
    print("  category coefficients (generator order: FINANCE > STUDY > HABIT > CAREER > FITNESS)")
    print("    model order:", " > ".join(k for k, _ in order))
    comp = coefs.get("competing_goals", 0.0)
    print(f"  competing_goals coefficient: {comp:+.3f}  "
          f"({'✓ negative, dilution recovered' if comp < 0 else '✗ expected negative'})")

    print("\n  top features by |coefficient|:")
    for name, c in sorted(coefs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]:
        print(f"    {name:<32}{c:>+8.3f}")

    # ── charts ───────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.plot([0, 1], [0, 1], "--", color="#8C8580", lw=1, label="perfect calibration")
    for probs, label, color in [
        (p_lr, "logistic regression", "#0F766E"),
        (p_gbm, "gradient boosting", "#8B4B8A"),
    ]:
        xs, ys, _ = reliability_points(y_te, probs)
        ax1.plot(xs, ys, "o-", color=color, label=label, lw=1.8, ms=5)
    ax1.set_xlabel("predicted probability")
    ax1.set_ylabel("observed completion rate")
    ax1.set_title("Reliability diagram")
    ax1.legend(frameon=False, fontsize=9)
    ax1.set_xlim(0, 1); ax1.set_ylim(0, 1)
    ax1.grid(alpha=.15)

    top = sorted(coefs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:10][::-1]
    ax2.barh([k for k, _ in top], [v for _, v in top],
             color=["#BE123C" if v < 0 else "#0F766E" for _, v in top])
    ax2.axvline(0, color="#8C8580", lw=1)
    ax2.set_title("Logistic regression coefficients")
    ax2.tick_params(labelsize=8)
    ax2.grid(axis="x", alpha=.15)

    fig.tight_layout()
    chart = out_dir / "evaluation.png"
    fig.savefig(chart, dpi=150)

    # ── persist the model for serving ────────────────────────────────────────
    # Logistic regression is shipped rather than the GBM: it scored higher on
    # every metric here, and its calibration is materially better (ECE 0.026 vs
    # 0.084), which is what matters for a number presented to a user as a
    # probability. feature_names is stored alongside so the serving path can
    # assert column order rather than silently mis-align.
    import joblib

    model_dir = Path("models_store")
    model_dir.mkdir(parents=True, exist_ok=True)
    # Feature ranges travel with the model so the serving path can detect inputs
    # outside what it was trained on. A linear model extrapolates silently and
    # confidently past its training range — a real goal with zero linked
    # transactions (contribution_count = 0, below anything in this data) came back
    # at 99.8%, which is meaningless rather than merely wrong. Percentiles rather
    # than min/max so a single outlier row does not widen the accepted range.
    train_df = X.iloc[train_idx]
    feature_ranges = {
        name: {
            "min": float(train_df[name].quantile(0.01)),
            "max": float(train_df[name].quantile(0.99)),
        }
        for name in feature_names
    }

    artifact = {
        "model": logreg,
        "feature_names": feature_names,
        "feature_ranges": feature_ranges,
        "trained_on": "synthetic",
        "seed": args.seed,
        "n_train_goals": int(len(y_tr)),
        "metrics": next(r for r in results if r["model"] == "logistic regression"),
    }
    joblib.dump(artifact, model_dir / "goal_completion.joblib")
    print(f"\nwrote {model_dir / 'goal_completion.joblib'}")

    (out_dir / "metrics.json").write_text(json.dumps({
        "n_goals": len(df), "n_users": int(df.user_id.nunique()),
        "test_completion_rate": float(y_te.mean()),
        "results": results,
        "logistic_coefficients": {k: float(v) for k, v in coefs.items()},
    }, indent=2))

    print(f"\nwrote {chart}")
    print(f"wrote {out_dir / 'metrics.json'}")
    print("\nNOTE: synthetic data. This validates the implementation, not the")
    print("model's fidelity to real behaviour.")


if __name__ == "__main__":
    main()
