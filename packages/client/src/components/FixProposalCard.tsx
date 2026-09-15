import type { FixProposal } from "../types";
import { DiffViewer } from "./DiffViewer";

interface Props {
  proposal: FixProposal;
}

export function FixProposalCard({ proposal }: Props) {
  if (!proposal) return null;
  const edits = proposal.edits ?? [];

  return (
    <div className="mt-3 rounded-xl border border-kira-border bg-kira-panel">
      <div className="px-3 py-2 border-b border-kira-border">
        <div className="text-[10px] uppercase tracking-wider text-kira-accent mb-1">
          Proposed fix
        </div>
        {proposal.diagnosis && (
          <div className="text-sm text-kira-text whitespace-pre-wrap leading-relaxed">
            {proposal.diagnosis}
          </div>
        )}
        {proposal.repo_path && (
          <div className="text-[10px] text-kira-muted mt-1 font-mono truncate">
            {proposal.repo_path}
          </div>
        )}
      </div>

      <div className="p-3 space-y-2">
        {edits.length === 0 ? (
          <div className="text-xs text-kira-muted">
            No concrete edits proposed — inspect the diagnosis above.
          </div>
        ) : (
          edits.map((e, i) => {
            const applyPayload = e.diff
              ? {
                  tool: "code.edit_source_file",
                  arguments: {
                    path: e.path,
                    old_text: e.old_text,
                    new_text: e.new_text,
                  },
                }
              : undefined;
            return e.diff ? (
              <DiffViewer
                key={`${e.path}-${i}`}
                diff={e.diff}
                path={e.path}
                applyPayload={applyPayload}
              />
            ) : (
              <div
                key={`${e.path}-${i}`}
                className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs"
              >
                <div className="text-kira-text">{e.path}</div>
                <div className="text-red-400 mt-1">
                  Could not preview: {e.preview_error || "unknown"}
                </div>
              </div>
            );
          })
        )}
      </div>

      {proposal.test_command && (
        <div className="px-3 py-2 border-t border-kira-border text-[11px] text-kira-muted">
          Post-fix test: <code className="text-kira-text">{proposal.test_command}</code>
        </div>
      )}
    </div>
  );
}
