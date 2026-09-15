import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import type { ServerStatus, ToolSpec } from "../types";

interface ToolsResponse {
  servers: ServerStatus[];
  tools: ToolSpec[];
}

export function ToolsPanel() {
  const [data, setData] = useState<ToolsResponse>({ servers: [], tools: [] });
  const [openServer, setOpenServer] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ToolsResponse>("/api/tools")
      .then(setData)
      .catch(() => {});
  }, []);

  return (
    <div className="mt-2">
      <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2">
        Tools
      </div>
      {data.servers.length === 0 && (
        <div className="text-xs text-kira-muted">No servers registered.</div>
      )}
      {data.servers.map((s) => {
        const tools = data.tools.filter((t) => t.server === s.name);
        const isOpen = openServer === s.name;
        return (
          <div key={s.name} className="mb-1">
            <button
              onClick={() => setOpenServer(isOpen ? null : s.name)}
              className="w-full text-left px-2 py-1.5 rounded hover:bg-kira-bg text-sm flex items-center justify-between"
            >
              <span>
                <span
                  className={
                    s.status === "ready"
                      ? "text-emerald-400"
                      : "text-amber-400"
                  }
                >
                  ●
                </span>{" "}
                {s.name}
              </span>
              <span className="text-[10px] text-kira-muted">
                {s.tool_count} · {s.transport}
              </span>
            </button>
            {isOpen && (
              <div className="pl-4 pb-1">
                {tools.map((t) => (
                  <div
                    key={t.qualified_name}
                    className="text-[11px] py-0.5"
                    title={t.description}
                  >
                    <span className="text-kira-accent">{t.name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
