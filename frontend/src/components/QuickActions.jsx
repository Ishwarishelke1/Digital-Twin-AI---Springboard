import { BarChart3, BookOpen, Wallet, Activity, TrendingUp, Target } from "lucide-react";

/**
 * Icon shortcuts for the same underlying chat — kept distinct in wording from
 * SuggestionCard's pills below (they used to share one question verbatim,
 * "How can I improve my productivity?", appearing twice on the same page).
 * Same grounding rule as SuggestionCard: every prompt maps to a real field in
 * the assistant's context (services/ai_assistant_service.py's `_build_context`).
 */
function QuickActions({ sendMessage }) {
  const actions = [
    {
      icon: BarChart3,
      label: "Overall Progress",
      prompt: "Give me an honest, detailed assessment of my progress across finance, study, and habits.",
    },
    {
      icon: Wallet,
      label: "Savings Check",
      prompt: "Break down my savings rate and emergency fund — am I in good shape?",
    },
    {
      icon: BookOpen,
      label: "Study Consistency",
      prompt: "Rate my study consistency and tell me what would move it up.",
    },
    {
      icon: Activity,
      label: "Habit Streaks",
      prompt: "How's my habit completion rate, and what's slipping?",
    },
    {
      icon: Target,
      label: "Goal Priorities",
      prompt: "Which of my active goals should I be prioritizing right now?",
    },
    {
      icon: TrendingUp,
      label: "Productivity Tips",
      prompt: "What's dragging down my productivity score, and how do I fix it?",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">

      {actions.map((item) => (

        <button
          key={item.label}
          className="flex flex-col items-center gap-2 rounded-2xl bg-white dark:bg-slate-800 p-4 text-center text-sm font-medium text-slate-600 dark:text-slate-400 shadow-sm transition-colors hover:bg-indigo-50 hover:text-indigo-700 dark:hover:bg-indigo-950 dark:hover:text-indigo-300"
          onClick={() => sendMessage(item.prompt)}
        >
          <item.icon size={20} strokeWidth={1.8} />
          {item.label}
        </button>

      ))}

    </div>
  );
}

export default QuickActions;
