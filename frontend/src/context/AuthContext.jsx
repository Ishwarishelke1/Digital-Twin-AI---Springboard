/**
 * src/context/AuthContext.jsx
 * Provides authentication state (user, isLoading) to the entire app.
 *
 * Auth is an httpOnly cookie (see services/api.js) — this code can't read it to
 * check "is there a session" up front, so it always asks the backend on mount
 * and treats a 401 as logged-out.
 */
import { useState, useEffect } from "react";
import { getUser, updatePreferences } from "../services/userService";
import { logoutUser } from "../services/authService";
import { AuthContext } from "./authContextInstance";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true); // true while validating session

  // ── Apply the user's saved dark-mode preference to the document root ───────
  // This is a per-account preference (preferences.dark_mode via Settings),
  // not the OS color-scheme — see the `dark` custom variant in index.css.
  useEffect(() => {
    document.documentElement.dataset.theme = user?.preferences?.dark_mode ? "dark" : "light";
  }, [user?.preferences?.dark_mode]);

  // ── Restore session on initial app load ────────────────────────────────────
  // No cross-tab `storage` listener here on purpose: an httpOnly cookie is
  // automatically shared by the browser across every tab of the same origin, so
  // logging out in one tab already applies to the others — just via their next
  // API call 401'ing, rather than instantly like a readable localStorage token
  // could signal. Nothing for this code to listen for.
  useEffect(() => {
    async function restoreSession() {
      try {
        // isSessionProbe: a 401 here means "not logged in", which is a valid
        // answer on a public route — it must not trigger api.js's redirect.
        const userData = await getUser({ isSessionProbe: true });
        setUser(userData);
      } catch {
        // No valid session cookie — stay logged out.
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    }
    restoreSession();
  }, []);

  /**
   * Called after a successful login or register API response. The auth cookie
   * has already been set by the backend on that response.
   * @param {object} userData - the UserResponse or TokenResponse from the backend
   */
  const login = async (userData) => {
    if (!userData.profile) {
      try {
        const fullUser = await getUser();
        setUser(fullUser);
      } catch (err) {
        console.error("Failed to fetch full user on login:", err);
        setUser(userData);
      }
    } else {
      setUser(userData);
    }
  };

  /**
   * Logs out server-side (invalidating the session cookie) and clears local state.
   */
  const logout = async () => {
    await logoutUser();
    setUser(null);
  };

  /**
   * Flips the saved dark-mode preference (sidebar sun/moon toggle) and
   * persists it via the same PATCH /users/me/preferences the old Settings
   * checkbox used — dark mode is still a per-account preference, just
   * toggled from the sidebar now instead of a form field.
   */
  const toggleDarkMode = async () => {
    const updated = await updatePreferences({ dark_mode: !user?.preferences?.dark_mode });
    setUser(updated);
  };

  /**
   * Re-fetches the full user and updates the shared context copy. Several
   * pages (Finance, Study) read `active_goals` off this context's `user`
   * rather than fetching their own copy, so a goal added/edited/deleted
   * anywhere (Goals page, Dashboard's quick-add) needs to call this
   * afterward — otherwise those pages keep showing the pre-mutation goal
   * list until the next full login/session restore.
   */
  const refreshUser = async () => {
    const data = await getUser();
    setUser(data);
    return data;
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, toggleDarkMode, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}
