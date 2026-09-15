import { useState } from "react";
import { useProactive } from "../hooks/useProactive";
import type { ProactiveScoredEvent } from "../types";

const TONE: Record<string, string> = {
  notify: "border-cyan-500/50",
  suggest: "border-amber-500/60",
  act: "border-emerald-500/60",
  silent: "border-kira-border",
};

function scoreLabel(e: ProactiveScoredEvent): string {
  const s = Math.round((e.score ?? 0) * 100);
  return `${e.intervention.toUpperCase()} · ${s}%`;
}

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const { queue, pending, unread, dismiss } = useProactive();
  const all = [...queue, ...pending];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`relative flex items-center gap-1 text-[11px] px-2 py-1 rounded border ${
          unread > 0
            ? "border-kira-accent text-kira-accent"
            : "border-kira-border text-kira-muted"
        } hover:text-kira-text`}
        title="Notifications"
      >
        <span>🔔</span>
        {unread > 0 && (
          <span className="ml-1 px-1 rounded-full bg-kira-accent text-black text-[9px] font-medium">
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 bottom-full mb-2 w-[340px] max-h-[70vh] overflow-y-auto rounded-xl border border-kira-border bg-kira-panel shadow-xl z-50">
          <div className="px-3 py-2 border-b border-kira-border flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider text-kira-muted">
              Notifications
            </span>
            <button
              onClick={() => setOpen(false)}
              className="text-kira-muted hover:text-kira-text text-sm"
            >
              ×
            </button>
          </div>
          {all.length === 0 ? (
            <div className="p-4 text-xs text-kira-muted text-center">
              Nothing to see.
            </div>
          ) : (
            <div className="p-2 space-y-1.5">
              {all.map((e, i) => (
                <div
                  key={`${e.kind}-${i}-${e.generated_at}`}
                  className={`p-2 rounded-lg border bg-kira-bg ${TONE[e.intervention] ?? TONE.notify}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-[10px] uppercase tracking-wider text-kira-muted">
                        {scoreLabel(e)}
                      </div>
                      <div className="text-sm text-kira-text font-medium">
                        {e.title}
                      </div>
                      <div className="text-xs text-kira-muted mt-0.5">
                        {e.message}
                      </div>
                    </div>
                    <button
                      onClick={() => dismiss(e)}
                      className="text-kira-muted hover:text-red-400 text-sm shrink-0"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
