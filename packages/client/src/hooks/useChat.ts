import { useCallback } from "react";
import { apiFetch } from "../lib/api";
import { useAppStore } from "../stores/appStore";
import type { ChatResponse, Message } from "../types";

export function useChat() {
  const {
    conversationId,
    researchMode,
    addMessage,
    setConversationId,
    setKiraState,
    setLastModel,
    setLastLatencyMs,
    setActiveResearchId,
  } = useAppStore();

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        created_at: new Date().toISOString(),
      };
      addMessage(userMsg);
      setKiraState("thinking");

      // If research mode is on, generate an id so the UI can subscribe to
      // progress events while the POST is in flight.
      const researchId =
        researchMode !== "off" ? `r-${crypto.randomUUID()}` : null;
      if (researchId) setActiveResearchId(researchId);

      try {
        const res = await apiFetch<ChatResponse>("/api/chat", {
          method: "POST",
          body: JSON.stringify({
            message: trimmed,
            conversation_id: conversationId ?? undefined,
            research_id: researchId ?? undefined,
            research_mode: researchMode !== "off" ? researchMode : undefined,
          }),
        });
        addMessage(res.message);
        setConversationId(res.conversation_id);
        setLastModel(res.model_used);
        setLastLatencyMs(res.latency_ms);
        setKiraState("idle");
      } catch (e) {
        addMessage({
          id: crypto.randomUUID(),
          role: "assistant",
          content: `[error] ${(e as Error).message}`,
          created_at: new Date().toISOString(),
        });
        setKiraState("error");
      } finally {
        setActiveResearchId(null);
      }
    },
    [
      conversationId,
      researchMode,
      addMessage,
      setConversationId,
      setKiraState,
      setLastModel,
      setLastLatencyMs,
      setActiveResearchId,
    ],
  );

  return { send };
}
