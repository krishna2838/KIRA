import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import type { Memory } from "../types";

export function useMemory() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch<{ memories: Memory[] }>(
        "/api/memory/all?limit=100",
      );
      setMemories(res.memories);
    } finally {
      setLoading(false);
    }
  }, []);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) return load();
    setLoading(true);
    try {
      const res = await apiFetch<{ memories: Memory[] }>(
        `/api/memory/search?q=${encodeURIComponent(q)}&limit=50`,
      );
      setMemories(res.memories);
    } finally {
      setLoading(false);
    }
  }, [load]);

  const remove = useCallback(async (id: string) => {
    await apiFetch(`/api/memory/${id}`, { method: "DELETE" });
    setMemories((prev) => prev.filter((m) => m.id !== id));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { memories, loading, load, search, remove };
}
