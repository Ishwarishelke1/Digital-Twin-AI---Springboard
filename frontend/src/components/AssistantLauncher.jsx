import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { MessageSquare, X } from "lucide-react";

import ChatBox from "./ChatBox";
import ChatInput from "./ChatInput";
import { useAssistantChatContext } from "../context/useAssistantChatContext";

/**
 * The AI Assistant, reachable from every protected page without navigating
 * away — mounted once in MainLayout.jsx, which is why it survives a route
 * change instead of resetting like the full /assistant page does. Its own
 * useAssistantChat() instance means the conversation you're mid-way through
 * on Finance is still there if you check Study next, for as long as the tab
 * stays open (see the hook's own docstring for why that's not saved anywhere
 * beyond that).
 *
 * Deliberately a compact panel, not a re-render of the full page: no
 * QuickActions/SuggestionCard grid here — those belong to the page you
 * navigate to on purpose, not a quick in-context ask. The sidebar's "AI
 * Assistant" link and the full page are unchanged; this is an additional way
 * in, not a replacement.
 */
function AssistantLauncher() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef(null);
  const { pathname } = useLocation();
  const { messages, isThinking, sendMessage } = useAssistantChatContext();

  // /assistant already *is* this chat — a floating button offering to open a
  // second, separate copy of it there would be redundant, not additive.
  const onAssistantPage = pathname === "/assistant";

  useEffect(() => {
    if (!open) return;

    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    function onClickOutside(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onClickOutside);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onClickOutside);
    };
  }, [open]);

  if (onAssistantPage) return null;

  return (
    <div className="fixed bottom-5 right-5 z-40 sm:bottom-6 sm:right-6">
      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label="AI Assistant"
          className="animate-modal-in absolute bottom-16 right-0 flex h-[min(32rem,70vh)] w-[min(24rem,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-black/5 dark:bg-slate-800 dark:ring-white/10"
        >
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-700">
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">AI Assistant</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close AI Assistant"
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-300"
            >
              <X size={17} strokeWidth={1.8} />
            </button>
          </div>

          {/* No overflow-y-auto here — ChatBox's own root div owns the scroll
              region in bare mode (see its docstring), so this only needs to
              size and pad the space ChatBox fills. Two nested overflow-auto
              containers here previously meant the outer one never actually
              scrolled (it always sized exactly to its flex parent) while the
              real scrolling — and the auto-scroll effect's ref — lived on the
              inner one; harmless to look at, but dead, confusing CSS. */}
          <div className="min-h-0 flex-1 p-4">
            <ChatBox messages={messages} isThinking={isThinking} bare />
          </div>

          <div className="border-t border-slate-100 p-3 dark:border-slate-700">
            <ChatInput sendMessage={sendMessage} disabled={isThinking} />
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close AI Assistant" : "Open AI Assistant"}
        aria-expanded={open}
        className="flex h-13 w-13 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg transition-transform hover:scale-105 hover:bg-indigo-700 focus-visible:scale-105"
      >
        {open ? <X size={22} strokeWidth={1.8} /> : <MessageSquare size={22} strokeWidth={1.8} />}
      </button>
    </div>
  );
}

export default AssistantLauncher;
