/**
 * src/services/recommendationService.js
 * AI recommendations for the Habits and Study pages.
 * GET /api/v1/recommendations/{habits,study}
 *
 * A plain call never reaches a model — it returns whatever was last generated,
 * or the deterministic threshold lines if nothing has been. Pass
 * `{ generate: true }` to actually spend a model call.
 *
 * The response carries `provider`: "groq" or "gemini" when a model wrote the
 * lines, "rules" when none did. Callers must surface that difference rather than
 * presenting fallback text as model output. `stale` marks a stored set written
 * before the current figures.
 */
import api from "./api";

async function fetchRecommendations(domain, { generate = false } = {}) {
  const response = await api.get(`/recommendations/${domain}`, {
    params: generate ? { generate: true } : {},
  });
  return response.data;
}

export const getHabitRecommendations = (options) => fetchRecommendations("habits", options);
export const getStudyRecommendations = (options) => fetchRecommendations("study", options);
