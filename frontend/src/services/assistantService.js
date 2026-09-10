/**
 * src/services/assistantService.js
 * AI assistant service layer — wraps /api/v1/assistant/*.
 */
import api from "./api";

/**
 * Sends a message to the AI assistant and gets a grounded reply back
 * (Gemini primary, Groq fallback — see backend_api/services/ai_assistant_service.py).
 * The reply is grounded in the user's live finance, study, habit, forecast and
 * what-if data — not just profile/goals.
 * POST /api/v1/assistant/chat
 * @param {string} message
 * @param {{sender: "user"|"ai", text: string}[]} [history] - recent prior turns,
 *   oldest first, for conversational continuity. Transcripts aren't persisted
 *   server-side, so the client resends the tail of the conversation on each
 *   call; the backend trims to its own bounded window regardless of how many
 *   are sent (capped at 20 here to match the schema's max_length).
 * @returns {Promise<{ reply: string, provider_used: string }>}
 */
export const sendChatMessage = async (message, history = []) => {
  const response = await api.post("/assistant/chat", {
    message,
    history: history.slice(-20).map(({ sender, text }) => ({ sender, text })),
  });
  return response.data;
};

/**
 * Records thumbs-up/down on a specific assistant reply.
 * POST /api/v1/assistant/chat/feedback
 * @param {string} messageSnippet - the reply text being rated (truncated server-side to 300 chars)
 * @param {"HELPFUL"|"UNHELPFUL"|"IRRELEVANT"} feedback
 */
export const submitChatFeedback = async (messageSnippet, feedback) => {
  const response = await api.post("/assistant/chat/feedback", { message_snippet: messageSnippet, feedback });
  return response.data;
};

/**
 * App-wide satisfaction score, combining AI Assistant chat feedback and simulation
 * recommendation feedback (Milestone 4's "user satisfaction" evaluation criterion).
 * GET /api/v1/assistant/satisfaction-summary
 */
export const getSatisfactionSummary = async () => {
  const response = await api.get("/assistant/satisfaction-summary");
  return response.data;
};
