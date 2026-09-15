import type { KiraState } from "../types";

interface Props {
  state: KiraState;
  size?: number;
}

// SVG state machine — the low-cost fallback for the 3D avatar in Avatar3D.
// The 3D wrapper automatically drops to this when fps drops below the
// configured threshold, when the user selects simple mode, or when WebGL
// isn't available.
export function AvatarSimple({ state, size = 40 }: Props) {
  const tone =
    state === "error"
      ? "#ef4444"
      : state === "success"
        ? "#22c55e"
        : state === "listening"
          ? "#3b82f6"
          : state === "thinking"
            ? "#f59e0b"
            : state === "executing"
              ? "#10b981"
              : "#06b6d4";

  return (
    <div
      className="relative inline-block"
      style={{ width: size, height: size }}
      aria-label={`KIRA state: ${state}`}
    >
      <svg viewBox="0 0 40 40" width={size} height={size}>
        <defs>
          <radialGradient id="core" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={tone} stopOpacity="0.9" />
            <stop offset="100%" stopColor={tone} stopOpacity="0.15" />
          </radialGradient>
        </defs>

        <circle
          cx="20"
          cy="20"
          r="8"
          fill="url(#core)"
          className={
            state === "idle"
              ? "animate-[pulse_2.5s_ease-in-out_infinite]"
              : state === "speaking"
                ? "animate-[pulse_0.5s_ease-in-out_infinite]"
                : ""
          }
        />

        {state === "listening" && (
          <>
            <circle
              cx="20" cy="20" r="14"
              fill="none" stroke={tone} strokeWidth="1.5"
              className="animate-[ping_1.5s_cubic-bezier(0,0,0.2,1)_infinite]"
              style={{ transformOrigin: "20px 20px" }}
            />
            <circle
              cx="20" cy="20" r="17"
              fill="none" stroke={tone} strokeWidth="1" opacity="0.4"
              className="animate-[ping_1.8s_cubic-bezier(0,0,0.2,1)_infinite]"
            />
          </>
        )}

        {state === "speaking" && (
          <g stroke={tone} strokeWidth="2" strokeLinecap="round">
            <line x1="8"  y1="20" x2="8"  y2="20">
              <animate attributeName="y1" values="16;24;16" dur="0.6s" repeatCount="indefinite" />
              <animate attributeName="y2" values="24;16;24" dur="0.6s" repeatCount="indefinite" />
            </line>
            <line x1="14" y1="20" x2="14" y2="20">
              <animate attributeName="y1" values="14;26;14" dur="0.5s" repeatCount="indefinite" />
              <animate attributeName="y2" values="26;14;26" dur="0.5s" repeatCount="indefinite" />
            </line>
            <line x1="20" y1="20" x2="20" y2="20">
              <animate attributeName="y1" values="12;28;12" dur="0.7s" repeatCount="indefinite" />
              <animate attributeName="y2" values="28;12;28" dur="0.7s" repeatCount="indefinite" />
            </line>
            <line x1="26" y1="20" x2="26" y2="20">
              <animate attributeName="y1" values="14;26;14" dur="0.5s" repeatCount="indefinite" />
              <animate attributeName="y2" values="26;14;26" dur="0.5s" repeatCount="indefinite" />
            </line>
            <line x1="32" y1="20" x2="32" y2="20">
              <animate attributeName="y1" values="16;24;16" dur="0.6s" repeatCount="indefinite" />
              <animate attributeName="y2" values="24;16;24" dur="0.6s" repeatCount="indefinite" />
            </line>
          </g>
        )}

        {state === "thinking" && (
          <g fill={tone}>
            <circle cx="12" cy="20" r="2">
              <animate attributeName="opacity" values="0.2;1;0.2" dur="1s" begin="0s" repeatCount="indefinite" />
            </circle>
            <circle cx="20" cy="20" r="2">
              <animate attributeName="opacity" values="0.2;1;0.2" dur="1s" begin="0.2s" repeatCount="indefinite" />
            </circle>
            <circle cx="28" cy="20" r="2">
              <animate attributeName="opacity" values="0.2;1;0.2" dur="1s" begin="0.4s" repeatCount="indefinite" />
            </circle>
          </g>
        )}

        {state === "executing" && (
          <g stroke={tone} strokeWidth="2" fill="none">
            <path d="M 20 6 A 14 14 0 0 1 34 20">
              <animateTransform attributeName="transform" type="rotate"
                from="0 20 20" to="360 20 20" dur="1.2s" repeatCount="indefinite" />
            </path>
          </g>
        )}

        {state === "searching" && (
          <g stroke={tone} strokeWidth="1" fill="none" strokeDasharray="2 4">
            <circle cx="20" cy="20" r="17" opacity="0.6">
              <animateTransform attributeName="transform" type="rotate"
                from="0 20 20" to="360 20 20" dur="3s" repeatCount="indefinite" />
            </circle>
          </g>
        )}

        {state === "error" && (
          <circle
            cx="20" cy="20" r="14"
            fill="none" stroke={tone} strokeWidth="2"
            className="animate-[ping_1s_ease-out_infinite]"
          />
        )}
      </svg>
    </div>
  );
}
