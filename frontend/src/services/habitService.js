/**
 * src/services/habitService.js
 * Habit service layer — wraps /api/v1/habits/* endpoints.
 * All requests are authenticated via the Axios interceptor in api.js.
 */
import api from "./api";

/**
 * Fetch paginated habit log history.
 * GET /api/v1/habits/daily-log
 * @param {{ page?, limit? }} params
 * @returns {Promise<{ data, total, page, limit, total_pages }>}
 */
export const getHabitLogs = async (params = {}) => {
  const response = await api.get("/habits/daily-log", { params });
  return response.data;
};

/**
 * Upsert today's daily habit log.
 * POST /api/v1/habits/daily-log
 * @param {{ sleep_hours, exercise_minutes, water_intake_liters, screen_time_hours, mood_rating?, meditation_minutes? }} payload
 * @returns {Promise<HabitRecordResponse>}
 */
export const logDailyHabit = async (payload) => {
  const response = await api.post("/habits/daily-log", payload);
  return response.data;
};

/**
 * Edit an existing habit log (typically a past day's entry). log_date is
 * never part of this payload — the backend's unique (user_id, log_date)
 * index means changing it belongs to delete + re-log, not a PATCH.
 * PATCH /api/v1/habits/daily-log/{id}
 * @param {string} id
 * @param {{ sleep_hours?, exercise_minutes?, water_intake_liters?, screen_time_hours?, mood_rating?, meditation_minutes?, linked_goal_id? }} payload
 * @returns {Promise<HabitRecordResponse>}
 */
export const updateHabitLog = async (id, payload) => {
  const response = await api.patch(`/habits/daily-log/${id}`, payload);
  return response.data;
};

export const deleteHabitLog = async (id) => {
  const response = await api.delete(`/habits/daily-log/${id}`);
  return response.data;
};
