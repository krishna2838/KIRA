import { useMemo, useState } from "react";
import { apiFetch } from "../lib/api";

interface Props {
  diff: string;
  path?: string;
  // Optional server-side re-apply info: if provided, an Approve button POSTS
  // to the executor to APPLY the same edit that produced this diff. The
  // default (undefined) just shows a read-only preview.
  applyPayload?: {
    tool: string;      // e.g. "code.edit_source_file"
    arguments: Record<string, unknown>;
  };
  onResolved?: (approved: boolean) => void;
}

interface ParsedLine {
  kind: "hunk" | "added" | "removed" | "context" | "meta";
  text: string;
  oldLine?: number;
  newLine?: number;
}

function parseUnified(diff: string): ParsedLine[] {
  const out: ParsedLine[] = [];
  let oldNo = 0;
  let newNo = 0;
  for (const raw of diff.split("\n")) {
    if (raw.startsWith("@@")) {
      const m = raw.match(/@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)(?:,\d+)?/);
      if (m) {
        oldNo = parseInt(m[1], 10);
        newNo = parseInt(m[2], 10);
      }
      out.push({ kind: "hunk", text: raw });
      continue;
    }
    if (raw.startsWith("---") || raw.startsWith("+++") || raw.startsWith("diff ")) {
      out.push({ kind: "meta", text: raw });
      continue;
    }
    if (raw.startsWith("+")) {
      out.push({ kind: "added", text: raw.slice(1), newLine: newNo });
      newNo++;
      continue;
    }
    if (raw.startsWith("-")) {
      out.push({ kind: "removed", text: raw.slice(1), oldLine: oldNo });
      oldNo++;
      continue;
    }
    out.push({
      kind: "context",
      text: raw.startsWith(" ") ? raw.slice(1) : raw,
      oldLine: oldNo,
      newLine: newNo,
    });
    oldNo++;
    newNo++;
  }
  return out;
}

export function DiffViewer({ diff, path, applyPayload, onResolved }: Props) {
  const parsed = useMemo(() => parseUnified(diff), [diff]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<null | "approved" | "denied" | "error">(null);
  const [error, setError] = useState<string | null>(null);

  const stats = useMemo(() => {
    let added = 0;
    let removed = 0;
    for (const p of parsed) {
      if (p.kind === "added") added++;
      else if (p.kind === "removed") removed++;
    }
    return { added, removed };
  }, [parsed]);

  const decide = async (approved: boolean) => {
    if (!applyPayload) return;
    if (!approved) {
      setStatus("denied");
      onResolved?.(false);
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/api/tools/exec", {
        method: "POST",
        body: JSON.stringify(applyPayload),
      });
      setStatus("approved");
      onResolved?.(true);
    } catch (e) {
      setStatus("error");
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-kira-border overflow-hidden my-2">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-kira-border bg-kira-panel/60">
        <div className="text-[10px] uppercase tracking-wider text-kira-muted">
          {path ? <span className="text-kira-text">{path}</span> : "diff"}
        </div>
        <div className="text-[10px] font-mono">
          <span className="text-emerald-400">+{stats.added}</span>{" "}
          <span className="text-red-400">-{stats.removed}</span>
        </div>
      </div>
      <div className="max-h-[380px] overflow-auto font-mono text-[11.5px] leading-snug bg-[#0f0f11]">
        {parsed.map((p, i) => {
          if (p.kind === "meta") {
            return (
              <div key={i} className="px-3 py-0.5 text-kira-muted">
                {p.text}
              </div>
            );
          }
          if (p.kind === "hunk") {
            return (
              <div
                key={i}
                className="px-3 py-0.5 bg-kira-panel/60 text-kira-accent"
              >
                {p.text}
              </div>
            );
          }
          const tone =
            p.kind === "added"
              ? "bg-emerald-500/10"
              : p.kind === "removed"
                ? "bg-red-500/10"
                : "";
          const prefix =
            p.kind === "added" ? "+" : p.kind === "removed" ? "-" : " ";
          return (
            <div key={i} className={`flex ${tone}`}>
              <div className="w-10 text-right pr-2 text-kira-muted select-none">
                {p.oldLine ?? ""}
              </div>
              <div className="w-10 text-right pr-2 text-kira-muted select-none">
                {p.newLine ?? ""}
              </div>
              <div
                className={`px-2 whitespace-pre ${
                  p.kind === "added"
                    ? "text-emerald-200"
                    : p.kind === "removed"
                      ? "text-red-200"
                      : "text-kira-text"
                }`}
              >
                <span className="opacity-40 mr-1">{prefix}</span>
                {p.text}
              </div>
            </div>
          );
        })}
      </div>

      {applyPayload && !status && (
        <div className="flex gap-2 p-2 border-t border-kira-border">
          <button
            disabled={busy}
            onClick={() => decide(true)}
            className="flex-1 text-sm bg-kira-accent text-black font-medium rounded px-3 py-1.5 disabled:opacity-50"
          >
            Approve & apply
          </button>
          <button
            disabled={busy}
            onClick={() => decide(false)}
            className="flex-1 text-sm border border-kira-border rounded px-3 py-1.5 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
      {status && (
        <div className="p-2 text-[11px] text-kira-muted border-t border-kira-border">
          {status === "approved" && "Applied."}
          {status === "denied" && "Rejected."}
          {status === "error" && `Error: ${error}`}
        </div>
      )}
    </div>
  );
}
