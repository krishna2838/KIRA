import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { AuditViewer } from "./AuditViewer";
import { GoogleConnect } from "./GoogleConnect";

type Section = "personality" | "accounts" | "avatar" | "voice" | "audit" | "health";

interface DetailedHealth {
  status: string;
  version: string;
  core: Record<string, { ok: boolean; detail: string }>;
  tools: { servers: { name: string; status: string; tool_count: number }[]; total: number };
  voice?: Record<string, unknown>;
  documents?: { indexed: number };
  scheduler?: { tasks: number };
}

export function SettingsPage() {
  const [section, setSection] = useState<Section>("personality");

  return (
    <div className="p-4 flex gap-6 min-h-full">
      <nav className="w-40 shrink-0 text-sm">
        {(["personality", "accounts", "avatar", "voice", "audit", "health"] as Section[]).map((s) => (
          <button
            key={s}
            onClick={() => setSection(s)}
            className={`w-full text-left px-3 py-2 rounded ${
              section === s ? "bg-kira-panel text-kira-accent" : "hover:bg-kira-panel"
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </nav>

      <div className="flex-1 min-w-0">
        {section === "personality" && <PersonalitySection />}
        {section === "accounts" && <AccountsSection />}
        {section === "avatar" && <AvatarSection />}
        {section === "voice" && <VoiceSection />}
        {section === "audit" && <AuditViewer />}
        {section === "health" && <HealthSection />}
      </div>
    </div>
  );
}

// ---- Personality --------------------------------------------------------

function PersonalitySection() {
  return (
    <div>
      <div className="text-sm font-medium mb-2">Personality</div>
      <div className="text-xs text-kira-muted mb-4">
        Configured in <code className="text-kira-text">config/default.yaml</code>
        (formality: casual/balanced/formal, verbosity: terse/normal/detailed,
        opinions on/off). Changes take effect on server restart.
      </div>
    </div>
  );
}

// ---- Accounts -----------------------------------------------------------

function AccountsSection() {
  const [githubStatus, setGithubStatus] = useState<{ authenticated: boolean } | null>(null);
  const [pat, setPat] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    apiFetch<{ authenticated: boolean }>("/api/auth/github/status")
      .then(setGithubStatus)
      .catch(() => setGithubStatus({ authenticated: false }));

  useEffect(() => {
    refresh();
  }, []);

  const submit = async () => {
    setBusy(true);
    try {
      await apiFetch("/api/auth/github", {
        method: "POST",
        body: JSON.stringify({ token: pat }),
      });
      setPat("");
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const signout = async () => {
    setBusy(true);
    try {
      await apiFetch("/api/auth/github/signout", { method: "POST" });
      refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="text-sm font-medium mb-3">Google</div>
      <GoogleConnect />

      <div className="text-sm font-medium mt-6 mb-3">GitHub</div>
      {githubStatus?.authenticated ? (
        <div className="flex items-center gap-3">
          <span className="text-xs text-emerald-400">● GitHub connected</span>
          <button
            onClick={signout}
            disabled={busy}
            className="text-xs text-kira-muted hover:text-red-400"
          >
            disconnect
          </button>
        </div>
      ) : (
        <div className="flex gap-2">
          <input
            type="password"
            value={pat}
            onChange={(e) => setPat(e.target.value)}
            placeholder="GitHub personal access token"
            className="flex-1 bg-kira-bg border border-kira-border rounded px-2 py-1 text-xs font-mono"
          />
          <button
            onClick={submit}
            disabled={busy || !pat.trim()}
            className="text-xs bg-kira-accent text-black px-3 py-1 rounded font-medium disabled:opacity-40"
          >
            connect
          </button>
        </div>
      )}
    </div>
  );
}

// ---- Avatar / Voice / Health -------------------------------------------

function AvatarSection() {
  return (
    <div>
      <div className="text-sm font-medium mb-2">Avatar</div>
      <div className="text-xs text-kira-muted">
        Use the sidebar "Avatar settings…" button — the modal covers mode,
        particle density, and the floating mini avatar.
      </div>
    </div>
  );
}

function VoiceSection() {
  return (
    <div>
      <div className="text-sm font-medium mb-2">Voice</div>
      <div className="text-xs text-kira-muted">
        Open voice settings via the ⚙ button next to the mic in the chat
        input bar. Toggles wake word, input, and output device.
      </div>
    </div>
  );
}

function HealthSection() {
  const [data, setData] = useState<DetailedHealth | null>(null);
  useEffect(() => {
    apiFetch<DetailedHealth>("/health/detailed")
      .then(setData)
      .catch(() => setData(null));
  }, []);
  if (!data) return <div className="text-xs text-kira-muted">loading…</div>;

  return (
    <div className="space-y-3 text-xs">
      <div className="text-sm">
        Status: <span className={data.status === "ok" ? "text-emerald-400" : "text-amber-400"}>{data.status}</span> · v{data.version}
      </div>
      <Section title="Core">
        {Object.entries(data.core).map(([k, v]) => (
          <Row key={k} label={k} ok={v.ok} detail={v.detail} />
        ))}
      </Section>
      <Section title={`Tools (${data.tools.total})`}>
        {data.tools.servers.map((s) => (
          <Row key={s.name} label={s.name} ok={s.status === "ready"} detail={`${s.tool_count} tools · ${s.status}`} />
        ))}
      </Section>
      {data.voice && (
        <Section title="Voice">
          <div className="text-kira-muted">
            {JSON.stringify(data.voice, null, 2)}
          </div>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-3 rounded-lg border border-kira-border bg-kira-panel">
      <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2">
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Row({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span
          className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-400"}`}
        />
        <span>{label}</span>
      </div>
      <span className="text-kira-muted">{detail}</span>
    </div>
  );
}
