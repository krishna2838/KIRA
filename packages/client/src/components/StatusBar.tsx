import { useEffect } from "react";
import { apiFetch } from "../lib/api";
import { useAppStore } from "../stores/appStore";
import { useMonitor } from "../hooks/useMonitor";
import { NotificationCenter } from "./NotificationCenter";

export function StatusBar() {
  const { lastModel, lastLatencyMs, serverConnected, setServerConnected } =
    useAppStore();
  const { events, unread, dismiss } = useMonitor();

  useEffect(() => {
    const check = async () => {
      try {
        await apiFetch<{ status: string }>("/health");
        setServerConnected(true);
      } catch {
        setServerConnected(false);
      }
    };
    check();
    const id = setInterval(check, 10_000);
    return () => clearInterval(id);
  }, [setServerConnected]);

  return (
    <>
      {events.length > 0 && (
        <div className="fixed bottom-16 right-4 z-40 space-y-2 max-w-sm">
          {events.slice(0, 3).map((e, i) => (
            <div
              key={i}
              className="p-3 rounded-xl border border-kira-accent bg-kira-panel shadow-lg animate-in slide-in-from-right"
            >
              <div className="flex items-start gap-2">
                <div className="flex-1">
                  <div className="text-xs text-kira-accent font-medium">
                    {e.title}
                  </div>
                  <div className="text-xs text-kira-muted mt-0.5">
                    {e.message}
                  </div>
                </div>
                <button
                  onClick={() => dismiss(i)}
                  className="text-kira-muted hover:text-kira-text text-sm"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between px-4 py-1.5 text-[11px] text-kira-muted border-t border-kira-border bg-kira-bg">
        <div className="flex items-center gap-3">
          <span
            className={`w-2 h-2 rounded-full ${
              serverConnected ? "bg-green-500" : "bg-red-500"
            }`}
          />
          <span>{serverConnected ? "connected" : "offline"}</span>
          {unread > 0 && (
            <span
              className="ml-1 px-1.5 py-0.5 rounded-full bg-kira-accent text-black text-[10px] font-medium"
              title="Unread notifications"
            >
              {unread} unread
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          {lastModel && <span>model: {lastModel}</span>}
          {lastLatencyMs > 0 && <span>{lastLatencyMs} ms</span>}
          <NotificationCenter />
        </div>
      </div>
    </>
  );
}
