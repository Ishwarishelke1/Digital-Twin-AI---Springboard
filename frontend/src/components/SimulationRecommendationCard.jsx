import { useState } from "react";
import { Sparkles, ThumbsUp, ThumbsDown } from "lucide-react";

function formatStatValue(value, unit) {
  const formatted = Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (!unit) return formatted;
  if (unit === "INR") return `₹${formatted}`;
  return `${formatted} ${unit}`;
}

function SimulationRecommendationCard({ recommendation, onFeedback }) {
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(null); // "HELPFUL" | "UNHELPFUL" | null

  if (!recommendation) {
    return null;
  }

  const handleFeedback = async (value) => {
    if (submitting || submitted) return;
    setSubmitting(true);
    try {
      await onFeedback(recommendation.id, value);
      setSubmitted(value);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-6 shadow-sm dark:border-indigo-500/30 dark:bg-indigo-500/10">
      <div className="mb-4 flex items-start gap-3">
        <Sparkles size={22} strokeWidth={1.8} className="mt-0.5 shrink-0 text-indigo-600 dark:text-indigo-400 dark:text-indigo-400" />

        <div>
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">AI Recommendation</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">Based on your simulated future outcomes</p>
        </div>
      </div>

      <h4 className="mb-1 text-sm font-semibold text-indigo-700 dark:text-indigo-300">{recommendation.title}</h4>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">{recommendation.reason}</p>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {recommendation.stats.map((stat) => (
          <div key={stat.label} className="rounded-lg bg-white p-3 dark:bg-slate-800">
            <span className="block text-xs text-slate-500 dark:text-slate-400">{stat.label}</span>
            <strong className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              {formatStatValue(stat.value, stat.unit)}
            </strong>
          </div>
        ))}
      </div>

      {onFeedback && (
        <div className="mt-4">
          {submitted ? (
            <p className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              Thanks for your feedback ({submitted === "HELPFUL" ? "Helpful" : "Not helpful"}).
            </p>
          ) : (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => handleFeedback("HELPFUL")}
                disabled={submitting}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-white disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <ThumbsUp size={14} /> Helpful
              </button>
              <button
                type="button"
                onClick={() => handleFeedback("UNHELPFUL")}
                disabled={submitting}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-white disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <ThumbsDown size={14} /> Not helpful
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SimulationRecommendationCard;
