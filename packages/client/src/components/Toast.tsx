import { create } from "zustand";
import { useEffect } from "react";

export type ToastKind = "info" | "success" | "error";

interface ToastItem {
  id: string;
  kind: ToastKind;
  text: string;
  timeoutMs: number;
}

interface ToastStore {
  items: ToastItem[];
  push: (t: Omit<ToastItem, "id"> & { id?: string }) => void;
  dismiss: (id: string) => void;
}

export const useToasts = create<ToastStore>((set) => ({
  items: [],
  push: (t) =>
    set((s) => ({
      items: [
        ...s.items,
        { id: t.id ?? crypto.randomUUID(), timeoutMs: 4000, ...t },
      ].slice(-6),
    })),
  dismiss: (id) => set((s) => ({ items: s.items.filter((x) => x.id !== id) })),
}));

/** Global helpers — safe to call anywhere. */
export const toast = {
  info: (text: string) => useToasts.getState().push({ kind: "info", text, timeoutMs: 4000 }),
  success: (text: string) => useToasts.getState().push({ kind: "success", text, timeoutMs: 3000 }),
  error: (text: string) => useToasts.getState().push({ kind: "error", text, timeoutMs: 6000 }),
};

const TONE: Record<ToastKind, string> = {
  info: "border-cyan-500/60 text-cyan-100 bg-cyan-500/10",
  success: "border-emerald-500/60 text-emerald-100 bg-emerald-500/10",
  error: "border-red-500/60 text-red-100 bg-red-500/10",
};

export function ToastHost() {
  const { items, dismiss } = useToasts();

  useEffect(() => {
    const timers = items.map((t) =>
      window.setTimeout(() => dismiss(t.id), t.timeoutMs),
    );
    return () => timers.forEach(window.clearTimeout);
  }, [items, dismiss]);

  return (
    <div className="fixed top-3 right-3 z-50 flex flex-col gap-2 max-w-sm">
      {items.map((t) => (
        <div
          key={t.id}
          className={`px-3 py-2 rounded-lg border text-xs shadow ${TONE[t.kind]}`}
        >
          <div className="flex justify-between gap-3">
            <div className="flex-1">{t.text}</div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-kira-muted hover:text-kira-text"
            >
              ×
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
