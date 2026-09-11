import { Sparkles, Wand2 } from "lucide-react";
import StaggerIn from "./ui/StaggerIn";

const PROVIDER_LABELS = {
  groq: "Groq",
  gemini: "Gemini",
};

function relativeTime(iso) {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;

  const minutes = Math.round((Date.now() - then.getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/**
 * Recommendations written by an LLM from the user's own figures.
 *
 * Nothing on this panel calls a model on its own. Opening the page shows the last
 * set that was generated; a new one costs a button press. The button is therefore
 * the primary control here rather than a quiet corner affordance, and it says what
 * it will do — "Generate" when there is nothing yet, "Regenerate" when there is.
 *
 * `provider` is "rules" whenever no model wrote the lines — nothing generated yet,
 * or every provider failed — and the panel says so, because the fallback text is
 * threshold output that reads exactly like advice and a reader with no way to tell
 * them apart would credit a model for lines a comparison wrote.
 *
 * There is deliberately no canned default. The version this replaced rendered four
 * hardcoded lines ("Your wellness score is improving...") whenever the real list was
 * empty, so a user with no data read confident advice about a routine they did not have.
 */
function AIRecommendationPanel({
  title, items = [], provider, generatedAt, stale = false,
  isLoading = false, isGenerating = false, onGenerate, emptyMessage,
}) {
  const modelLabel = PROVIDER_LABELS[provider];
  const stamp = relativeTime(generatedAt);
  const hasModelOutput = Boolean(modelLabel);

  /* The footer only appears when it has something the reader cannot otherwise
   * know. A successful, current generation says nothing: the violet rule down
   * each line already marks the panel as model output, and repeating the
   * provider's name under every load was noise. What stays is the two cases
   * where silence would mislead — advice written against figures that have since
   * moved, and threshold lines no model wrote. */
  let footnote = null;
  if (isGenerating) {
    footnote = "Reading your figures…";
  } else if (hasModelOutput && stale) {
    footnote = `Written ${stamp ?? "earlier"} — your data has changed since. Regenerate to update.`;
  } else if (!hasModelOutput) {
    footnote = "Threshold-based summaries. Generate to have a model read your figures.";
  }

  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800 dark:text-slate-100">
          <Sparkles size={17} strokeWidth={1.8} className="text-violet-500" aria-hidden="true" />
          {title}
        </h3>

        {onGenerate && (
          <button
            type="button"
            onClick={onGenerate}
            disabled={isGenerating || isLoading}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
              hasModelOutput && !stale
                ? "border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700/40"
                : "border-violet-500 text-violet-600 hover:bg-violet-100 dark:text-violet-400 dark:hover:bg-violet-500/10"
            }`}
          >
            <Wand2 size={13} strokeWidth={2} className={isGenerating ? "animate-pulse" : ""} />
            {isGenerating ? "Generating..." : hasModelOutput ? "Regenerate" : "Generate"}
          </button>
        )}
      </div>

      {isLoading && items.length === 0 ? (
        <div className="flex flex-col gap-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700/40" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">{emptyMessage}</p>
      ) : (
        <div className={`flex flex-col gap-2.5 transition-opacity ${isGenerating ? "opacity-50" : "opacity-100"}`}>
          {items.map((text, i) => (
            <StaggerIn key={i} index={i}>
              <div
                className={`rounded-lg border-l-4 bg-slate-50 p-3.5 text-sm text-slate-700 dark:bg-slate-700/40 dark:text-slate-300 ${
                  hasModelOutput ? "border-violet-500" : "border-slate-300 dark:border-slate-600"
                }`}
              >
                {text}
              </div>
            </StaggerIn>
          ))}
        </div>
      )}

      {items.length > 0 && footnote && (
        <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-400 dark:border-slate-700 dark:text-slate-500">
          {footnote}
        </p>
      )}
    </div>
  );
}

export default AIRecommendationPanel;
