import { useResearchProgress } from "../hooks/useResearchProgress";

const STAGE_LABEL: Record<string, string> = {
  planning: "Planning search queries",
  searching: "Searching sources",
  reading: "Reading pages",
  synthesizing: "Synthesizing answer",
  waiting: "Working…",
  done: "Done",
};

export function ResearchProgress({ researchId }: { researchId: string }) {
  const { events, done } = useResearchProgress(researchId);
  if (done && events.length === 0) return null;

  const latest = events[events.length - 1];

  return (
    <div className="mt-2 mb-2 p-3 rounded-xl border border-kira-border bg-kira-panel/60">
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            done ? "bg-emerald-500" : "bg-kira-accent animate-pulse"
          }`}
        />
        <span className="text-xs text-kira-muted">
          {done ? "research complete" : "researching…"}
        </span>
      </div>
      <div className="space-y-1">
        {events.slice(-6).map((e, i) => (
          <div key={i} className="text-[11px] text-kira-muted">
            <span className="text-kira-text">
              {STAGE_LABEL[e.stage] ?? e.stage}
            </span>
            {e.message ? <span> — {e.message}</span> : null}
          </div>
        ))}
      </div>
      {!done && latest?.stage === "reading" && Array.isArray(latest.detail?.urls) && (
        <div className="mt-2 text-[10px] text-kira-muted truncate">
          reading: {(latest.detail!.urls as string[]).join(", ")}
        </div>
      )}
    </div>
  );
}
