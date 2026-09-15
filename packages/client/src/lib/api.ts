// API base URL detection.
//
// - In Tauri (desktop) the server is always on localhost.
// - In a browser (dev on 5173, or a phone hitting the LAN IP on 8750), the
//   FastAPI server itself serves both /api and the built React app, so the
//   same origin works. In Vite dev on :5173 we point at :8750 explicitly.

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function getApiBaseUrl(): string {
  if (isTauri()) {
    return "http://127.0.0.1:8750";
  }
  const { protocol, hostname, port } = window.location;
  if (port === "5173") {
    // Vite dev — API is on 8750 of the same host
    return `${protocol}//${hostname}:8750`;
  }
  return window.location.origin;
}

export const API_BASE = getApiBaseUrl();

export function getWsUrl(path = "/api/chat/stream"): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}${path}`;
}

export async function apiFetch<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}
