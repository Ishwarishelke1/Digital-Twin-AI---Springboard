import { useEffect, useRef, useState } from "react";
import { Filter, ChevronDown } from "lucide-react";
import Button from "./Button";

/** Shared "close on click-outside or Escape" wiring, used by both pieces below
 *  and matching the pattern in Sidebar's ProfileMenu and Dashboard's AddRecordMenu. */
function useDismissable(onDismiss) {
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) onDismiss();
    }
    function onKey(e) {
      if (e.key === "Escape") onDismiss();
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [onDismiss]);

  return ref;
}

/**
 * A filter select styled to match the page rather than the OS. Deliberately not
 * `ui/Field`'s Select: this one lives inside an already-floating menu, where a
 * second nested popup layer needs its own z-index and its own dismissal, and it
 * always carries an "all" row whose value is the empty string.
 *
 * Calls onChange with a `{ target: { value } }` shape, so it is a drop-in for a
 * native select's handler and no caller needs a different signature.
 */
export function FilterDropdown({ label, value, options, placeholder, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useDismissable(() => setOpen(false));
  const selectedLabel = value ? (options.find((o) => o.value === value)?.label ?? value) : placeholder;

  function choose(optionValue) {
    onChange({ target: { value: optionValue } });
    setOpen(false);
  }

  const rowClasses = (isSelected) =>
    `block w-full px-3.5 py-2 text-left text-sm ${
      isSelected
        ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300"
        : "text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-700/40"
    }`;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-left text-sm text-slate-800 transition-colors hover:border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:border-slate-500"
      >
        <span className="truncate">{selectedLabel}</span>
        <ChevronDown
          size={15}
          strokeWidth={1.8}
          className={`shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={label}
          className="absolute left-0 right-0 z-20 mt-1.5 max-h-56 overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-md dark:border-slate-700 dark:bg-slate-800"
        >
          <button
            type="button"
            role="option"
            aria-selected={!value}
            onClick={() => choose("")}
            className={rowClasses(!value)}
          >
            {placeholder}
          </button>

          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="option"
              aria-selected={value === opt.value}
              onClick={() => choose(opt.value)}
              className={rowClasses(value === opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Filter icon holding a menu of FilterDropdowns. The dot on the icon is the only
 * indication a filter is active once the menu is closed, so `hasActiveFilter`
 * must reflect every filter the menu owns — otherwise a table shows a subset of
 * its rows with nothing on screen explaining why.
 *
 * Filter state stays with the caller; this is presentation only.
 */
export function FilterMenu({ label, hasActiveFilter, onClearFilters, children }) {
  const [open, setOpen] = useState(false);
  const ref = useDismissable(() => setOpen(false));

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={label}
        className="relative flex h-10.5 w-10.5 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/40 dark:hover:text-slate-200"
      >
        <Filter size={17} strokeWidth={1.8} />
        {hasActiveFilter && (
          <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-indigo-600" aria-hidden="true" />
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-10 mt-2 w-56 rounded-lg border border-slate-200 bg-white p-3 shadow-md dark:border-slate-700 dark:bg-slate-800"
        >
          <div className="flex flex-col gap-2.5">
            {children}

            {hasActiveFilter && (
              <Button type="button" variant="secondary" onClick={onClearFilters} className="w-full">
                Clear filters
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default FilterMenu;
