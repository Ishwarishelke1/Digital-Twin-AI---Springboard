/**
 * Suggested Questions — each one deliberately answerable from what the
 * assistant is actually handed (services/ai_assistant_service.py's
 * `_build_context`: savings rate, emergency fund, study consistency, habit
 * completion, lifestyle score, productivity score, active goals). The
 * assistant is told to say so plainly rather than guess when a question falls
 * outside that context — a suggestion built to trigger exactly that response
 * would make the assistant look unreliable for something it was never
 * grounded on to begin with, which was true of a few of the questions this
 * replaced (asking to predict a CGPA the app doesn't track, generic sleep/
 * routine advice with no data behind it).
 */
function SuggestionCard({ sendMessage }) {
  const suggestions = [
    "How's my savings rate and emergency fund looking?",
    "Am I on track with my active goals?",
    "How consistent has my studying been lately?",
    "How am I doing with my daily habits?",
    "What's holding back my productivity score?",
    "Give me an honest overview of my progress.",
  ];

  return (
    <div className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">

      <h3 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">Suggested Questions</h3>

      <div className="flex flex-wrap gap-2.5">

        {suggestions.map((item) => (

          <button
            key={item}
            className="rounded-full border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm text-indigo-700 transition-colors hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 dark:hover:bg-indigo-900"
            onClick={() => sendMessage(item)}
          >
            {item}
          </button>

        ))}

      </div>

    </div>
  );
}

export default SuggestionCard;
