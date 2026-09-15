import { useState } from "react";
import { apiFetch } from "../lib/api";
import type { ConfirmationRequest } from "../types";

const RISK_LABELS = [
  "L0 · Read",
  "L1 · Personal",
  "L2 · Execute",
  "L3 · External",
  "L4 · Critical",
];

const RISK_TONE = [
  "text-emerald-400",
  "text-cyan-400",
  "text-amber-400",
  "text-orange-400",
  "text-red-500",
];

interface Props {
  confirmation: ConfirmationRequest;
  onResolved?: (approved: boolean) => void;
}

export function ToolConfirmation({ confirmation, onResolved }: Props) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<null | "approved" | "denied">(null);

  const decide = async (approved: boolean) => {
    setBusy(true);
    try {
      await apiFetch(`/api/tools/confirm/${confirmation.id}`, {
        method: "POST",
        body: JSON.stringify({ approved }),
      });
      setDone(approved ? "approved" : "denied");
      onResolved?.(approved);
    } finally {
      setBusy(false);
    }
  };

  const level = confirmation.risk_level ?? 2;

  return (
    <div className="mt-2 p-3 border border-kira-border rounded-xl bg-kira-panel">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs uppercase tracking-wider text-kira-muted">
          KIRA needs permission
        </div>
        <div className={`text-xs font-medium ${RISK_TONE[level]}`}>
          {RISK_LABELS[level] ?? `L${level}`}
        </div>
      </div>
      <div className="text-sm mb-1">
        <span className="font-mono text-kira-accent">{confirmation.tool}</span>
      </div>
      <div className="text-xs text-kira-muted mb-2">{confirmation.description}</div>
      <pre className="text-[11px] bg-kira-bg border border-kira-border rounded p-2 overflow-x-auto">
        {JSON.stringify(confirmation.arguments, null, 2)}
      </pre>
      {done ? (
        <div className="text-xs text-kira-muted mt-2">
          {done === "approved" ? "Approved." : "Denied."}
        </div>
      ) : (
        <div className="flex gap-2 mt-3">
          <button
            disabled={busy}
            onClick={() => decide(true)}
            className="flex-1 bg-kira-accent text-black text-sm font-medium rounded px-3 py-1.5 disabled:opacity-50"
          >
            Approve
          </button>
          <button
            disabled={busy}
            onClick={() => decide(false)}
            className="flex-1 border border-kira-border text-sm rounded px-3 py-1.5 disabled:opacity-50"
          >
            Deny
          </button>
        </div>
      )}
    </div>
  );
}
