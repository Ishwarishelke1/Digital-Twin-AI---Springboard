/**
 * src/context/assistantChatContextInstance.js
 * The raw React context object, split out from AssistantChatContext.jsx (the
 * provider component) and useAssistantChatContext.js (the hook) — same
 * three-file split as context/authContextInstance.js, required for Vite Fast
 * Refresh to treat each file as component-only / hook-only.
 */
import { createContext } from "react";

export const AssistantChatContext = createContext();
