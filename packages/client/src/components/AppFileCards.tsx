export function AppList({ apps }: { apps: string[] }) {
  if (!apps.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {apps.map((a) => (
        <div
          key={a}
          className="text-xs px-2.5 py-1 rounded-full border border-kira-border bg-kira-bg text-kira-text"
        >
          {a}
        </div>
      ))}
    </div>
  );
}

export function FileList({ files }: { files: string[] }) {
  if (!files.length) return null;
  return (
    <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
      {files.map((p) => {
        const name = p.split("/").pop() || p;
        return (
          <div
            key={p}
            className="text-xs px-3 py-2 rounded border border-kira-border bg-kira-bg"
          >
            <div className="text-kira-text truncate">{name}</div>
            <div className="text-[10px] text-kira-muted truncate">{p}</div>
          </div>
        );
      })}
    </div>
  );
}

export function ScreenshotBlock({
  base64,
  mime,
  caption,
}: {
  base64: string;
  mime?: string;
  caption?: string;
}) {
  return (
    <div className="mt-3">
      <img
        src={`data:${mime || "image/png"};base64,${base64}`}
        alt={caption || "screenshot"}
        className="w-full rounded-xl border border-kira-border"
      />
      {caption && (
        <div className="text-[10px] text-kira-muted mt-1 text-center">
          {caption}
        </div>
      )}
    </div>
  );
}
