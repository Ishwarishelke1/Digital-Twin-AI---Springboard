import CountUp from "../CountUp";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

const ACCENTS = {
  neutral: "border-t-slate-200 dark:border-t-slate-700",
  indigo: "border-t-indigo-600",
  emerald: "border-t-emerald-500",
  red: "border-t-red-500",
  amber: "border-t-amber-500",
  predicted: "border-t-violet-500",
};

/**
 * Renders `value` as ticking-up digits when it's a genuine single number
 * (via CountUp), or as static text otherwise — a fraction like "3/5" or the
 * "—" empty-state placeholder isn't one number, so it's rendered as-is with
 * no attempt to parse it. `prefix`/`suffix` wrap the animated digits (e.g. a
 * currency symbol or "%") so the symbol never itself "counts up".
 */
function StatValue({ value, prefix, suffix, decimals, predicted }) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const isNumber = typeof value === "number" && Number.isFinite(value);

  if (!isNumber) {
    return <>{value}</>;
  }

  if (prefersReducedMotion) {
    const rounded = decimals != null ? value.toFixed(decimals) : value.toLocaleString();
    return <>{prefix}{rounded}{suffix}</>;
  }

  return (
    <>
      {prefix}
      <CountUp
        to={value}
        duration={1}
        className={predicted ? "text-violet-600 dark:text-violet-400" : ""}
      />
      {suffix}
    </>
  );
}

/**
 * Shared stat tile — replaces the four near-identical "4-card grid" components
 * that FinanceSummary/StudySummary/HabitSummary/PredictionSummary each used
 * to hand-roll independently.
 *
 * `predicted` marks a value produced by a forecasting/trend engine rather than
 * entered by the user — per the design system, predicted values get the violet
 * accent and a small "Predicted" caption so they're never visually mistaken
 * for an actual.
 */
export function StatTile({ label, value, prefix, suffix, decimals, accent = "neutral", predicted = false, sublabel }) {
  const tone = predicted ? "predicted" : accent;
  return (
    <div className={`rounded-2xl border-t-4 bg-white p-5 shadow-sm dark:bg-slate-800 ${ACCENTS[tone]}`}>
      <h4 className={`text-sm font-medium ${predicted ? "text-violet-600 dark:text-violet-400" : "text-slate-500 dark:text-slate-400"}`}>
        {predicted ? "✦ " : ""}{label}
      </h4>
      <p className={`mt-2.5 font-mono text-2xl font-semibold tabular-nums ${predicted ? "text-violet-600 dark:text-violet-400" : "text-slate-800 dark:text-slate-100"}`}>
        <StatValue value={value} prefix={prefix} suffix={suffix} decimals={decimals} predicted={predicted} />
      </p>
      {sublabel && <p className="mt-1 text-xs text-slate-400">{sublabel}</p>}
    </div>
  );
}

/** Responsive grid wrapper — 4-across desktop, 2-across tablet, 1-across mobile. */
export function StatGrid({ children }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{children}</div>;
}

export default StatTile;
