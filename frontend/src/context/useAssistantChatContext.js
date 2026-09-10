/**
 * src/context/useAssistantChatContext.js
 * Hook for consuming AssistantChatContext.
 */
import { useContext } from "react";
import { AssistantChatContext } from "./assistantChatContextInstance";

export function useAssistantChatContext() {
  return useContext(AssistantChatContext);
}
