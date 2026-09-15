import { useEffect, useRef, useState } from "react";
import { getWsUrl } from "../lib/api";
import type { ResearchProgressEvent } from "../types";

export function useResearchProgress(researchId: string | null) {
  const [events, setEvents] = useState<ResearchProgressEvent[]>([]);
  const [done, setDone] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!researchId) return;
    setEvents([]);
    setDone(false);

    const ws = new WebSocket(getWsUrl(`/api/research/stream/${researchId}`));
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const evt: ResearchProgressEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, evt]);
        if (evt.stage === "done") {
          setDone(true);
          ws.close();
        }
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => setDone(true);

    return () => {
      ws.close();
    };
  }, [researchId]);

  return { events, done };
}
