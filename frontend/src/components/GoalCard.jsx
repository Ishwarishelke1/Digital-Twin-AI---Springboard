import { Edit, Trash2, CheckCircle2, Sparkles } from "lucide-react";

/** Likelihood of hitting the target by its deadline.
 *
 * Rendered in the "predicted" plum accent rather than the teal used for real
 * figures, because it is an estimate sitting next to measured values and should
 * not be mistaken for one. `prediction.probability` is null whenever the model
 * declines — too little history, or inputs outside its trained range — in which
 * case the reason is shown instead of a number. That refusal is the expected
 * path for new goals, not an error state.
 *
 * The response still carries `trained_on` (currently "synthetic"); it is no
 * longer surfaced here at the product owner's request. Worth stating somewhere
 * user-visible before this ships to anyone but the author, since the model has
 * not been validated against real behaviour.
 */
function CompletionLikelihood({ prediction }) {
  if (!prediction) return null;

  const { probability, reason } = prediction;
  const pct = probability == null ? null : Math.round(probability * 100);

  return (
    <div className="mt-3.5 border-t border-slate-100 pt-3 dark:border-slate-700">
      <div className="flex items-center justify-center gap-1.5">
        <Sparkles size={12} strokeWidth={1.8} className="text-violet-600 dark:text-violet-400" />
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          Likely to finish on time
        </span>
      </div>
      {pct == null ? (
        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{reason}</p>
      ) : (
        <>
          <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-violet-600 dark:text-violet-400">
            {pct}%
          </p>
          <p className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
            Estimate
          </p>
        </>
      )}
    </div>
  );
}

function GoalCard({ title, value, completed, prediction, onEdit, onDelete }) {
  return(
    <div className={`relative rounded-2xl bg-white dark:bg-slate-800 p-6 text-center shadow-sm ${completed ? "ring-1 ring-emerald-400/60" : ""}`}>
      <div className="absolute right-1.5 top-1.5 flex gap-0.5">
        {onEdit && (
          <button onClick={onEdit} className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 dark:hover:bg-white/10" aria-label="Edit">
            <Edit size={14} />
          </button>
        )}
        {onDelete && (
          <button onClick={onDelete} className="rounded-md p-1.5 text-red-400 hover:bg-slate-100 hover:text-red-600 dark:hover:bg-white/10" aria-label="Delete">
            <Trash2 size={14} />
          </button>
        )}
      </div>
      {completed && (
        <span className="absolute left-1.5 top-1.5 flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400">
          <CheckCircle2 size={12} strokeWidth={2} /> Completed
        </span>
      )}
      <h3 className="mb-3.5 text-sm font-medium text-slate-500 dark:text-slate-400">{title}</h3>
      <h2 className="font-mono text-xl font-semibold tabular-nums text-indigo-600 dark:text-indigo-400">{value}</h2>
      {!completed && <CompletionLikelihood prediction={prediction} />}
    </div>
  );
}

export default GoalCard;
