import { useProactive } from "../hooks/useProactive";
import type { ProactiveScoredEvent } from "../types";

const TONE: Record<string, string> = {
  notify: "border-cyan-500/60 bg-cyan-500/5",
  suggest: "border-amber-500/60 bg-amber-500/5",
  act: "border-emerald-500/60 bg-emerald-500/5",
  silent: "border-kira-border bg-kira-panel",
};

const LABEL: Record<string, string> = {
  notify: "Heads up",
  suggest: "Want help?",
  act: "Ready to act",
  silent: "Log",
};

interface Props {
  onAsk?: (prompt: string) => void;
}

export function ProactiveSuggestions({ onAsk }: Props) {
  const { queue, dismiss } = useProactive();
  if (queue.length === 0) return null;

  // Show up to 3 highest-scoring events.
  const shown = [...queue].sort((a, b) => b.score - a.score).slice(0, 3);

  const askAbout = (e: ProactiveScoredEvent) => {
    const prompt = e.intervention === "suggest"
      ? `${e.title}. ${e.message} — help me with this.`
      : `Tell me more about: ${e.title}`;
    onAsk?.(prompt);
    dismiss(e);
  };

  return (
    <div className="mb-3 space-y-2">
      {shown.map((e, i) => (
        <div
          key={`${e.kind}-${i}`}
          className={`p-3 rounded-xl border ${TONE[e.intervention] ?? TONE.notify}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-0.5">
                {LABEL[e.intervention] ?? e.intervention}
              </div>
              <div className="text-sm text-kira-text font-medium">
                {e.title}
              </div>
              <div className="text-xs text-kira-muted mt-0.5 leading-relaxed">
                {e.message}
              </div>
            </div>
            <div className="flex flex-col gap-1 shrink-0">
              {(e.intervention === "suggest" || e.intervention === "act") && (
                <button
                  onClick={() => askAbout(e)}
                  className="text-[11px] bg-kira-accent text-black px-2 py-1 rounded font-medium"
                >
                  Ask KIRA
                </button>
              )}
              <button
                onClick={() => dismiss(e)}
                className="text-[11px] text-kira-muted hover:text-red-400 px-2 py-1 rounded"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
