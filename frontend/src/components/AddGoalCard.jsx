import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

/**
 * The last tile in a page's goal row: a way into the Goals page from where the
 * goals are actually being read.
 *
 * It exists because goal cards no longer stretch to fill their row. A single
 * goal used to span the full width, which read as a design decision rather than
 * as "you have one goal"; a fixed grid tells the truth about how many there are,
 * and this fills the first empty slot with the action a user looking at a short
 * row most likely wants.
 *
 * Deliberately drawn as an outline rather than a filled card — it is an
 * affordance sitting among real data, and it should not read as another goal.
 *
 * The link carries `new=1` so the Goals page opens its form on arrival rather
 * than landing the user on a list they then have to find a button in, and
 * `category` so the form arrives already set to the kind of goal the page they
 * came from is about.
 */
function AddGoalCard({ label = "Add a goal", hint, category }) {
  const query = new URLSearchParams({ new: "1", ...(category ? { category } : {}) });

  return (
    <Link
      to={`/goals?${query}`}
      className="group flex min-h-45 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-200 p-6 text-center transition-colors hover:border-indigo-600 hover:bg-indigo-100/40 dark:border-slate-700 dark:hover:border-indigo-400 dark:hover:bg-indigo-500/10"
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition-colors group-hover:bg-indigo-600 group-hover:text-white dark:bg-slate-700 dark:text-slate-400">
        <Plus size={18} strokeWidth={2} />
      </span>

      <span className="text-sm font-medium text-slate-700 group-hover:text-indigo-700 dark:text-slate-300 dark:group-hover:text-indigo-400">
        {label}
      </span>

      {hint && <span className="text-xs text-slate-400 dark:text-slate-500">{hint}</span>}
    </Link>
  );
}

export default AddGoalCard;
