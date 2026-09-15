import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import type { ProactiveScoredEvent } from "../types";

export function useProactive(pollMs: number = 20_000) {
  const [queue, setQueue] = useState<ProactiveScoredEvent[]>([]);
  const [pending, setPending] = useState<ProactiveScoredEvent[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const [q, p] = await Promise.all([
        apiFetch<{ events: ProactiveScoredEvent[] }>("/api/monitor/queue"),
        apiFetch<{ events: ProactiveScoredEvent[] }>("/api/proactive/peek"),
      ]);
      if (q.events?.length) {
        setQueue((prev) => [...q.events, ...prev].slice(0, 40));
      }
      setPending(p.events || []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
  }, [load, pollMs]);

  const dismiss = (evt: ProactiveScoredEvent) => {
    const key = evt.dedupe_key || `${evt.kind}:${evt.generated_at}`;
    setDismissed((prev) => new Set(prev).add(key));
    setQueue((prev) => prev.filter((e) => (e.dedupe_key || `${e.kind}:${e.generated_at}`) !== key));
  };

  const visible = queue.filter(
    (e) => !dismissed.has(e.dedupe_key || `${e.kind}:${e.generated_at}`),
  );
  const unread = visible.length + pending.length;

  return { queue: visible, pending, unread, dismiss, reload: load };
}
