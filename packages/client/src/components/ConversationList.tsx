import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

interface ConversationSummary {
  id: string;
  title: string | null;
  summary: string | null;
  started_at: string | null;
  message_count: number;
}

export function ConversationList({
  onOpen,
}: {
  onOpen?: (id: string) => void;
}) {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50" });
    if (q) params.set("q", q);
    try {
      const r = await apiFetch<{ conversations: ConversationSummary[] }>(
        `/api/conversations?${params}`,
      );
      setItems(r.conversations);
    } catch {
      /* ignore */
    }
  }, [q]);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="mt-2">
      <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2">
        Conversations
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && load()}
        placeholder="search…"
        className="w-full bg-kira-bg border border-kira-border rounded px-2 py-1 text-[11px] mb-2 focus:outline-none focus:border-kira-accent"
      />
      {items.length === 0 && (
        <div className="text-[10px] text-kira-muted italic">No conversations yet.</div>
      )}
      <div className="space-y-1 max-h-64 overflow-y-auto kira-scroll">
        {items.map((c) => (
          <button
            key={c.id}
            onClick={() => onOpen?.(c.id)}
            className="w-full text-left px-2 py-1.5 rounded hover:bg-kira-bg text-[11px]"
          >
            <div className="truncate text-kira-text">
              {c.title || c.summary || "(untitled)"}
            </div>
            <div className="text-[9px] text-kira-muted">
              {c.message_count} msgs
              {c.started_at
                ? ` · ${new Date(c.started_at).toLocaleDateString()}`
                : ""}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
