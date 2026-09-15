import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, getWsUrl } from "../lib/api";
import { useAppStore } from "../stores/appStore";
import type { KiraState } from "../types";

interface VoiceStatus {
  available: boolean;
  state?: string;
  active?: boolean;
  wake_word_enabled?: boolean;
  last_transcript?: string;
  reason?: string;
}

const SERVER_TO_KIRA_STATE: Record<string, KiraState> = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
  error: "error",
};

export function useVoice() {
  const [status, setStatus] = useState<VoiceStatus>({ available: false });
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const { setKiraState } = useAppStore();

  const refresh = useCallback(async () => {
    try {
      const s = await apiFetch<VoiceStatus>("/api/voice/status");
      setStatus(s);
    } catch {
      setStatus({ available: false, reason: "unreachable" });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const connect = useCallback(() => {
    if (wsRef.current) return;
    const ws = new WebSocket(getWsUrl("/api/voice/stream"));
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
    };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "state") {
          setStatus((prev) => ({ ...prev, ...msg }));
          const mapped = SERVER_TO_KIRA_STATE[msg.state];
          if (mapped) setKiraState(mapped);
        }
      } catch {
        /* ignore */
      }
    };
  }, [setKiraState]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const start = useCallback(async () => {
    await apiFetch("/api/voice/start", { method: "POST" });
    connect();
    refresh();
  }, [connect, refresh]);

  const stop = useCallback(async () => {
    await apiFetch("/api/voice/stop", { method: "POST" });
    disconnect();
    refresh();
    setKiraState("idle");
  }, [disconnect, refresh, setKiraState]);

  const setWakeWord = useCallback(
    async (enabled: boolean) => {
      const s = await apiFetch<VoiceStatus>("/api/voice/settings", {
        method: "POST",
        body: JSON.stringify({ wake_word_enabled: enabled }),
      });
      setStatus((prev) => ({ ...prev, ...s }));
    },
    [],
  );

  const interrupt = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "stop" }));
  }, []);

  useEffect(
    () => () => {
      wsRef.current?.close();
    },
    [],
  );

  return {
    status,
    connected,
    start,
    stop,
    setWakeWord,
    interrupt,
    refresh,
  };
}
