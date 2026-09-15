const TAG_STYLE: Record<string, string> = {
  MEMORY: "border-cyan-500/60 text-cyan-300",
  SEARCH: "border-emerald-500/60 text-emerald-300",
  DOCUMENT: "border-amber-500/60 text-amber-300",
  TOOL: "border-sky-500/60 text-sky-300",
  INFERRED: "border-kira-border text-kira-muted",
};

export function SourceTags({ tags }: { tags: string[] }) {
  if (!tags?.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {tags.map((t) => (
        <span
          key={t}
          className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${TAG_STYLE[t] ?? TAG_STYLE.INFERRED}`}
          title={`Source: ${t}`}
        >
          {t}
        </span>
      ))}
    </div>
  );
}

export function ConfidenceBadge({
  confidence,
  reason,
}: {
  confidence: number;
  reason?: string;
}) {
  const tone =
    confidence >= 8
      ? "border-emerald-500/60 text-emerald-300"
      : confidence >= 5
        ? "border-amber-500/60 text-amber-300"
        : "border-red-500/60 text-red-300";
  return (
    <span
      className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone}`}
      title={reason || "confidence"}
    >
      conf {confidence}/10
    </span>
  );
}
