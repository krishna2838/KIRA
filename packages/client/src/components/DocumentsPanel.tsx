import { useState } from "react";
import { useDocuments } from "../hooks/useDocuments";

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function DocumentsPanel() {
  const { files, events, inFlight, indexFile, indexDirectory } = useDocuments();
  const [manualPath, setManualPath] = useState("");
  const [dragActive, setDragActive] = useState(false);

  const submitManual = async () => {
    const path = manualPath.trim();
    if (!path) return;
    // Naïve heuristic: paths ending with a slash → directory.
    if (path.endsWith("/")) {
      await indexDirectory(path);
    } else {
      await indexFile(path);
    }
    setManualPath("");
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const dropped = Array.from(e.dataTransfer.files);
    for (const f of dropped) {
      // In web browsers we only receive `File` (no absolute path). This drop
      // handler is meaningful inside the Tauri app where drops carry the file
      // path via a Tauri-specific event — that wiring lives in the Rust host
      // and we listen for it there. For the browser case we surface the file
      // name so the user can paste the full path.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const anyF = f as any;
      const path = anyF.path as string | undefined;
      if (path) {
        await indexFile(path);
      }
    }
  };

  const latest = events[events.length - 1];

  return (
    <div className="mt-2">
      <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2 flex items-center justify-between">
        <span>Documents</span>
        {inFlight > 0 && (
          <span className="text-kira-accent normal-case tracking-normal">
            indexing…
          </span>
        )}
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        className={`p-2 rounded border border-dashed text-[10px] mb-2 text-center ${
          dragActive
            ? "border-kira-accent bg-kira-accent/5 text-kira-accent"
            : "border-kira-border text-kira-muted"
        }`}
      >
        Drop a file or folder to index
      </div>

      <div className="flex gap-1 mb-2">
        <input
          value={manualPath}
          onChange={(e) => setManualPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submitManual()}
          placeholder="~/Documents/notes.pdf"
          className="flex-1 bg-kira-bg border border-kira-border rounded px-2 py-1 text-[11px] focus:outline-none focus:border-kira-accent"
        />
        <button
          onClick={submitManual}
          disabled={!manualPath.trim()}
          className="px-2 py-1 text-[11px] rounded bg-kira-panel border border-kira-border hover:border-kira-accent disabled:opacity-40"
        >
          Index
        </button>
      </div>

      {latest && latest.stage !== "done" && (
        <div className="text-[10px] text-kira-muted truncate mb-2">
          {latest.stage}: {latest.message}
        </div>
      )}

      {files.length === 0 ? (
        <div className="text-[10px] text-kira-muted italic">
          Nothing indexed yet.
        </div>
      ) : (
        <div className="space-y-1 max-h-80 overflow-y-auto kira-scroll">
          {files.slice(0, 60).map((f) => (
            <div
              key={f.file_path}
              className="px-2 py-1 rounded hover:bg-kira-bg text-[11px]"
              title={f.file_path}
            >
              <div className="truncate text-kira-text">{f.file_name}</div>
              <div className="flex justify-between text-[9px] text-kira-muted">
                <span>{f.chunks} chunks</span>
                <span>{timeAgo(f.indexed_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
