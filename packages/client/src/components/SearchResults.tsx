import type { SourceHit } from "../types";
import { SourceCard } from "./SourceCard";

export function SearchResults({ sources }: { sources: SourceHit[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
      {sources.map((s, i) => (
        <SourceCard key={s.url + i} index={i + 1} source={s} />
      ))}
    </div>
  );
}
