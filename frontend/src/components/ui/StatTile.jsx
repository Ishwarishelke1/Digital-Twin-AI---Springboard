const ACCENTS = {
  neutral: "border-t-slate-200 dark:border-t-slate-700",
  indigo: "border-t-indigo-600",
  emerald: "border-t-emerald-500",
  red: "border-t-red-500",
  amber: "border-t-amber-500",
  predicted: "border-t-violet-500",
};

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
export function StatTile({ label, value, accent = "neutral", predicted = false, sublabel }) {
  const tone = predicted ? "predicted" : accent;
  return (
    <div className={`rounded-2xl border-t-4 bg-white p-5 shadow-sm dark:bg-slate-800 ${ACCENTS[tone]}`}>
      <h4 className={`text-sm font-medium ${predicted ? "text-violet-600 dark:text-violet-400" : "text-slate-500 dark:text-slate-400"}`}>
        {predicted ? "✦ " : ""}{label}
      </h4>
      <p className={`mt-2.5 font-mono text-2xl font-semibold tabular-nums ${predicted ? "text-violet-600 dark:text-violet-400" : "text-slate-800 dark:text-slate-100"}`}>{value}</p>
      {sublabel && <p className="mt-1 text-xs text-slate-400">{sublabel}</p>}
    </div>
  );
}

/** Responsive grid wrapper — 4-across desktop, 2-across tablet, 1-across mobile. */
export function StatGrid({ children }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{children}</div>;
}

export default StatTile;
