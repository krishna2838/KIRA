import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import type { ScheduledTaskSpec } from "../types";

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function ScheduledTasksPanel() {
  const [tasks, setTasks] = useState<ScheduledTaskSpec[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [cron, setCron] = useState("0 9 * * *");
  const [toolChainJson, setToolChainJson] = useState(
    '[{"name":"morning","tool":"life.morning_brief","arguments":{}}]',
  );
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ tasks: ScheduledTaskSpec[] }>("/api/scheduler/tasks");
      setTasks(r.tasks);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  const toggleEnabled = async (t: ScheduledTaskSpec) => {
    await apiFetch(`/api/scheduler/tasks/${encodeURIComponent(t.name)}/enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled: !t.enabled }),
    });
    load();
  };

  const runNow = async (t: ScheduledTaskSpec) => {
    await apiFetch(`/api/scheduler/tasks/${encodeURIComponent(t.name)}/run`, { method: "POST" });
    load();
  };

  const deleteTask = async (t: ScheduledTaskSpec) => {
    await apiFetch(`/api/scheduler/tasks/${encodeURIComponent(t.name)}`, { method: "DELETE" });
    load();
  };

  const createTask = async () => {
    setErr(null);
    let chain: unknown;
    try {
      chain = JSON.parse(toolChainJson);
    } catch (e) {
      setErr(`tool_chain must be JSON: ${(e as Error).message}`);
      return;
    }
    if (!Array.isArray(chain)) {
      setErr("tool_chain must be a JSON array");
      return;
    }
    try {
      await apiFetch("/api/scheduler/tasks", {
        method: "POST",
        body: JSON.stringify({
          name,
          cron,
          tool_chain: chain,
          enabled: true,
        }),
      });
      setName("");
      setCreating(false);
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-medium">Scheduled tasks</div>
        <button
          onClick={() => setCreating((v) => !v)}
          className="text-[11px] px-2 py-1 rounded border border-kira-border hover:border-kira-accent"
        >
          {creating ? "cancel" : "+ new"}
        </button>
      </div>

      {creating && (
        <div className="p-3 rounded-xl border border-kira-border bg-kira-bg mb-3 space-y-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="task name"
            className="w-full bg-kira-panel border border-kira-border rounded px-2 py-1 text-xs"
          />
          <input
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            placeholder="cron (e.g. 0 8 * * 1-5)"
            className="w-full bg-kira-panel border border-kira-border rounded px-2 py-1 text-xs font-mono"
          />
          <textarea
            value={toolChainJson}
            onChange={(e) => setToolChainJson(e.target.value)}
            rows={4}
            className="w-full bg-kira-panel border border-kira-border rounded px-2 py-1 text-xs font-mono"
          />
          {err && <div className="text-[11px] text-red-400">{err}</div>}
          <button
            onClick={createTask}
            disabled={!name.trim() || !cron.trim()}
            className="bg-kira-accent text-black text-xs font-medium px-3 py-1 rounded disabled:opacity-40"
          >
            Save
          </button>
        </div>
      )}

      {tasks.length === 0 ? (
        <div className="text-xs text-kira-muted">No tasks yet.</div>
      ) : (
        <div className="space-y-2">
          {tasks.map((t) => (
            <div
              key={t.name}
              className="p-2.5 rounded-lg border border-kira-border bg-kira-bg"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <div className="text-sm truncate">
                    <span className={t.enabled ? "text-kira-text" : "text-kira-muted line-through"}>
                      {t.name}
                    </span>
                    <span className="text-[10px] text-kira-muted font-mono ml-2">
                      {t.cron}
                    </span>
                  </div>
                  <div className="text-[10px] text-kira-muted mt-0.5">
                    {t.tool_chain?.length || 0} step
                    {t.tool_chain?.length === 1 ? "" : "s"} · last run {timeAgo(t.last_run)}
                    {t.last_result ? ` · ${t.last_result.slice(0, 40)}` : ""}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0 ml-2">
                  <button
                    onClick={() => runNow(t)}
                    className="text-[10px] px-1.5 py-0.5 rounded border border-kira-border hover:border-kira-accent"
                  >
                    run
                  </button>
                  <button
                    onClick={() => toggleEnabled(t)}
                    className="text-[10px] px-1.5 py-0.5 rounded border border-kira-border hover:border-kira-accent"
                  >
                    {t.enabled ? "pause" : "resume"}
                  </button>
                  <button
                    onClick={() => deleteTask(t)}
                    className="text-[10px] px-1.5 py-0.5 rounded border border-kira-border hover:text-red-400"
                  >
                    ×
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
