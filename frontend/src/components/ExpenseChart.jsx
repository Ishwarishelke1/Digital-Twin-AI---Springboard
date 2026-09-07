import { memo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ReferenceDot,
} from "recharts";
import { CHART_COLORS } from "../utils/chartColors";
import { formatCurrency } from "../utils/currency";

/**
 * ExpenseChart — monthly expenses, with the forecast continuing the same line.
 *
 * Recorded months are solid in the action colour; projected months are dashed in
 * the "predicted" plum. Previously the projections were merged into the same
 * `expense` key and drawn as one unbroken solid line, so a viewer had no way to
 * tell which months had actually happened.
 *
 * @param {{ data: Array<{ month: string, expense?: number, projected?: number }>,
 *           currency?: string }} props
 */
function ExpenseChart({ data, currency = "USD" }) {
  const rows = data ?? [];
  const actuals = rows.filter((d) => d.expense != null);
  const latest = actuals[actuals.length - 1];
  const forecasts = rows.filter((d) => d.expense == null && d.projected != null);
  const hasForecast = forecasts.length > 0;
  const joinPoint = hasForecast ? actuals[actuals.length - 1] : null;

  return (
    <div className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">
      <h3 className="mb-5 text-lg font-semibold text-slate-800 dark:text-slate-100">Monthly Expense Trend</h3>
      <p className="sr-only">
        Monthly expense trend chart.{" "}
        {latest
          ? `Most recent recorded month: ${latest.month}, ${formatCurrency(Math.round(latest.expense), currency)}.`
          : "No data yet."}
        {hasForecast &&
          ` Projected ${forecasts.length} month${forecasts.length === 1 ? "" : "s"} ahead, ending at ${formatCurrency(Math.round(forecasts[forecasts.length - 1].projected), currency)}.`}
      </p>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
          <XAxis dataKey="month" tick={{ fill: CHART_COLORS.muted, fontSize: 12 }} />
          <YAxis tick={{ fill: CHART_COLORS.muted, fontSize: 12 }} />
          <Tooltip
            formatter={(value, name) => [formatCurrency(Math.round(value), currency), name]}
            contentStyle={{ fontSize: 12 }}
          />
          {hasForecast && (
            <Legend verticalAlign="top" align="right" height={28} wrapperStyle={{ fontSize: 12 }} />
          )}

          <Line
            type="monotone"
            dataKey="expense"
            name="Recorded"
            stroke={CHART_COLORS.action}
            strokeWidth={3}
            dot={false}
          />

          {hasForecast && (
            <Line
              type="monotone"
              dataKey="projected"
              name="Projected"
              stroke={CHART_COLORS.predicted}
              strokeWidth={2.5}
              strokeDasharray="6 4"
              dot={{ r: 3, fill: CHART_COLORS.predicted, strokeWidth: 0 }}
              connectNulls
            />
          )}

          {joinPoint && (
            <ReferenceDot
              x={joinPoint.month}
              y={joinPoint.expense}
              r={4}
              fill={CHART_COLORS.action}
              stroke="none"
              isFront
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default memo(ExpenseChart);
