import { useEffect, useRef } from "react";
import { getWsUrl } from "../lib/api";

// Phase 1: minimal reusable WS hook. Chat currently uses POST /api/chat;
// this is here for future streaming.
export function useWebSocket(path: string, onMessage?: (data: unknown) => void) {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(getWsUrl(path));
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        onMessage?.(JSON.parse(e.data));
      } catch {
        onMessage?.(e.data);
      }
    };
    return () => {
      ws.close();
    };
  }, [path, onMessage]);

  return wsRef;
}
