import { useState } from "react";
import { toast } from "react-toastify";

import { getDomainComparison } from "../services/simulationService";
import { getApiErrorMessage } from "../utils/apiError";
import RecommendationCard from "./SimulationRecommendationCard";

const DOMAIN_LABELS = { finance: "Finance", study: "Study", fitness: "Fitness" };

function bestScenario(scenarios) {
  if (!scenarios || scenarios.length === 0) return null;
  return scenarios.reduce((a, b) => (b.score > a.score ? b : a), scenarios[0]);
}

function DomainComparison() {
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleCompare = async () => {
    setLoading(true);
    try {
      const data = await getDomainComparison();
      setComparison(data);
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Unable to load the comparison."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">Compare All Outcomes</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Run a default what-if across finance, study, and fitness at once, and see which one deserves your focus.
          </p>
        </div>

        <button
          type="button"
          onClick={handleCompare}
          disabled={loading}
          className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          {loading ? "Comparing..." : comparison ? "Re-run Comparison" : "Compare"}
        </button>
      </div>

      {comparison && (
        <div className="flex flex-col gap-6">
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Re-running saves a new simulation snapshot to your history — it doesn't overwrite this one.
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {["finance", "study", "fitness"].map((domain) => {
              const best = bestScenario(comparison[domain]?.scenarios);
              return (
                <div
                  key={domain}
                  className="rounded-xl border border-slate-100 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-700/40"
                >
                  <h4 className="mb-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {DOMAIN_LABELS[domain]}
                  </h4>
                  {best ? (
                    <>
                      <p className="text-xs text-slate-500 dark:text-slate-400">Best: {best.name}</p>
                      <p className="mt-2 text-xs font-medium text-indigo-600 dark:text-indigo-400 dark:text-indigo-400">
                        Score: {Math.round(best.score)}/100
                      </p>
                    </>
                  ) : (
                    <p className="text-xs text-slate-400 dark:text-slate-500">No scenarios available.</p>
                  )}
                </div>
              );
            })}
          </div>

          <RecommendationCard key={comparison.overall_recommendation.id} recommendation={comparison.overall_recommendation} />
        </div>
      )}
    </div>
  );
}

export default DomainComparison;
