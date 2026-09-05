import Card from "./ui/Card";
import Badge from "./ui/Badge";

const BURNOUT_TONE = {
  LOW_RISK: "success",
  MODERATE_RISK: "warning",
  HIGH_RISK: "danger",
  CRITICAL_BURNOUT: "danger",
  UNKNOWN: "neutral",
};

const BURNOUT_LABEL = {
  LOW_RISK: "Low risk",
  MODERATE_RISK: "Moderate risk",
  HIGH_RISK: "High risk",
  CRITICAL_BURNOUT: "Critical",
  UNKNOWN: "Not enough data yet",
};

function metric(label, value, decimals = 0) {
  return { label, value: value != null ? `${Number(value).toFixed(decimals)}%` : "—" };
}

/**
 * Renders User.digital_twin_state — the composite snapshot the backend
 * computes on every GET /users/me (savings rate, emergency fund runway,
 * study/habit/lifestyle/productivity scores, burnout risk). This data has
 * always been fetched by Dashboard.jsx but never rendered anywhere in the app.
 */
function DigitalTwinCard({ twinState }) {
  if (!twinState) return null;

  const metrics = [
    metric("Savings rate", twinState.savings_rate_pct, 1),
    { label: "Emergency fund", value: `${Number(twinState.emergency_fund_months ?? 0).toFixed(1)} mo` },
    metric("Study consistency", twinState.study_consistency_score),
    metric("Predicted exam score", twinState.predicted_exam_score),
    metric("Habit completion", twinState.habit_completion_rate),
    { label: "Lifestyle score", value: twinState.lifestyle_score != null ? `${Math.round(twinState.lifestyle_score)}/100` : "—" },
    metric("Productivity", twinState.productivity_score),
  ];

  // Hidden while UNKNOWN. Nothing in the backend writes burnout_risk_cluster
  // today (see api/v1/habits.py and user_service.py, which both say so), so this
  // badge was permanently "Not enough data yet" — a visible metric that never
  // changes erodes trust in the real numbers beside it. Kept as a conditional
  // rather than deleted: the moment the field is populated the badge returns
  // with no further change here. See REMEDIATION_PLAN.md §6 for why the planned
  // clustering model was reconsidered rather than built.
  const burnout = twinState.burnout_risk_cluster ?? "UNKNOWN";
  const showBurnout = burnout !== "UNKNOWN";
  const lastUpdated = twinState.last_updated_at
    ? new Date(twinState.last_updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : null;

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Your Digital Twin</h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">A single snapshot of where every model has you right now.</p>
        </div>
        {showBurnout && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Burnout risk</span>
            <Badge tone={BURNOUT_TONE[burnout] ?? "neutral"}>{BURNOUT_LABEL[burnout] ?? burnout}</Badge>
          </div>
        )}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-4">
        {metrics.map((m) => (
          <div key={m.label}>
            <div className="text-xs font-medium text-slate-500 dark:text-slate-400">{m.label}</div>
            <div className="mt-1.5 font-mono text-lg font-semibold tabular-nums text-slate-800 dark:text-slate-100">{m.value}</div>
          </div>
        ))}
      </div>

      {lastUpdated && (
        <p className="mt-6 text-xs text-slate-400">Last updated {lastUpdated}</p>
      )}
    </Card>
  );
}

export default DigitalTwinCard;
