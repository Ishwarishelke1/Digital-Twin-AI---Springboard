import { useEffect, useRef, useState } from "react";
import { toast } from "react-toastify";
import { Loader2, ThumbsUp, ThumbsDown } from "lucide-react";
import ChatMessage from "./ChatMessage";
import { submitChatFeedback } from "../services/assistantService";
import { getApiErrorMessage } from "../utils/apiError";

/** Thumbs-up/down under each AI reply — persisted via POST /assistant/chat/feedback
 * and aggregated into the app-wide satisfaction score (see Assistant.jsx's stat
 * tile). Same visual pattern as SimulationRecommendationCard's feedback. */
function MessageFeedback({ messageIndex, feedback, onFeedback }) {
  if (feedback) {
    return (
      <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">
        Thanks for your feedback ({feedback === "up" ? "helpful" : "not helpful"}).
      </p>
    );
  }
  return (
    <div className="mt-1.5 flex items-center gap-2">
      <button
        type="button"
        aria-label="Helpful"
        onClick={() => onFeedback(messageIndex, "up")}
        className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-emerald-600 dark:hover:bg-slate-700/40 dark:hover:text-emerald-400"
      >
        <ThumbsUp size={13} strokeWidth={1.8} />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        onClick={() => onFeedback(messageIndex, "down")}
        className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-red-600 dark:hover:bg-slate-700/40 dark:hover:text-red-400"
      >
        <ThumbsDown size={13} strokeWidth={1.8} />
      </button>
    </div>
  );
}

/**
 * `bare` drops the card chrome (background/padding/rounding/shadow/own
 * max-height) for callers that already provide their own container —
 * AssistantLauncher.jsx's floating panel, which would otherwise double up
 * into a card nested inside a card. The full /assistant page keeps the
 * default (card-styled, sized to its own max-height) unchanged.
 */
function ChatBox({ messages, isThinking = false, bare = false }) {
  const [feedbackByIndex, setFeedbackByIndex] = useState({});

  // Auto-scroll to the newest message — including while "Thinking..." is
  // showing, so that indicator (and then the reply that replaces it) stays
  // pinned in view rather than requiring a manual scroll every reply. This
  // div is always the scroll container itself, in both modes (see the
  // `bare` className below) — that's what makes one ref/effect correct for
  // both the full-page card and the floating launcher's panel, rather than
  // needing separate scroll logic for a parent-owned scroll region in the
  // bare case.
  const scrollRef = useRef(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, isThinking]);

  // Optimistic UI stays instant; the persist call is fire-and-forget (only a
  // toast on failure) — same pattern SimulationRecommendationCard already uses.
  //
  // Truncated to 300 chars before it's sent: the backend's own schema caps
  // message_snippet at 300 (a deliberate privacy choice — "only a short
  // snippet of the specific reply being rated," never the full transcript,
  // per api/v1/assistant.py's docstring) and rejects anything longer with a
  // 422 rather than truncating it itself. An assistant reply is routinely
  // past 300 characters, so every thumbs-click on a normal-length reply was
  // silently failing to save — the optimistic UI still showed "Thanks for
  // your feedback" while a toast (easy to miss, auto-dismissing) was the only
  // sign it hadn't actually been recorded. Confirmed against a live backend:
  // a 438-character reply, well within what the assistant's own system
  // prompt asks for, returned a clean 422 "string_too_long" before this fix.
  function handleFeedback(index, value) {
    setFeedbackByIndex((prev) => ({ ...prev, [index]: value }));
    const messageText = (messages[index]?.text ?? "").slice(0, 300);
    submitChatFeedback(messageText, value === "up" ? "HELPFUL" : "UNHELPFUL").catch((err) => {
      toast.error(getApiErrorMessage(err, "Couldn't save your feedback."));
    });
  }

  return (
    <div
      ref={scrollRef}
      className={
        bare
          ? "flex h-full min-h-0 flex-col gap-4 overflow-y-auto"
          : "flex max-h-100 flex-col gap-4 overflow-y-auto rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm"
      }
    >
      {messages.map((message, index) => (
        <div key={index}>
          <ChatMessage message={message} />
          {message.sender === "ai" && index !== 0 && (
            <MessageFeedback
              messageIndex={index}
              feedback={feedbackByIndex[index]}
              onFeedback={handleFeedback}
            />
          )}
        </div>
      ))}

      {isThinking && (
        <div className="flex items-center gap-2 text-sm text-slate-400 dark:text-slate-500">
          <Loader2 size={15} strokeWidth={2} className="animate-spin" />
          Thinking...
        </div>
      )}
    </div>
  );
}

export default ChatBox;
