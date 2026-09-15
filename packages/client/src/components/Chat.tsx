import { useEffect, useRef } from "react";
import { useAppStore } from "../stores/appStore";
import { useChat } from "../hooks/useChat";
import { Avatar } from "./Avatar";
import { InputBar } from "./InputBar";
import { MessageBubble } from "./MessageBubble";
import { ProactiveSuggestions } from "./ProactiveSuggestions";
import { ResearchProgress } from "./ResearchProgress";

export function Chat() {
  const { messages, kiraState, activeResearchId } = useAppStore();
  const { send } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  const askAbout = (prompt: string) => {
    void send(prompt);
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length]);

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center gap-3 px-6 py-3 border-b border-kira-border">
        <Avatar state={kiraState} size={44} />
        <div className="text-sm font-medium">KIRA</div>
        <div className="text-xs text-kira-muted ml-2">{kiraState}</div>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto kira-scroll px-6 py-6"
      >
        <div className="max-w-4xl mx-auto">
          <ProactiveSuggestions onAsk={askAbout} />
          {messages.length === 0 ? (
            <div className="text-center text-kira-muted mt-24">
              Say something. KIRA is listening.
            </div>
          ) : (
            messages.map((m) => <MessageBubble key={m.id} msg={m} />)
          )}
          {activeResearchId && <ResearchProgress researchId={activeResearchId} />}
        </div>
      </div>

      <InputBar onSend={send} disabled={kiraState === "thinking"} />
    </div>
  );
}
