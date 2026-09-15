import { KeyboardEvent, useState } from "react";
import { useVoice } from "../hooks/useVoice";
import { useAppStore } from "../stores/appStore";
import { VoiceSettings } from "./VoiceSettings";
import { Waveform } from "./Waveform";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function InputBar({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const { status, start, stop, interrupt } = useVoice();
  const voiceActive = !!status.active;
  const { researchMode, setResearchMode } = useAppStore();

  const nextResearchMode = () => {
    const cycle: Record<string, "off" | "quick" | "deep"> = {
      off: "quick",
      quick: "deep",
      deep: "off",
    };
    setResearchMode(cycle[researchMode]);
  };

  const submit = () => {
    if (!text.trim()) return;
    onSend(text);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const toggleMic = async () => {
    if (voiceActive) {
      await stop();
    } else {
      await start();
    }
  };

  return (
    <div className="border-t border-kira-border bg-kira-bg p-4">
      {voiceActive && (
        <div className="max-w-4xl mx-auto mb-2 px-1">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <Waveform active={voiceActive} />
            </div>
            <div className="text-[11px] text-kira-muted">
              {status.state}
              {status.wake_word_enabled ? " · wake word on" : ""}
            </div>
            {status.state === "speaking" && (
              <button
                onClick={interrupt}
                className="text-[11px] text-kira-muted hover:text-red-400"
              >
                stop
              </button>
            )}
          </div>
          {status.last_transcript && (
            <div className="text-xs text-kira-muted italic mt-1 truncate">
              "{status.last_transcript}"
            </div>
          )}
        </div>
      )}

      <div className="flex items-end gap-2 max-w-4xl mx-auto">
        <button
          type="button"
          onClick={toggleMic}
          disabled={!status.available && !voiceActive}
          title={
            !status.available
              ? "Voice unavailable — install voice deps or configure Piper"
              : voiceActive
                ? "Stop voice"
                : "Start voice"
          }
          className={`w-11 h-11 rounded-xl border flex items-center justify-center transition ${
            voiceActive
              ? "bg-red-500/20 border-red-500 text-red-400"
              : "bg-kira-panel border-kira-border text-kira-text hover:border-kira-accent"
          } disabled:opacity-40`}
        >
          {voiceActive ? "■" : "🎙"}
        </button>

        <button
          type="button"
          onClick={() => setShowSettings(true)}
          className="w-11 h-11 rounded-xl border border-kira-border bg-kira-panel text-kira-muted hover:text-kira-text"
          title="Voice settings"
        >
          ⚙
        </button>

        <button
          type="button"
          onClick={nextResearchMode}
          title={`Research mode: ${researchMode} — click to cycle`}
          className={`h-11 px-3 rounded-xl border text-xs uppercase tracking-wider transition ${
            researchMode === "off"
              ? "bg-kira-panel border-kira-border text-kira-muted hover:text-kira-text"
              : researchMode === "quick"
                ? "bg-cyan-500/15 border-cyan-500/60 text-cyan-300"
                : "bg-emerald-500/15 border-emerald-500/60 text-emerald-300"
          }`}
        >
          {researchMode === "off" ? "🔎 research" : researchMode === "quick" ? "🔎 quick" : "🔎 deep"}
        </button>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={voiceActive ? "Voice active — or type to override…" : "Talk to KIRA…"}
          disabled={disabled}
          className="flex-1 bg-kira-panel border border-kira-border rounded-xl px-4 py-3 text-kira-text placeholder-kira-muted focus:outline-none focus:border-kira-accent resize-none max-h-40"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !text.trim()}
          className="bg-kira-accent text-black font-medium px-4 py-3 rounded-xl disabled:opacity-40"
        >
          Send
        </button>
      </div>

      {showSettings && <VoiceSettings onClose={() => setShowSettings(false)} />}
    </div>
  );
}
