import { Children, useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

/* border-slate-300 + bg-slate-50 (not bg-white) so the box reads against a white
 * Modal/Card/Drawer panel — a white input on a literal white panel border in
 * slate-200 was ~1.1:1 contrast, effectively invisible. slate-50 is already used
 * elsewhere as a "recessed" fill inside white cards (e.g. table row hover), so
 * this reuses an existing convention rather than inventing a new one. */
const inputClasses = `w-full rounded-lg border border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-800 dark:text-slate-100
  placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20
  dark:text-slate-100 dark:placeholder:text-slate-500`;

const errorClasses = "border-red-500 focus:border-red-500 focus:ring-red-500/20 dark:border-red-500";

/** Shared text/number/date input — standardizes border, radius, and focus ring.
 * Pass `error` (a message string) to switch the border/ring to the danger
 * color, set `aria-invalid`, and render the message underneath, wired via
 * `aria-describedby` — every call site gets inline validation for free.
 * Only wraps in a container when `error` is set — plain (no error) usage
 * stays a bare `<input>` so existing layout classNames (e.g. `flex-1` on a
 * flex-item Input) keep applying to the actual flex/grid item, not a new
 * wrapper div around it. */
export function Input({ className = "", error, id, ...props }) {
  const generatedId = useId();

  if (!error) {
    return <input id={id} className={`${inputClasses} ${className}`} {...props} />;
  }

  const errorId = `${id ?? generatedId}-error`;

  return (
    <div className={className}>
      <input
        id={id}
        className={`${inputClasses} ${errorClasses} w-full`}
        aria-invalid="true"
        aria-describedby={errorId}
        {...props}
      />
      <p id={errorId} className="mt-1.5 text-xs text-red-600 dark:text-red-400">{error}</p>
    </div>
  );
}

/** Reads { value, label, disabled } option descriptors off <option> children —
 * the same shape every call site in the app already passes to Select — so
 * Select can fully replace the native element without any call site changing. */
function extractOptions(children) {
  return Children.toArray(children)
    .filter((child) => child?.type === "option")
    .map((child) => ({
      value: child.props.value ?? "",
      label: child.props.children,
      disabled: !!child.props.disabled,
    }));
}

/**
 * Shared select — a custom-styled dropdown (not the native OS menu), per
 * docs/DESIGN.md's direction: rounded-lg/hairline-border/indigo-accent closed box,
 * a floating panel with the selected row highlighted in indigo + a check
 * mark. Reuses the same click-outside/Escape-to-close pattern established by
 * Dashboard.jsx's AddRecordMenu / Sidebar.jsx's ProfileMenu (see docs/DESIGN.md's
 * "Navigation" section — "reuse that pattern for any future dropdown rather
 * than inventing a new one"). Drop-in for the native <select> it replaces:
 * same props (name/value/onChange/children as <option>), so no call site
 * needs to change — onChange still receives an event-shaped
 * { target: { name, value } }.
 */
export function Select({ className = "", error, id, children, name, value, onChange, disabled = false, ...rest }) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const wrapperRef = useRef(null);
  const listboxId = useId();
  const generatedId = useId();
  const errorId = error ? `${id ?? generatedId}-error` : undefined;
  const options = extractOptions(children);
  const selectable = options.filter((o) => !o.disabled);
  const selected = options.find((o) => String(o.value) === String(value));

  useEffect(() => {
    function onClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
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

  function selectOption(option) {
    setOpen(false);
    setActiveIndex(-1);
    onChange?.({ target: { name, value: option.value, type: "select-one" } });
  }

  function openAt(index) {
    setOpen(true);
    setActiveIndex(index);
  }

  const selectedIndex = selectable.findIndex((o) => String(o.value) === String(value));

  function handleKeyDown(e) {
    if (disabled) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openAt(selectedIndex >= 0 ? selectedIndex : 0);
        else setActiveIndex((i) => Math.min(i + 1, selectable.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!open) openAt(selectedIndex >= 0 ? selectedIndex : selectable.length - 1);
        else setActiveIndex((i) => Math.max(i - 1, 0));
        break;
      case "Home":
        if (open) { e.preventDefault(); setActiveIndex(0); }
        break;
      case "End":
        if (open) { e.preventDefault(); setActiveIndex(selectable.length - 1); }
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (open && activeIndex >= 0) selectOption(selectable[activeIndex]);
        else openAt(selectedIndex >= 0 ? selectedIndex : 0);
        break;
      case "Escape":
        setOpen(false);
        break;
      case "Tab":
        setOpen(false);
        break;
      default:
        break;
    }
  }

  return (
    <div className={className}>
    <div
      ref={wrapperRef}
      id={id}
      className={`relative ${inputClasses} h-11.5 w-full focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20 ${
        error ? errorClasses : ""
      } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
    >
      <button
        type="button"
        name={name}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openAt(selectedIndex >= 0 ? selectedIndex : 0))}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open && activeIndex >= 0 ? `${listboxId}-opt-${activeIndex}` : undefined}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={errorId}
        className="flex h-full w-full items-center justify-between gap-2 rounded-lg bg-transparent text-left focus:outline-none disabled:cursor-not-allowed"
        {...rest}
      >
        <span className={`truncate ${!selected || selected.disabled ? "text-slate-400 dark:text-slate-500" : ""}`}>
          {selected ? selected.label : ""}
        </span>
        <ChevronDown
          size={16}
          strokeWidth={1.8}
          className={`shrink-0 text-slate-500 transition-transform dark:text-slate-400 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute inset-x-0 top-full z-10 mt-1 max-h-60 overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-md dark:border-slate-700 dark:bg-slate-800"
        >
          {selectable.map((option, index) => {
            const isSelected = String(option.value) === String(value);
            const isActive = index === activeIndex;
            return (
              <div
                key={option.value}
                id={`${listboxId}-opt-${index}`}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => selectOption(option)}
                className={`flex cursor-pointer items-center justify-between gap-2 px-3.5 py-2.5 text-sm ${
                  isActive
                    ? "bg-indigo-600 text-white"
                    : isSelected
                    ? "bg-indigo-100/60 font-medium text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300"
                    : "text-slate-700 dark:text-slate-300"
                }`}
              >
                <span className="truncate">{option.label}</span>
                {isSelected && <Check size={15} strokeWidth={2} className="shrink-0" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
    {error && <p id={errorId} className="mt-1.5 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

/** Shared textarea — same visual language and error-state contract as Input. */
export function Textarea({ className = "", error, id, ...props }) {
  const generatedId = useId();

  if (!error) {
    return <textarea id={id} className={`${inputClasses} ${className}`} {...props} />;
  }

  const errorId = `${id ?? generatedId}-error`;

  return (
    <div className={className}>
      <textarea
        id={id}
        className={`${inputClasses} ${errorClasses} w-full`}
        aria-invalid="true"
        aria-describedby={errorId}
        {...props}
      />
      <p id={errorId} className="mt-1.5 text-xs text-red-600 dark:text-red-400">{error}</p>
    </div>
  );
}
