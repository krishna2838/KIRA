import { useState } from "react";
import type { DocumentHit } from "../types";

function hostFromPath(path: string): string {
  return path.split("/").pop() || path;
}

export function DocumentQuote({
  index,
  hit,
}: {
  index: number;
  hit: DocumentHit;
}) {
  const [open, setOpen] = useState(false);
  const shortPath = hostFromPath(hit.file_path);

  return (
    <div className="mt-1 rounded-lg border border-kira-border bg-kira-panel/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-start gap-2 px-3 py-2 text-left"
      >
        <span className="text-[10px] font-mono text-kira-muted mt-0.5">
          [doc {index}]
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm truncate">
            <span className="text-kira-accent">{hit.file_name}</span>
            {hit.page_number != null && (
              <span className="text-kira-muted"> · p.{hit.page_number}</span>
            )}
            <span className="text-[10px] text-kira-muted ml-2">
              {Math.round(hit.score * 100)}% match
            </span>
          </div>
          <div className="text-[10px] text-kira-muted truncate font-mono">
            {hit.file_path}
          </div>
        </div>
        <span className="text-kira-muted text-xs">{open ? "−" : "＋"}</span>
      </button>
      {open && (
        <div className="px-3 pb-2 text-xs text-kira-text leading-relaxed whitespace-pre-wrap border-t border-kira-border">
          {hit.content}
          <div className="mt-2">
            <a
              href={`file://${hit.file_path}`}
              target="_blank"
              rel="noreferrer"
              className="text-[10px] text-kira-accent underline"
            >
              open {shortPath}
            </a>
          </div>
        </div>
      )}
    </div>
  );
}


export function DocumentCitations({ hits }: { hits: DocumentHit[] }) {
  if (!hits.length) return null;
  return (
    <div className="mt-3">
      <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-1">
        Cited from your documents
      </div>
      {hits.map((h, i) => (
        <DocumentQuote key={h.id} index={i + 1} hit={h} />
      ))}
    </div>
  );
}
