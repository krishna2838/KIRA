import { useCallback, useEffect, useState } from "react";
import { API_BASE, apiFetch } from "../lib/api";

interface AuditEntry {
  id: string;
  action: string;
  tool_name: string | null;
  risk_level: number | null;
  input_summary: string | null;
  output_summary: string | null;
  approved: boolean | null;
  approved_by: string | null;
  error: string | null;
  latency_ms: number | null;
  created_at: string | null;
}

const RISK_LABEL = ["READ", "PERS", "EXEC", "EXT", "CRIT"];
const RISK_TONE = [
  "text-emerald-400",
  "text-cyan-400",
  "text-amber-400",
  "text-orange-400",
  "text-red-400",
];

export function AuditViewer() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [q, setQ] = useState("");
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        since_hours: String(hours),
        limit: "200",
      });
      if (q) params.set("q", q);
      const r = await apiFetch<{ entries: AuditEntry[] }>(`/api/audit?${params}`);
      setEntries(r.entries);
    } finally {
      setLoading(false);
    }
  }, [q, hours]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="flex gap-2 mb-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          placeholder="filter (tool, error, arg)"
          className="flex-1 bg-kira-bg border border-kira-border rounded px-2 py-1 text-xs"
        />
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          className="bg-kira-bg border border-kira-border rounded px-2 py-1 text-xs"
        >
          <option value={1}>1h</option>
          <option value={24}>24h</option>
          <option value={168}>7d</option>
          <option value={720}>30d</option>
        </select>
        <a
          href={`${API_BASE}/api/audit/export?since_hours=${hours}`}
          target="_blank"
          rel="noreferrer"
          className="text-xs px-2 py-1 rounded border border-kira-border hover:border-kira-accent"
        >
          export
        </a>
      </div>

      {loading && <div className="text-xs text-kira-muted">loading…</div>}
      {!loading && entries.length === 0 && (
        <div className="text-xs text-kira-muted italic">No entries.</div>
      )}
      <div className="space-y-1 max-h-[70vh] overflow-y-auto kira-scroll">
        {entries.map((e) => (
          <div
            key={e.id}
            className="p-2 rounded border border-kira-border bg-kira-panel text-[11px]"
          >
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={`text-[9px] ${e.risk_level != null ? RISK_TONE[e.risk_level] : "text-kira-muted"}`}
                >
                  {e.risk_level != null ? RISK_LABEL[e.risk_level] : "—"}
                </span>
                <span className="text-kira-text font-mono truncate">
                  {e.tool_name || e.action}
                </span>
                {e.approved === false && <span className="text-red-400">denied</span>}
                {e.approved && (
                  <span className="text-emerald-400 text-[9px]">
                    {e.approved_by}
                  </span>
                )}
              </div>
              <div className="text-[10px] text-kira-muted whitespace-nowrap">
                {e.created_at && new Date(e.created_at).toLocaleString()}
                {e.latency_ms != null && ` · ${e.latency_ms}ms`}
              </div>
            </div>
            {e.input_summary && (
              <div className="text-kira-muted mt-0.5 truncate">
                in: {e.input_summary}
              </div>
            )}
            {e.error && (
              <div className="text-red-400 mt-0.5 truncate">err: {e.error}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
