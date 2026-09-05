import { formatCurrency } from "../utils/currency";

const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

/**
 * IncomeProjectionCard — surfaces GET /forecast/income, which has no other
 * representation in the UI (unlike savings/expenses, which are shown via
 * charts, and goal completions, which are shown on the Prediction page).
 * This is model output, not a value the user entered — per the design
 * system, predicted content always carries the violet accent.
 */
function IncomeProjectionCard({ projection, currency = "USD" }) {
  if (!projection || !projection.projections?.length) return null;

  return (
    <div className="rounded-2xl border-t-4 border-t-violet-500 bg-white dark:bg-slate-800 p-6 shadow-sm">
      <h3 className="mb-5 text-lg font-semibold text-violet-600 dark:text-violet-400">✦ Projected Income</h3>
      <ul className="flex flex-col gap-2.5">
        {projection.projections.map((p) => (
          <li key={`${p.year}-${p.month}`} className="flex justify-between border-b border-slate-100 dark:border-slate-700 py-2.5 text-sm">
            <span className="font-mono tabular-nums text-slate-600 dark:text-slate-400">{MONTH_NAMES[p.month - 1]} {p.year}</span>
            <strong className="font-mono tabular-nums text-violet-600 dark:text-violet-400">{formatCurrency(p.projected_amount, currency)}</strong>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-slate-400">
        Data sufficiency: {Math.round(projection.confidence_score * 100)}% · method: {projection.method_used}
      </p>
    </div>
  );
}

export default IncomeProjectionCard;
