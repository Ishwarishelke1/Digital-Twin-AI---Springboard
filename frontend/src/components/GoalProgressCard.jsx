import { PieChart, Pie, Cell } from "recharts";
import { CHART_COLORS } from "../utils/chartColors";

/**
 * Donut + figures for one active goal. Extracted from SavingsProgress so the
 * Study page can show its goals the same way Finance shows savings goals,
 * without the money assumption baked in — `formatValue` is what differs between
 * them (a currency amount vs. a plain count), and everything else is identical.
 *
 * `unitLabel` is deliberately separate from the value rather than folded into
 * formatValue: a unit long enough to matter ("sessions", "chapters") wrapped the
 * headline figure onto two lines in a four-across grid. The number stays on one
 * line and the unit rides on the "of …" line below it, where there is room.
 *
 * Progress comes from `goal.current_value`, which the backend maintains per goal.
 * It is never re-derived here from the page's own records: an earlier version of
 * the finance card computed account-wide savings and showed that same figure on
 * every goal, so two £1,000 goals both claimed the same £800 as 80% complete.
 */
function GoalProgressCard({ goal: activeGoal, formatValue, unitLabel, emptyTitle, emptyMessage }) {

  if (!activeGoal) {
    return (
      <div className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{emptyTitle}</h3>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{emptyMessage}</p>
      </div>
    );
  }

  const target = Number(activeGoal.target_value);
  const current = Number(activeGoal.current_value);

  // A target of zero (or a malformed one) would make the ratio Infinity or NaN and
  // render "NaN%". Nothing is knowable about progress toward it, so show none.
  const percentage =
    Number.isFinite(target) && target > 0
      ? Math.max(0, Math.min(Math.round((current / target) * 100), 100))
      : 0;

  const donutData = [
    { name: "completed", value: percentage },
    { name: "remaining", value: 100 - percentage },
  ];

  return (
    <div className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">

      <h3 className="truncate text-lg font-semibold text-slate-800 dark:text-slate-100" title={activeGoal.title}>
        {activeGoal.title}
      </h3>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="relative h-28 w-28 shrink-0">
          <PieChart width={112} height={112}>
            <Pie
              data={donutData}
              dataKey="value"
              cx="50%"
              cy="50%"
              innerRadius={38}
              outerRadius={52}
              startAngle={90}
              endAngle={-270}
              stroke="none"
              isAnimationActive={false}
            >
              <Cell fill={CHART_COLORS.positive} />
              <Cell fill={CHART_COLORS.grid} />
            </Pie>
          </PieChart>
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="font-mono text-lg font-semibold tabular-nums text-slate-800 dark:text-slate-100">
              {percentage}%
            </span>
          </div>
        </div>

        <div className="min-w-0">
          <p className="truncate font-mono text-xl font-semibold tabular-nums text-slate-800 dark:text-slate-100">
            {formatValue(current)}
          </p>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            of {formatValue(target)}{unitLabel ? ` ${unitLabel}` : ""} goal
          </p>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{percentage}% Completed</p>
        </div>
      </div>

    </div>
  );
}

export default GoalProgressCard;
