/**
 * Current Score is real (from the productivity/consistency engines);
 * Future Prediction is model output — per the design system, only the
 * predicted half of each card carries the violet accent, so the two
 * don't read as equally-certain numbers.
 */
function PredictionCards({ predictions = [] }) {

  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">

      {predictions.map((item) => (

        <div key={item.title} className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">

          <h3 className="mb-3 text-lg font-semibold text-slate-800 dark:text-slate-100">
            {item.title}
          </h3>

          <p className="text-sm text-slate-600 dark:text-slate-400">
            Current Score : <strong className="font-mono tabular-nums text-slate-800 dark:text-slate-100">{item.current}%</strong>
          </p>

          <p className="mt-1 text-sm text-violet-600 dark:text-violet-400">
            ✦ Future Prediction : <strong className="font-mono tabular-nums">{item.future}%</strong>
          </p>

          <div
            className="mt-4 h-3 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
            role="progressbar"
            aria-valuenow={Math.min(100, Math.max(0, item.future))}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${item.title} future prediction`}
          >
            <div
              className="h-full rounded-full bg-violet-500"
              style={{ width: `${Math.min(100, Math.max(0, item.future))}%` }}
            ></div>
          </div>

        </div>

      ))}

    </div>
  );
}

export default PredictionCards;
