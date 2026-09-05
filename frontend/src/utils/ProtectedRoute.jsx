import { Navigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";

/**
 * Gates protected routes on AuthContext's session state, rather than reading a
 * token directly (auth is an httpOnly cookie now — JS can't read it at all, so
 * there's nothing to decode/check expiry on here; AuthContext's restoreSession
 * already asked the backend and knows whether the session is valid).
 */
function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuth();

  // Themed full-page hold while the session is validated. An unstyled <h2> here
  // flashes raw text on the browser's default background before the app shell
  // paints, on every single load.
  if (isLoading) {
    return (
      <div
        className="flex min-h-dvh items-center justify-center bg-slate-50 dark:bg-slate-900"
        role="status"
        aria-live="polite"
      >
        <span className="text-sm font-medium text-slate-500 dark:text-slate-400">Loading…</span>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default ProtectedRoute;
