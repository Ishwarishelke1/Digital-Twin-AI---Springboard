import { Edit, Trash2, CheckCircle2 } from "lucide-react";

function GoalCard({ title, value, completed, onEdit, onDelete }) {
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
    </div>
  );
}

export default GoalCard;
