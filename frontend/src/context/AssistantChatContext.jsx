/**
 * src/context/AssistantChatContext.jsx
 * One shared assistant conversation for the whole authenticated session —
 * the full /assistant page and the floating launcher (components/
 * AssistantLauncher.jsx) both read and write THIS state, not independent
 * copies of their own, so a question asked from either one shows up in the
 * other immediately, with nothing to reconcile.
 *
 * Persisted to localStorage, scoped to today only: the backend deliberately
 * does not store chat transcripts (see api/v1/assistant.py's docstring — a
 * stated privacy choice, not an oversight), so this stays entirely
 * client-side rather than reversing that. A day-scoped memory doesn't need a
 * database or Redis to get "remembers for today, forgets after" — a
 * date-stamped localStorage key already does exactly that, the same way
 * MainLayout.jsx already persists the sidebar's expanded/collapsed state.
 * Scoped by user id too, so switching accounts on the same browser can't
 * inherit someone else's conversation.
 *
 * Mounted in MainLayout.jsx, not main.jsx — ProtectedRoute only renders
 * MainLayout once `user` is populated, and un-mounts it on logout (renders
 * <Navigate> instead), so this provider naturally resets between sessions
 * with no separate "clear on logout" logic needed.
 */
import { useEffect, useState } from "react";
import { toast } from "react-toastify";

import { sendChatMessage } from "../services/assistantService";
import { getApiErrorMessage } from "../utils/apiError";
import { useAuth } from "./useAuth";
import { AssistantChatContext } from "./assistantChatContextInstance";

const GREETING = {
  sender: "ai",
  text: "Hi — ask me anything about your finances, study progress, or habits and I'll answer using your real Digital Twin data.",
};

const STORAGE_PREFIX = "digital_twin_assistant_chat_";

/** Local calendar day, not UTC — this is a courtesy "did you already talk to
 *  it today" feature, not a data-integrity boundary, so it should match what
 *  the person in front of the screen means by "today." */
function todayStamp() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function storageKey(userId) {
  return `${STORAGE_PREFIX}${userId}_${todayStamp()}`;
}

function loadTodaysMessages(userId) {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : null;
  } catch {
    return null; // corrupt/foreign value — treat as "nothing stored," not a crash
  }
}

/** Drops this user's stored entries from days other than today, so
 *  localStorage doesn't quietly grow by one key per calendar day forever. */
function pruneOldEntries(userId) {
  try {
    const keep = storageKey(userId);
    const prefix = `${STORAGE_PREFIX}${userId}_`;
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (key && key.startsWith(prefix) && key !== keep) localStorage.removeItem(key);
    }
  } catch {
    // Storage unavailable — nothing to prune, nothing to fail over.
  }
}

export function AssistantChatProvider({ children }) {
  const { user } = useAuth();
  const userId = user?.id;

  // Loaded once, synchronously, at mount — not in an effect that re-runs and
  // calls setState on [userId]. That would only matter if this provider's
  // userId could change under an already-mounted instance, which it can't
  // today: ProtectedRoute unmounts MainLayout (and everything inside it,
  // this provider included) on logout and mounts it fresh on the next login
  // (see the file-level docstring), so a given instance only ever sees one
  // user for its whole lifetime. pruneOldEntries runs here too, for the same
  // reason — once, at the point the real userId is first known.
  const [messages, setMessages] = useState(() => {
    if (!userId) return [GREETING];
    pruneOldEntries(userId);
    return loadTodaysMessages(userId) || [GREETING];
  });
  const [isThinking, setIsThinking] = useState(false);

  useEffect(() => {
    if (!userId) return;
    try {
      localStorage.setItem(storageKey(userId), JSON.stringify(messages));
    } catch {
      // Quota/private-browsing — the conversation still works for this tab,
      // it just won't be there on the next reload.
    }
  }, [messages, userId]);

  const sendMessage = async (text) => {
    if (!text.trim() || isThinking) return;

    // Snapshot the conversation so far as history — sent back to the backend
    // for bounded multi-turn memory (see assistantService.sendChatMessage
    // and services/ai_assistant_service.py's MAX_HISTORY_TURNS). Now that
    // the conversation lives here rather than in Assistant.jsx's own state,
    // this is the one place both surfaces (the full page and the floating
    // launcher) get it from.
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

  /** Starts over — both surfaces see the reset immediately, same as any
   *  other change to this shared state. Worth having now that the
   *  conversation persists across visits instead of resetting on its own. */
  const clearChat = () => {
    setMessages([GREETING]);
    if (userId) {
      try {
        localStorage.removeItem(storageKey(userId));
      } catch {
        // Nothing to clean up if storage isn't available in the first place.
      }
    }
  };

  return (
    <AssistantChatContext.Provider value={{ messages, isThinking, sendMessage, clearChat }}>
      {children}
    </AssistantChatContext.Provider>
  );
}
