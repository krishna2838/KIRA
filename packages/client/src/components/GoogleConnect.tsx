import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

interface Status {
  authenticated: boolean;
  credentials_file_present: boolean;
}

export function GoogleConnect() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await apiFetch<Status>("/api/auth/google/status"));
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const connect = async () => {
    setBusy(true);
    setErr(null);
    try {
      await apiFetch("/api/auth/google", { method: "POST" });
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await apiFetch("/api/auth/google/signout", { method: "POST" });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  if (!status) return null;

  return (
    <div className="flex items-center gap-2">
      {status.authenticated ? (
        <>
          <span className="text-xs text-emerald-400">● Google connected</span>
          <button
            onClick={disconnect}
            disabled={busy}
            className="text-xs text-kira-muted hover:text-red-400"
          >
            disconnect
          </button>
        </>
      ) : status.credentials_file_present ? (
        <button
          onClick={connect}
          disabled={busy}
          className="text-sm bg-kira-accent text-black font-medium px-3 py-1.5 rounded"
        >
          {busy ? "Opening browser…" : "Connect Google"}
        </button>
      ) : (
        <div className="text-[11px] text-kira-muted leading-snug">
          Drop your OAuth Desktop client JSON at
          <code className="mx-1 text-kira-text">~/.kira/google/credentials.json</code>
          then click Connect.
        </div>
      )}
      {err && <div className="text-[11px] text-red-400">{err}</div>}
    </div>
  );
}
