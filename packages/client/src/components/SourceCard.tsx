import type { SourceHit } from "../types";

const DOT: Record<string, string> = {
  high: "bg-emerald-500",
  medium: "bg-amber-400",
  low: "bg-red-500",
};

function favicon(url: string): string {
  try {
    const host = new URL(url).hostname;
    return `https://icons.duckduckgo.com/ip3/${host}.ico`;
  } catch {
    return "";
  }
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function SourceCard({
  index,
  source,
}: {
  index: number;
  source: SourceHit;
}) {
  const ico = favicon(source.url);
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noreferrer"
      className="block p-3 rounded-xl border border-kira-border bg-kira-panel hover:border-kira-accent transition"
    >
      <div className="flex items-start gap-3">
        {ico ? (
          <img src={ico} alt="" width={16} height={16} className="mt-1" />
        ) : (
          <div className="w-4 h-4 mt-1 rounded bg-kira-bg" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-kira-muted font-mono">
              [{index}]
            </span>
            <span
              className={`w-2 h-2 rounded-full ${DOT[source.reliability] ?? DOT.medium}`}
              title={`reliability: ${source.reliability}`}
            />
            <span className="text-xs text-kira-muted truncate">
              {hostname(source.url)}
            </span>
          </div>
          <div className="text-sm font-medium mt-0.5 line-clamp-2">
            {source.title || source.url}
          </div>
          {source.snippet && (
            <div className="text-xs text-kira-muted mt-1 line-clamp-2">
              {source.snippet}
            </div>
          )}
        </div>
      </div>
    </a>
  );
}
