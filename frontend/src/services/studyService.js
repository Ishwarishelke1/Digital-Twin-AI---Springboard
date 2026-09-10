/**
 * src/services/studyService.js
 * Study service layer — wraps /api/v1/study/* endpoints.
 * All requests are authenticated via the Axios interceptor in api.js.
 */
import api from "./api";

/**
 * Fetch paginated study session history.
 * GET /api/v1/study/sessions
 * @param {{ page?, limit?, subject? }} params
 * @returns {Promise<{ data, total, page, limit, total_pages }>}
 */
export const getSessions = async (params = {}) => {
  const response = await api.get("/study/sessions", { params });
  return response.data;
};

/**
 * Log a new study session.
 * POST /api/v1/study/sessions
 * @param {{ subject, study_hours, session_type, session_date? }} payload
 * @returns {Promise<StudyRecordResponse>}
 */
export const createSession = async (payload) => {
  const response = await api.post("/study/sessions", payload);
  return response.data;
};

/**
 * Fetch aggregated subject performance for the analytics chart.
 * GET /api/v1/study/analytics/subject-performance
 * @param {number} [monthsBack] - optional lookback window
 * @returns {Promise<SubjectPerformanceSummary[]>}
 */
export const getSubjectPerformance = async (monthsBack) => {
  const params = monthsBack ? { months_back: monthsBack } : {};
  const response = await api.get("/study/analytics/subject-performance", { params });
  return response.data;
};

export const updateSession = async (id, payload) => {
  const response = await api.patch(`/study/sessions/${id}`, payload);
  return response.data;
};

export const deleteSession = async (id) => {
  const response = await api.delete(`/study/sessions/${id}`);
  return response.data;
};
