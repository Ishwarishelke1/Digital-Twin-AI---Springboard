import { useState } from "react";
import { toast } from "react-toastify";

import ChatBox from "../components/ChatBox";
import ChatInput from "../components/ChatInput";
import QuickActions from "../components/QuickActions";
import SuggestionCard from "../components/SuggestionCard";
import { sendChatMessage } from "../services/assistantService";
import { getApiErrorMessage } from "../utils/apiError";

function Assistant() {

  const [messages, setMessages] = useState([
    {
      sender: "ai",
      text: "Hi — ask me anything about your finances, study progress, or habits and I'll answer using your real Digital Twin data.",
    },
  ]);
  const [isThinking, setIsThinking] = useState(false);

  const sendMessage = async (text) => {

    if (!text.trim() || isThinking) return;

    // Snapshot the conversation so far as history — sent back to the backend
    // for bounded multi-turn memory (see assistantService.sendChatMessage).
    const history = messages;
    setMessages((prev) => [...prev, { sender: "user", text }]);
    setIsThinking(true);

    try {
      const { reply } = await sendChatMessage(text, history);
      setMessages((prev) => [...prev, { sender: "ai", text: reply }]);
    } catch (err) {
      toast.error(getApiErrorMessage(err, "The assistant couldn't respond. Please try again."));
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <div>

      <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">Digital Twin AI Assistant</h2>

      <p className="mb-6 mt-1.5 text-sm text-slate-500 dark:text-slate-400">
        Grounded in your real profile, goals, finance, study, habits, forecasts, and what-if history — not canned replies.
      </p>

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
