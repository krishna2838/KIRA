import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { useMemory } from "../hooks/useMemory";
import type { Entity, Relationship } from "../types";

type Tab = "memories" | "graph";

export function MemoryViewer() {
  const [tab, setTab] = useState<Tab>("memories");
  const [query, setQuery] = useState("");
  const { memories, search, remove } = useMemory();

  return (
    <div className="h-full flex flex-col bg-kira-panel border-l border-kira-border">
      <div className="flex border-b border-kira-border">
        <TabButton active={tab === "memories"} onClick={() => setTab("memories")}>
          Memories
        </TabButton>
        <TabButton active={tab === "graph"} onClick={() => setTab("graph")}>
          Graph
        </TabButton>
      </div>

      {tab === "memories" && (
        <>
          <div className="p-3 border-b border-kira-border">
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                search(e.target.value);
              }}
              placeholder="Search memories…"
              className="w-full bg-kira-bg border border-kira-border rounded px-3 py-2 text-sm focus:outline-none focus:border-kira-accent"
            />
          </div>
          <div className="flex-1 overflow-y-auto kira-scroll p-3">
            {memories.length === 0 && (
              <div className="text-kira-muted text-sm">No memories yet.</div>
            )}
            {memories.map((m) => (
              <div
                key={m.id}
                className="mb-3 p-3 bg-kira-bg border border-kira-border rounded"
              >
                <div className="flex justify-between items-start gap-2">
                  <div className="text-xs text-kira-accent uppercase tracking-wide">
                    {m.category}
                  </div>
                  <button
                    onClick={() => remove(m.id)}
                    className="text-xs text-kira-muted hover:text-red-400"
                  >
                    delete
                  </button>
                </div>
                <div className="text-sm mt-1">{m.content}</div>
                <div className="text-[10px] text-kira-muted mt-2">
                  importance: {m.importance.toFixed(2)} ·{" "}
                  {new Date(m.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "graph" && <GraphView />}
    </div>
  );
}

function TabButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 py-2 text-sm ${
        active
          ? "text-kira-accent border-b-2 border-kira-accent"
          : "text-kira-muted"
      }`}
    >
      {children}
    </button>
  );
}

function GraphView() {
  const [data, setData] = useState<{
    entities: Entity[];
    relationships: Relationship[];
  }>({ entities: [], relationships: [] });

  useEffect(() => {
    apiFetch<{ entities: Entity[]; relationships: Relationship[] }>(
      "/api/memory/graph",
    )
      .then(setData)
      .catch(() => {});
  }, []);

  return (
    <div className="flex-1 overflow-y-auto kira-scroll p-3">
      <div className="text-xs text-kira-muted mb-2">
        {data.entities.length} entities · {data.relationships.length} relationships
      </div>
      {data.entities.map((e) => {
        const rels = data.relationships.filter(
          (r) => r.source_id === e.id || r.target_id === e.id,
        );
        return (
          <div
            key={e.id}
            className="mb-2 p-2 bg-kira-bg border border-kira-border rounded"
          >
            <div className="text-sm">
              <span className="text-kira-accent">{e.name}</span>
              <span className="text-kira-muted text-xs ml-2">{e.type}</span>
            </div>
            {rels.length > 0 && (
              <div className="text-xs text-kira-muted mt-1">
                {rels.length} relation{rels.length === 1 ? "" : "s"}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
