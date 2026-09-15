import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

interface Status {
  battery?: { percent?: number | null; charging?: boolean };
  disk?: { free_gb?: number; percent_used?: number };
  wifi?: { ssid?: string | null };
  volume?: { volume?: number | null };
}

export function SystemStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        // The tools registry exposes /api/tools; direct exec of a specific
        // read-only tool is done via a helper endpoint the executor exposes
        // in a later phase. For now, we lean on a batched shell tool call
        // through /api/tools/exec (added in Phase 5 wiring).
        const r = await apiFetch<{ result: Status }>("/api/tools/exec", {
          method: "POST",
          body: JSON.stringify({
            tool: "computer.system_status",
            arguments: {},
          }),
        });
        if (!cancelled) setStatus(r.result);
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    };

    load();
    const id = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (err) return null;
  if (!status) return null;

  const b = status.battery;
  const d = status.disk;
  const w = status.wifi;
  const v = status.volume;

  return (
    <div className="mt-2">
      <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2">
        Computer
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {b?.percent != null && (
          <Tile
            label="Battery"
            value={`${b.percent}%${b.charging ? " ⚡" : ""}`}
            tone={
              b.percent > 40
                ? "text-emerald-400"
                : b.percent > 15
                  ? "text-amber-400"
                  : "text-red-400"
            }
          />
        )}
        {d?.free_gb != null && (
          <Tile
            label="Disk free"
            value={`${d.free_gb} GB`}
            tone={
              (d.percent_used ?? 0) < 80 ? "text-emerald-400" : "text-amber-400"
            }
          />
        )}
        {w?.ssid != null && <Tile label="Wi-Fi" value={w.ssid || "—"} />}
        {v?.volume != null && (
          <Tile label="Volume" value={`${v.volume}`} />
        )}
      </div>
    </div>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="px-2 py-1.5 rounded bg-kira-bg border border-kira-border">
      <div className="text-[9px] text-kira-muted uppercase">{label}</div>
      <div className={`text-xs mt-0.5 truncate ${tone ?? ""}`}>{value}</div>
    </div>
  );
}
