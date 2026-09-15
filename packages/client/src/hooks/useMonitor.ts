import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

export interface ProactiveEvent {
  type: string;
  importance: number;
  title: string;
  message: string;
  detail?: Record<string, unknown>;
  generated_at: string;
}

export function useMonitor(pollMs: number = 30_000) {
  const [events, setEvents] = useState<ProactiveEvent[]>([]);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      try {
        const [q, n] = await Promise.all([
          apiFetch<{ events: ProactiveEvent[] }>("/api/monitor/queue"),
          apiFetch<{ unread: number }>("/api/notifications?limit=1&since_hours=6"),
        ]);
        if (cancelled) return;
        if (q.events.length) {
          setEvents((prev) => [...q.events, ...prev].slice(0, 30));
        }
        setUnread(n.unread || 0);
      } catch {
        /* ignore */
      }
    };

    tick();
    const id = setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pollMs]);

  const dismiss = (i: number) =>
    setEvents((prev) => prev.filter((_, idx) => idx !== i));

  return { events, unread, dismiss };
}
