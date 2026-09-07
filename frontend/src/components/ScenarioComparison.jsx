function formatMetricValue(value, unit) {
  const formatted = Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (!unit) return formatted;
  if (unit === "INR") return `₹${formatted}`;
  return `${formatted} ${unit}`;
}

function ScenarioComparison({ scenarios }) {
  if (!scenarios || scenarios.length === 0) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <h3 className="mb-4 text-base font-semibold text-slate-800 dark:text-slate-100">
        Future Scenario Comparison
      </h3>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {scenarios.map((scenario, index) => (
          <div
            key={index}
            className="rounded-xl border border-slate-100 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-700/40"
          >
            <h4 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">{scenario.name}</h4>

            <div className="flex flex-col gap-2">
              {scenario.metrics.map((metric) => (
                <div key={metric.label} className="flex items-baseline justify-between gap-2">
                  <span className="text-xs text-slate-500 dark:text-slate-400">{metric.label}</span>
                  <strong className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {formatMetricValue(metric.value, metric.unit)}
                  </strong>
                </div>
              ))}
            </div>

            <p className="mt-3 text-xs font-medium text-indigo-600 dark:text-indigo-400 dark:text-indigo-400">
              Score: {Math.round(scenario.score)}/100
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ScenarioComparison;
