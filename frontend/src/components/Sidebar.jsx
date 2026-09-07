import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate, Link } from "react-router-dom";
import {
  LayoutDashboard,
  Wallet,
  BookOpen,
  CheckSquare,
  BrainCircuit,
  MessageSquare,
  Activity,
  Target,
  Sun,
  Moon,
  Settings,
  LogOut,
  User,
  ChevronUp,
  ChevronsLeft,
  ChevronsRight,
  X,
} from "lucide-react";
import { useAuth } from "../context/useAuth";

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

// Grouped by purpose rather than one flat list: Overview (glance at everything),
// Track (log/review data), Foresight (what the model predicts). Identity
// (My Profile / Settings / Logout) lives in the profile dropdown at the
// bottom of the sidebar instead of its own nav group.
// Assistant is rendered separately below, since it's the one preview/experimental
// feature rather than a fully-real section.
const menuGroups = [
  {
    label: "Overview",
    items: [
      { name: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
      { name: "Goals",     path: "/goals",      icon: Target },
      { name: "Activity",  path: "/activity",   icon: Activity },
    ],
  },
  {
    label: "Track",
    items: [
      { name: "Finance", path: "/finance", icon: Wallet },
      { name: "Study",   path: "/study",   icon: BookOpen },
      { name: "Habits",  path: "/habits",  icon: CheckSquare },
    ],
  },
  {
    label: "Foresight",
    items: [
      { name: "Prediction", path: "/prediction", icon: BrainCircuit },
    ],
  },
];

/**
 * Label/heading visibility follows `expanded` only at the lg breakpoint and up.
 * Below lg the sidebar only ever renders as the full-width mobile drawer (see
 * MainLayout), so labels always show there regardless of the desktop
 * expanded/collapsed preference.
 */
function labelClasses(expanded, extra = "") {
  return `whitespace-nowrap ${expanded ? "" : "lg:hidden"} ${extra}`;
}

function navLinkClasses(expanded) {
  return ({ isActive }) =>
    `mb-1 flex items-center gap-3.5 rounded-lg px-3 py-3 text-[15px] no-underline transition-colors justify-start ${
      expanded ? "" : "lg:justify-center"
    } ${
      isActive
        ? "bg-indigo-100 font-semibold text-indigo-700 dark:bg-[#1E3330] dark:text-[#5EEAD4]"
        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
    }`;
}

/** Avatar + name trigger at the bottom of the sidebar — opens upward (it's
 * pinned to the bottom of the screen) with My Profile / Settings / Logout. */
function ProfileMenu({ name, initials, expanded, onLogout }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`flex w-full items-center gap-3 rounded-lg px-1 py-1.5 transition-colors hover:bg-slate-100 dark:hover:bg-white/10 justify-start ${
          expanded ? "" : "lg:justify-center"
        }`}
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[13px] font-bold text-white">
          {initials}
        </div>
        <div className={`min-w-0 flex-1 text-left ${expanded ? "" : "lg:hidden"}`}>
          <h4 className="truncate text-[13px] font-medium text-slate-800 dark:text-slate-100">{name}</h4>
          <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">Digital Twin User</p>
        </div>
        <ChevronUp
          size={16}
          strokeWidth={1.8}
          className={`shrink-0 text-slate-500 transition-transform dark:text-slate-400 ${expanded ? "" : "lg:hidden"} ${open ? "" : "rotate-180"}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-10 mb-2 w-48 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-md dark:border-slate-700 dark:bg-slate-800"
        >
          <Link
            role="menuitem"
            to="/profile"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-700/40"
          >
            <User size={16} strokeWidth={1.8} /> My Profile
          </Link>
          <Link
            role="menuitem"
            to="/settings"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-700/40"
          >
            <Settings size={16} strokeWidth={1.8} /> Settings
          </Link>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="flex w-full items-center gap-2.5 border-t border-slate-100 px-4 py-2.5 text-left text-sm text-red-600 hover:bg-slate-50 dark:border-slate-700 dark:text-red-400 dark:hover:bg-slate-700/40"
          >
            <LogOut size={16} strokeWidth={1.8} /> Log out
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * `expanded` / `onToggleExpanded` control the persistent desktop (lg+) rail
 * width (icon-only vs. icon+label) — a real toggle instead of the old
 * hover-to-widen behavior, so keyboard and touch users can reach the labels
 * too. `mobileOpen` / `onCloseMobile` control the below-lg off-canvas drawer,
 * which always renders full-width regardless of `expanded`.
 */
function Sidebar({ expanded, onToggleExpanded, mobileOpen, onCloseMobile }) {
  const { user, logout, toggleDarkMode } = useAuth();
  const navigate = useNavigate();
  const isDark = Boolean(user?.preferences?.dark_mode);
  const asideRef = useRef(null);
  const triggerRef = useRef(null);
  const linkClasses = navLinkClasses(expanded);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const name     = user?.profile?.name ?? "Digital Twin User";
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  // Mobile drawer: trap focus, close on Escape, restore focus to whatever
  // opened it — same contract as Modal.jsx/Drawer.jsx. Desktop rail isn't a
  // modal overlay, so this only runs while the drawer is actually open.
  useEffect(() => {
    if (!mobileOpen) return;

    triggerRef.current = document.activeElement;

    const panel = asideRef.current;
    const focusables = panel?.querySelectorAll(FOCUSABLE);
    (focusables?.[0] || panel)?.focus();

    function handleKeyDown(e) {
      if (e.key === "Escape") {
        onCloseMobile?.();
        return;
      }
      if (e.key !== "Tab" || !panel) return;

      const items = Array.from(panel.querySelectorAll(FOCUSABLE));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      triggerRef.current?.focus?.();
    };
  }, [mobileOpen, onCloseMobile]);

  return (
    <aside
      ref={asideRef}
      role={mobileOpen ? "dialog" : undefined}
      aria-modal={mobileOpen ? "true" : undefined}
      aria-label="Main navigation"
      tabIndex={-1}
      className={`fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-slate-200 bg-white text-slate-800 transition-[width,transform] duration-200 ease-out focus:outline-none dark:border-r-0 dark:bg-slate-900 dark:text-white ${
        mobileOpen ? "translate-x-0" : "-translate-x-full"
      } lg:translate-x-0 ${expanded ? "lg:w-64" : "lg:w-16"}`}
    >
      <div className={`flex items-center gap-3 border-b border-slate-200 px-4 py-6 dark:border-white/10 ${expanded ? "" : "lg:px-3"}`}>
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-sm font-bold text-white">
          DT
        </div>

        <div className={`min-w-0 flex-1 ${labelClasses(expanded)}`}>
          <h2 className="text-[19px] font-semibold">Digital Twin</h2>
          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">AI Decision Assistant</p>
        </div>

        <button
          type="button"
          onClick={onCloseMobile}
          aria-label="Close menu"
          className="ml-auto shrink-0 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 lg:hidden dark:hover:bg-white/10"
        >
          <X size={18} strokeWidth={1.8} />
        </button>
      </div>

      {/* The scroll container lives here rather than on the <aside>. Setting
          overflow-y on the aside made its computed overflow-x `auto` too, turning
          it into a clipping context in both directions — which cropped the
          profile menu to the rail's width when collapsed (a 192px menu inside a
          64px rail showed only the first letter of each item). Scrolling the nav
          instead also keeps the header and footer pinned. min-h-0 is required:
          without it a flex item won't shrink below its content height, so the
          overflow never triggers. */}
      <nav
        className={`min-h-0 flex-1 overflow-y-auto px-2 py-6 ${expanded ? "" : "lg:px-2.5"}`}
        aria-label="Main"
      >
        {menuGroups.map((group) => (
          <div key={group.label} className="mb-5">
            <p className={labelClasses(expanded, "mb-2 pl-3 text-[11px] font-bold tracking-wider text-slate-500 dark:text-slate-400")}>
              {group.label.toUpperCase()}
            </p>

            {group.items.map(({ name, path, icon: Icon }) => (
              <NavLink key={name} to={path} aria-label={name} onClick={onCloseMobile} className={linkClasses}>
                <span className="flex w-5 shrink-0 justify-center">
                  <Icon size={18} strokeWidth={1.8} />
                </span>
                <span className={labelClasses(expanded)}>{name}</span>
              </NavLink>
            ))}
          </div>
        ))}

        <div className="mt-2 border-t border-slate-200 pt-4 dark:border-white/10">
          <NavLink to="/assistant" aria-label="AI Assistant (preview)" onClick={onCloseMobile} className={linkClasses}>
            <span className="flex w-5 shrink-0 justify-center">
              <MessageSquare size={18} strokeWidth={1.8} />
            </span>
            <span className={labelClasses(expanded, "flex items-center gap-2")}>
              AI Assistant
            </span>
          </NavLink>
        </div>
      </nav>

      <div className={`border-t border-slate-200 px-2 py-4 dark:border-white/10 ${expanded ? "" : "lg:px-2.5"}`}>
        <button
          type="button"
          onClick={onToggleExpanded}
          aria-pressed={expanded}
          className={`mb-2 hidden h-9 w-full items-center gap-2.5 rounded-lg border border-slate-200 px-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 lg:flex dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white ${
            expanded ? "justify-start" : "justify-center"
          }`}
        >
          {expanded ? <ChevronsLeft size={17} strokeWidth={1.8} /> : <ChevronsRight size={17} strokeWidth={1.8} />}
          <span className={labelClasses(expanded, "text-xs")}>Collapse</span>
        </button>

        <button
          type="button"
          onClick={toggleDarkMode}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          title={isDark ? "Switch to light mode" : "Switch to dark mode"}
          className={`mb-2 flex h-9 w-full items-center gap-2.5 rounded-lg px-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 justify-start dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white ${
            expanded ? "" : "lg:justify-center"
          }`}
        >
          {isDark ? <Sun size={17} strokeWidth={1.8} /> : <Moon size={17} strokeWidth={1.8} />}
          <span className={labelClasses(expanded, "text-xs")}>{isDark ? "Light mode" : "Dark mode"}</span>
        </button>

        <ProfileMenu name={name} initials={initials} expanded={expanded} onLogout={handleLogout} />
      </div>
    </aside>
  );
}

export default Sidebar;
