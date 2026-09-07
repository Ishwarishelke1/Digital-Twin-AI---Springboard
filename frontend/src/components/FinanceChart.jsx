import { memo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
  ReferenceDot,
} from "recharts";
import EmptyState from "./ui/EmptyState";
import { CHART_COLORS } from "../utils/chartColors";
import { formatCurrency } from "../utils/currency";

/**
 * FinanceChart — monthly savings, with the forecast continuing the same line.
 *
 * History and projection are separate series so they can be drawn differently:
 * solid in the action colour for what was measured, dashed in the "predicted"
 * plum for what is estimated. Drawing them identically would present a
 * projection with the same authority as a recorded figure, which is the whole
 * reason the design system reserves a distinct colour for predicted content.
 *
 * @param {{ data: Array<{ month: string, savings?: number, projected?: number }>,
 *           currency?: string, forecastMethod?: string }} props
 */
function FinanceChart({ data = [], currency = "USD", forecastMethod }) {
  if (data.length === 0) {
    return <EmptyState title="No savings data yet" message="Log a few transactions on the Finance page to see your trend here." />;
  }

  const actuals = data.filter((d) => d.savings != null);
  const latest = actuals[actuals.length - 1];
  const forecasts = data.filter((d) => d.savings == null && d.projected != null);
  const hasForecast = forecasts.length > 0;

  // The join point carries both keys; it is where measurement stops and
  // estimation begins, so it gets a marker.
  const joinPoint = hasForecast ? actuals[actuals.length - 1] : null;

  const summary = latest
    ? `Savings trend chart. Latest recorded point: ${latest.month}, ${formatCurrency(Math.round(latest.savings), currency)}.` +
      (hasForecast
        ? ` Projected ${forecasts.length} month${forecasts.length === 1 ? "" : "s"} ahead, ending at ${formatCurrency(Math.round(forecasts[forecasts.length - 1].projected), currency)}.`
        : "")
    : "Savings trend chart.";

  return (
    <>
      <p className="sr-only">{summary}</p>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
          <XAxis dataKey="month" tick={{ fill: CHART_COLORS.muted, fontSize: 12 }} />
          <YAxis tick={{ fill: CHART_COLORS.muted, fontSize: 12 }} />
          <Tooltip
            formatter={(value, name) => [formatCurrency(Math.round(value), currency), name]}
            contentStyle={{ fontSize: 12 }}
          />
          {hasForecast && (
            <Legend
              verticalAlign="top"
              align="right"
              height={28}
              wrapperStyle={{ fontSize: 12 }}
            />
          )}

          <Line
            type="monotone"
            dataKey="savings"
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
              // Without this the dashed series breaks at every historical point,
              // where `projected` is undefined.
              connectNulls
            />
          )}

          {joinPoint && (
            <ReferenceDot
              x={joinPoint.month}
              y={joinPoint.savings}
              r={4}
              fill={CHART_COLORS.action}
              stroke="none"
              isFront
            />
          )}
        </LineChart>
      </ResponsiveContainer>

      {hasForecast && forecastMethod && (
        <p className="mt-1 text-center text-[11px] text-slate-400 dark:text-slate-500">
          Projection uses {forecastMethod.replace(/_/g, " ")}
        </p>
      )}
    </>
  );
}

export default memo(FinanceChart);
