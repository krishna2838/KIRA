import { useAppStore } from "../stores/appStore";
import type { AvatarMode, ParticleDensity } from "../stores/appStore";
import { Avatar } from "./Avatar";

const MODES: { value: AvatarMode; label: string; hint: string }[] = [
  { value: "auto", label: "Auto", hint: "3D when GPU is happy, SVG otherwise" },
  { value: "3d", label: "3D orb", hint: "Full Three.js scene" },
  { value: "simple", label: "Simple", hint: "SVG only — near-zero GPU" },
  { value: "hidden", label: "Hidden", hint: "Chat only, no avatar" },
];

const DENSITIES: { value: ParticleDensity; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];


export function AvatarSettings({ onClose }: { onClose: () => void }) {
  const {
    kiraState,
    avatarMode,
    particleDensity,
    floatingAvatar,
    setAvatarMode,
    setParticleDensity,
    setFloatingAvatar,
  } = useAppStore();

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-kira-panel border border-kira-border rounded-xl p-5 w-[480px] max-w-[92vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <div className="text-sm font-medium">Avatar</div>
          <button
            onClick={onClose}
            className="text-kira-muted hover:text-kira-text"
          >
            ×
          </button>
        </div>

        <div className="flex items-center gap-4 mb-4">
          <div className="w-24 h-24 rounded-full overflow-hidden border border-kira-border bg-kira-bg">
            <Avatar state={kiraState} size={96} />
          </div>
          <div className="text-xs text-kira-muted">
            Preview reacts to KIRA's real state. Try sending a message.
          </div>
        </div>

        <div className="mb-4">
          <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2">
            Mode
          </div>
          <div className="grid grid-cols-2 gap-2">
            {MODES.map((m) => (
              <button
                key={m.value}
                onClick={() => setAvatarMode(m.value)}
                className={`text-left p-2 rounded-lg border ${
                  avatarMode === m.value
                    ? "border-kira-accent bg-kira-accent/10"
                    : "border-kira-border hover:border-kira-accent/60"
                }`}
              >
                <div className="text-sm">{m.label}</div>
                <div className="text-[10px] text-kira-muted">{m.hint}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="mb-4">
          <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-2">
            Particle density
          </div>
          <div className="flex gap-2">
            {DENSITIES.map((d) => (
              <button
                key={d.value}
                onClick={() => setParticleDensity(d.value)}
                className={`flex-1 py-1.5 text-sm rounded border ${
                  particleDensity === d.value
                    ? "border-kira-accent bg-kira-accent/10"
                    : "border-kira-border hover:border-kira-accent/60"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
          <div className="text-[10px] text-kira-muted mt-1">
            The 3D avatar auto-drops to fewer particles (and eventually the
            SVG) if the GPU gets busy.
          </div>
        </div>

        <label className="flex items-center justify-between">
          <span className="text-sm">Floating mini avatar</span>
          <input
            type="checkbox"
            checked={floatingAvatar}
            onChange={(e) => setFloatingAvatar(e.target.checked)}
            className="scale-125"
          />
        </label>
      </div>
    </div>
  );
}
