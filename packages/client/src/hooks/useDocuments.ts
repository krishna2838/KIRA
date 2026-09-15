import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, getWsUrl } from "../lib/api";
import type { DocumentIndexEvent, IndexedFile } from "../types";

export function useDocuments(pollMs: number = 30_000) {
  const [files, setFiles] = useState<IndexedFile[]>([]);
  const [events, setEvents] = useState<DocumentIndexEvent[]>([]);
  const [inFlight, setInFlight] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await apiFetch<{ files: IndexedFile[] }>("/api/documents");
      setFiles(r.files);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  useEffect(() => {
    const ws = new WebSocket(getWsUrl("/api/documents/progress"));
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        const evt: DocumentIndexEvent = JSON.parse(e.data);
        if (evt.stage === "heartbeat") return;
        setEvents((prev) => [...prev.slice(-40), evt]);
        if (evt.stage === "start") setInFlight((n) => n + 1);
        if (evt.stage === "done") {
          setInFlight((n) => Math.max(0, n - 1));
          refresh();
        }
        if (evt.stage === "indexed") refresh();
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, [refresh]);

  const indexFile = useCallback(async (path: string) => {
    await apiFetch("/api/documents/index_file", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  }, []);

  const indexDirectory = useCallback(async (path: string) => {
    await apiFetch("/api/documents/index_directory", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  }, []);

  return { files, events, inFlight, refresh, indexFile, indexDirectory };
}
