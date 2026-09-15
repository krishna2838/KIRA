import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { useVoice } from "../hooks/useVoice";

interface Device {
  index: number;
  name: string;
  channels: number;
}

interface DevicesResponse {
  available: boolean;
  input: Device[];
  output: Device[];
  default_input?: number | null;
  default_output?: number | null;
  reason?: string;
}

export function VoiceSettings({ onClose }: { onClose: () => void }) {
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const { status, setWakeWord } = useVoice();

  useEffect(() => {
    apiFetch<DevicesResponse>("/api/voice/devices")
      .then(setDevices)
      .catch(() => setDevices(null));
  }, []);

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-kira-panel border border-kira-border rounded-xl p-5 w-[420px] max-w-[92vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <div className="text-sm font-medium">Voice settings</div>
          <button
            onClick={onClose}
            className="text-kira-muted hover:text-kira-text"
          >
            ×
          </button>
        </div>

        <label className="flex items-center justify-between mb-4">
          <span className="text-sm">Wake word ("Hey KIRA")</span>
          <input
            type="checkbox"
            checked={!!status.wake_word_enabled}
            onChange={(e) => setWakeWord(e.target.checked)}
            className="scale-125"
          />
        </label>

        <div className="mb-4">
          <div className="text-xs text-kira-muted mb-1">Input device</div>
          {devices?.available ? (
            <select
              className="w-full bg-kira-bg border border-kira-border rounded px-2 py-1.5 text-sm"
              defaultValue={devices.default_input ?? undefined}
            >
              {devices.input.map((d) => (
                <option key={d.index} value={d.index}>
                  {d.name}
                </option>
              ))}
            </select>
          ) : (
            <div className="text-xs text-kira-muted">
              {devices?.reason ?? "loading…"}
            </div>
          )}
        </div>

        <div>
          <div className="text-xs text-kira-muted mb-1">Output device</div>
          {devices?.available ? (
            <select
              className="w-full bg-kira-bg border border-kira-border rounded px-2 py-1.5 text-sm"
              defaultValue={devices.default_output ?? undefined}
            >
              {devices.output.map((d) => (
                <option key={d.index} value={d.index}>
                  {d.name}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        <div className="text-[10px] text-kira-muted mt-4">
          Device changes apply on next voice start.
        </div>
      </div>
    </div>
  );
}
