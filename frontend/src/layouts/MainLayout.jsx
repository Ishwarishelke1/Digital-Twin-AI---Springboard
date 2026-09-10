import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Menu } from "lucide-react";

import Sidebar from "../components/Sidebar";
import AssistantLauncher from "../components/AssistantLauncher";
import { AssistantChatProvider } from "../context/AssistantChatContext";

const EXPANDED_KEY = "digital_twin_sidebar_expanded";

function readStoredExpanded() {
  try {
    const raw = localStorage.getItem(EXPANDED_KEY);
    return raw === null ? true : raw === "true";
  } catch {
    return true;
  }
}

function MainLayout() {
  const [expanded, setExpanded] = useState(readStoredExpanded);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(EXPANDED_KEY, String(expanded));
    } catch {
      // Storage unavailable (private browsing, quota) — the toggle still
      // works for this session, it just won't be remembered next visit.
    }
  }, [expanded]);

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-900">
      <Sidebar
        expanded={expanded}
        onToggleExpanded={() => setExpanded((e) => !e)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <div
        className={`min-h-screen min-w-0 w-full transition-[margin-left] duration-200 ease-out ${
          expanded ? "lg:ml-64" : "lg:ml-16"
        }`}
      >
        <div className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 lg:hidden dark:border-slate-700 dark:bg-slate-900">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10"
          >
            <Menu size={20} strokeWidth={1.8} />
          </button>
          <span className="font-serif text-[15px] font-semibold text-slate-800 dark:text-slate-100">Digital Twin</span>
        </div>

        {/* One provider for both surfaces that read/write the assistant
            conversation: the page content below (Assistant.jsx, via Outlet)
            and the floating launcher, fixed-positioned outside <main> since
            it isn't part of the page flow — both need to be inside this for
            "ask in the launcher, see it on the page" to actually be true. */}
        <AssistantChatProvider>
          <main className="p-4 sm:p-6 lg:p-8">
            <Outlet />
          </main>

          <AssistantLauncher />
        </AssistantChatProvider>
      </div>
    </div>
  );
}

export default MainLayout;
