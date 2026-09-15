import type { ToolEvent } from "../types";

const VERBS: Record<string, string> = {
  "web.web_search": "Searching the web",
  "web.news_search": "Reading the news",
  "web.image_search": "Searching images",
  "filesystem.read_file": "Reading file",
  "filesystem.write_file": "Writing file",
  "filesystem.list_files": "Listing files",
  "filesystem.search_files": "Searching files",
  "filesystem.delete_file": "Deleting file",
  "terminal.run_command": "Running command",
};

function verbFor(tool: string): string {
  return VERBS[tool] || `Using ${tool}`;
}

export function ToolIndicator({ events }: { events: ToolEvent[] }) {
  if (!events.length) return null;
  return (
    <div className="space-y-1 mb-2">
      {events.map((e, i) => (
        <div
          key={i}
          className="text-[11px] text-kira-muted flex items-center gap-2"
        >
          <span
            className={
              e.phase === "ok"
                ? "text-emerald-400"
                : e.phase === "start"
                  ? "text-cyan-400"
                  : e.phase === "await_confirmation"
                    ? "text-amber-400"
                    : "text-red-400"
            }
          >
            ●
          </span>
          <span>
            {verbFor(e.tool)}
            {e.phase === "ok" && typeof e.latency_ms === "number"
              ? ` · ${e.latency_ms}ms`
              : e.phase === "await_confirmation"
                ? " · needs permission"
                : e.phase === "start"
                  ? "…"
                  : e.message
                    ? ` · ${e.message}`
                    : ""}
          </span>
        </div>
      ))}
    </div>
  );
}
