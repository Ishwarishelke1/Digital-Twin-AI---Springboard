/**
 * Shared "title + list of labeled progress bars" component — replaces the
 * near-identical markup SubjectProgress (Study) and HabitProgress (Habits)
 * each hand-rolled independently.
 *
 * An item's `value` is always the bar's fill percentage. What that percentage
 * *means* differs by caller, so the figure beside the label is overridable:
 * Habits shows the percentage itself ("62%"), while Study shows the underlying
 * quantity ("14.5 hrs") because a share-of-total reads better as the real
 * amount. `meta` and `chip` add a secondary line and a status pill for callers
 * that have more to say per row; both are optional and Habits passes neither.
 */
function ProgressList({ title, items, emptyMessage, footnote }) {
  return (
    <div className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">
      <h3 className="mb-5 text-lg font-semibold text-slate-800 dark:text-slate-100">{title}</h3>

      {items.length === 0 ? (
        <p className="text-sm text-slate-400">{emptyMessage}</p>
      ) : (
        <div className="flex flex-col gap-4">
          {items.map((item) => (
            <div key={item.key}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm text-slate-600 dark:text-slate-400">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate">{item.label}</span>
                  {item.chip}
                </span>
                <span className="shrink-0 font-mono tabular-nums">
                  {item.valueLabel ?? `${Math.round(item.value)}%`}
                </span>
              </div>

              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                <div
                  className={`h-full rounded-full ${item.color || "bg-indigo-600"}`}
                  style={{ width: `${Math.min(Math.max(item.value, 0), 100)}%` }}
                ></div>
              </div>

              {item.meta && (
                <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">{item.meta}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {footnote && (
        <p className="mt-5 border-t border-slate-100 pt-3 text-xs text-slate-400 dark:border-slate-700 dark:text-slate-500">
          {footnote}
        </p>
      )}
    </div>
  );
}

export default ProgressList;
