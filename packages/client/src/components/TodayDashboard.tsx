import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { useToday } from "../hooks/useToday";
import { GoogleConnect } from "./GoogleConnect";

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function relativeDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
    if (diff < 1) return "today";
    if (diff < 2) return "tomorrow";
    return `in ${Math.round(diff)} days`;
  } catch {
    return iso;
  }
}

export function TodayDashboard() {
  const { data } = useToday();
  const [morning, setMorning] = useState<{ brief: string } | null>(null);
  const [morningLoaded, setMorningLoaded] = useState(false);

  useEffect(() => {
    // Show the morning brief once per session on first mount.
    if (morningLoaded) return;
    setMorningLoaded(true);
    apiFetch<{ brief: string }>("/api/today/morning")
      .then(setMorning)
      .catch(() => {});
  }, [morningLoaded]);

  if (!data) return null;

  const google = data.google;
  const events = google.connected ? google.today_events : [];
  const tasks = google.connected ? google.open_tasks : [];
  const unreadEmail = google.connected ? google.unread_email ?? 0 : null;

  return (
    <div className="p-4 space-y-4">
      {morning?.brief && (
        <section className="p-4 rounded-xl border border-kira-border bg-kira-panel">
          <div className="text-[10px] uppercase tracking-wider text-kira-accent mb-1">
            Morning brief
          </div>
          <div className="text-sm whitespace-pre-wrap leading-relaxed">
            {morning.brief}
          </div>
        </section>
      )}

      {!google.connected && (
        <section className="p-4 rounded-xl border border-kira-border bg-kira-panel">
          <div className="text-sm text-kira-muted mb-2">
            Connect Google to see your day.
          </div>
          <GoogleConnect />
        </section>
      )}

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Today's schedule">
          {events.length === 0 ? (
            <div className="text-xs text-kira-muted">
              {google.connected ? "Nothing on the calendar." : "Not connected."}
            </div>
          ) : (
            events.map((e, i) => (
              <div key={e.id ?? i} className="py-1.5 border-b border-kira-border last:border-0">
                <div className="text-sm truncate">{e.title || "(untitled)"}</div>
                <div className="text-[11px] text-kira-muted">
                  {formatTime(e.start)}
                  {e.end ? ` – ${formatTime(e.end)}` : ""}
                  {e.location ? ` · ${e.location}` : ""}
                </div>
                {e.hangout_link && (
                  <a
                    href={e.hangout_link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-kira-accent underline"
                  >
                    Join
                  </a>
                )}
              </div>
            ))
          )}
        </Card>

        <Card title={`Tasks${tasks.length ? ` · ${tasks.length}` : ""}`}>
          {tasks.length === 0 ? (
            <div className="text-xs text-kira-muted">Nothing pending.</div>
          ) : (
            tasks.slice(0, 8).map((t) => (
              <div key={t.id} className="py-1.5 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-kira-accent" />
                <span className="text-sm flex-1 truncate">{t.title}</span>
                {t.due && (
                  <span className="text-[10px] text-kira-muted">
                    {new Date(t.due).toLocaleDateString()}
                  </span>
                )}
              </div>
            ))
          )}
        </Card>

        <Card title={`Unread email${unreadEmail !== null ? ` · ${unreadEmail}` : ""}`}>
          {unreadEmail === null && (
            <div className="text-xs text-kira-muted">Not connected.</div>
          )}
          {unreadEmail !== null && (
            <div className="text-xs text-kira-muted">
              {unreadEmail === 0
                ? "Inbox zero."
                : `${unreadEmail} unread in inbox.`}
            </div>
          )}
        </Card>

        <Card title={`Deadlines${data.deadlines.length ? ` · ${data.deadlines.length}` : ""}`}>
          {data.deadlines.length === 0 ? (
            <div className="text-xs text-kira-muted">None tracked.</div>
          ) : (
            data.deadlines.slice(0, 5).map((d) => (
              <div key={d.id} className="py-1.5 border-b border-kira-border last:border-0">
                <div className="text-sm truncate">{d.name}</div>
                <div className="text-[11px] text-kira-muted">
                  {relativeDate(d.due)} · {new Date(d.due).toLocaleDateString()}
                </div>
              </div>
            ))
          )}
        </Card>
      </section>

      <section>
        <Card title={`Notifications · ${data.notifications.unread} unread`}>
          {data.notifications.recent.length === 0 ? (
            <div className="text-xs text-kira-muted">Nothing recent.</div>
          ) : (
            data.notifications.recent.slice(0, 6).map((n) => (
              <div
                key={n.id}
                className="py-1.5 border-b border-kira-border last:border-0"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-kira-bg border border-kira-border text-kira-muted">
                    {n.app_name}
                  </span>
                  <span className="text-sm truncate flex-1">
                    {n.sender ? `${n.sender} · ` : ""}
                    {n.title}
                  </span>
                  {!n.read && (
                    <span className="w-1.5 h-1.5 rounded-full bg-kira-accent" />
                  )}
                </div>
                {n.body && (
                  <div className="text-[11px] text-kira-muted truncate mt-0.5">
                    {n.body}
                  </div>
                )}
              </div>
            ))
          )}
        </Card>
      </section>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="p-3 rounded-xl border border-kira-border bg-kira-panel">
      <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2">
        {title}
      </div>
      {children}
    </div>
  );
}
