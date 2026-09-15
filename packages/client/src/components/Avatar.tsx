import { useEffect, useState } from "react";
import { useAppStore } from "../stores/appStore";
import type { KiraState } from "../types";
import { AvatarSimple } from "./AvatarSimple";
import { Avatar3D } from "./Avatar3D";

/**
 * Smart avatar wrapper.
 *
 * - `avatarMode: hidden` → nothing renders (accessibility label kept).
 * - `avatarMode: simple` → SVG.
 * - `avatarMode: 3d`     → Three.js.
 * - `avatarMode: auto`   → 3D when WebGL is available; auto-drops to simple
 *                          when Avatar3D reports sustained poor performance,
 *                          which sticks for the rest of the session.
 */
interface Props {
  state: KiraState;
  size?: number;
}

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext("webgl2") || canvas.getContext("webgl"))
    );
  } catch {
    return false;
  }
}

export function Avatar({ state, size = 40 }: Props) {
  const { avatarMode, particleDensity } = useAppStore();
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const [degraded, setDegraded] = useState(false);

  useEffect(() => {
    setWebgl(hasWebGL());
  }, []);

  if (avatarMode === "hidden") return null;

  const wantsSimple =
    avatarMode === "simple" ||
    (avatarMode === "auto" && (webgl === false || degraded));

  if (wantsSimple || webgl === null) {
    return <AvatarSimple state={state} size={size} />;
  }

  return (
    <Avatar3D
      state={state}
      size={size}
      density={particleDensity}
      onPoorPerformance={() => setDegraded(true)}
    />
  );
}
