import { RotateCcw } from "lucide-react";

import ChatBox from "../components/ChatBox";
import ChatInput from "../components/ChatInput";
import QuickActions from "../components/QuickActions";
import SuggestionCard from "../components/SuggestionCard";
import { useAssistantChatContext } from "../context/useAssistantChatContext";

function Assistant() {

  const { messages, isThinking, sendMessage, clearChat } = useAssistantChatContext();

  // Only one real exchange (past the standing greeting) is worth offering to
  // clear — an empty conversation has nothing to reset.
  const hasConversation = messages.length > 1;

  return (
    <div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">Digital Twin AI Assistant</h2>
          <p className="mb-6 mt-1.5 text-sm text-slate-500 dark:text-slate-400">
            Grounded in your real profile, goals, finance, study, habits, forecasts, and what-if history — not canned replies.
          </p>
        </div>

        {/* This conversation now carries over between visits (today only —
            see context/AssistantChatContext.jsx) instead of resetting on
            every page load, and it's the same one the floating launcher on
            every other page reads and writes. A way to start over is worth
            having now that it doesn't reset on its own. */}
        {hasConversation && (
          <button
            type="button"
            onClick={clearChat}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-200"
          >
            <RotateCcw size={13} strokeWidth={1.8} />
            Clear chat
          </button>
        )}
      </div>

      <div className="flex flex-col gap-6">
        <QuickActions sendMessage={sendMessage} />

        <SuggestionCard sendMessage={sendMessage} />

        <ChatBox messages={messages} isThinking={isThinking} />

        <ChatInput sendMessage={sendMessage} disabled={isThinking} />
      </div>

    </div>
  );
}

export default Assistant;
