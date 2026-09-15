import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

// Renders a QR code pointing at the LAN URL. Shown when this app is running
// on desktop; scan from your phone on the same WiFi to load the same UI.
export function PhoneConnect() {
  const [ip, setIp] = useState<string | null>(null);

  useEffect(() => {
    // Try Tauri command first
    const w = window as unknown as {
      __TAURI_INTERNALS__?: unknown;
      __TAURI__?: { core?: { invoke: (cmd: string) => Promise<string> } };
    };
    if (w.__TAURI__?.core?.invoke) {
      w.__TAURI__.core
        .invoke("get_local_ip")
        .then((v) => setIp(v))
        .catch(() => setIp(null));
    }
  }, []);

  const url = ip && ip !== "unknown" ? `http://${ip}:8750` : null;
  if (!url) return null;

  return (
    <div className="p-4 border-t border-kira-border">
      <div className="text-xs text-kira-muted mb-2">Open on phone</div>
      <div className="bg-white p-2 rounded inline-block">
        <QRCodeSVG value={url} size={112} />
      </div>
      <div className="text-[10px] text-kira-muted mt-2 font-mono">{url}</div>
    </div>
  );
}
