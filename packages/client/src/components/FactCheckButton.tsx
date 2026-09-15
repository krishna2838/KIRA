import { useState } from "react";
import { apiFetch } from "../lib/api";
import type { SourceHit } from "../types";
import { SearchResults } from "./SearchResults";

interface Verdict {
  verdict: string;
  sources: SourceHit[];
}

export function FactCheckButton({ claim }: { claim: string }) {
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await apiFetch<Verdict>("/api/factcheck", {
        method: "POST",
        body: JSON.stringify({ claim: claim.slice(0, 2000) }),
      });
      setVerdict(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        onClick={run}
        disabled={busy}
        className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-kira-border text-kira-muted hover:border-kira-accent hover:text-kira-accent disabled:opacity-50"
        title="Re-search and cross-reference"
      >
        {busy ? "checking…" : "double-check"}
      </button>
      {(verdict || err) && (
        <div className="w-full mt-2 rounded-xl border border-kira-border bg-kira-panel p-3 normal-case tracking-normal">
          {err && <div className="text-xs text-red-400">Fact-check failed: {err}</div>}
          {verdict && (
            <>
              <div className="text-[10px] uppercase tracking-wider text-kira-accent mb-1">
                Fact-check
              </div>
              <div className="text-sm leading-relaxed whitespace-pre-wrap">
                {verdict.verdict}
              </div>
              {verdict.sources.length > 0 && <SearchResults sources={verdict.sources} />}
              <button
                onClick={() => setVerdict(null)}
                className="mt-2 text-[10px] text-kira-muted hover:text-kira-text"
              >
                close
              </button>
            </>
          )}
        </div>
      )}
    </>
  );
}
