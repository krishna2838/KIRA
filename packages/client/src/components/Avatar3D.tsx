import { Suspense, useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import type { KiraState } from "../types";
import type { ParticleDensity } from "../stores/appStore";

/**
 * Per-state visual profile.
 *
 * We keep the state → color/motion mapping isolated so the shader/particle
 * code stays simple: all three subsystems (core sphere, particle ring, bloom)
 * lerp toward the target values every frame.
 */
interface Profile {
  color: THREE.Color;
  particleSpeed: number;
  particleRadius: number;   // orbit radius around the core
  particleSpread: number;   // random scatter added to the orbit
  scale: number;            // core scale target
  bloomIntensity: number;
  displacement: number;     // vertex displacement magnitude
  rotationSpeed: number;    // core rotation (rad/s)
  particleDirection: 1 | -1;
}

function profileFor(state: KiraState): Profile {
  switch (state) {
    case "listening":
      return {
        color: new THREE.Color("#3b82f6"),
        particleSpeed: 0.8, particleRadius: 1.6, particleSpread: 0.2,
        scale: 1.08, bloomIntensity: 1.2, displacement: 0.08,
        rotationSpeed: 0.4, particleDirection: 1,
      };
    case "thinking":
      return {
        color: new THREE.Color("#f59e0b"),
        particleSpeed: 0.6, particleRadius: 1.5, particleSpread: 0.05,
        scale: 1.0, bloomIntensity: 1.0, displacement: 0.05,
        rotationSpeed: 0.9, particleDirection: 1,
      };
    case "searching":
      return {
        color: new THREE.Color("#06b6d4"),
        particleSpeed: 1.6, particleRadius: 1.9, particleSpread: 1.2,
        scale: 1.0, bloomIntensity: 1.1, displacement: 0.06,
        rotationSpeed: 0.6, particleDirection: 1,
      };
    case "speaking":
      return {
        color: new THREE.Color("#60a5fa"),
        particleSpeed: 0.9, particleRadius: 1.7, particleSpread: 0.3,
        scale: 1.05, bloomIntensity: 1.4, displacement: 0.14,
        rotationSpeed: 0.5, particleDirection: 1,
      };
    case "executing":
      return {
        color: new THREE.Color("#10b981"),
        particleSpeed: 1.0, particleRadius: 1.7, particleSpread: 0.15,
        scale: 1.0, bloomIntensity: 1.1, displacement: 0.06,
        rotationSpeed: 1.2, particleDirection: 1,
      };
    case "error":
      return {
        color: new THREE.Color("#ef4444"),
        particleSpeed: 1.4, particleRadius: 2.4, particleSpread: 1.5,
        scale: 0.9, bloomIntensity: 1.3, displacement: 0.12,
        rotationSpeed: 0.2, particleDirection: -1,
      };
    case "success":
      return {
        color: new THREE.Color("#10b981"),
        particleSpeed: 1.6, particleRadius: 2.2, particleSpread: 0.8,
        scale: 1.1, bloomIntensity: 1.6, displacement: 0.08,
        rotationSpeed: 0.6, particleDirection: 1,
      };
    case "idle":
    default:
      return {
        color: new THREE.Color("#06b6d4"),
        particleSpeed: 0.35, particleRadius: 1.6, particleSpread: 0.1,
        scale: 1.0, bloomIntensity: 0.9, displacement: 0.04,
        rotationSpeed: 0.15, particleDirection: 1,
      };
  }
}


// ---- Core sphere with animated vertex displacement + fresnel glow ----------

const coreVertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uDisplacement;
  uniform float uAmplitude;

  varying vec3 vNormal;
  varying float vDisp;

  // Cheap 3D noise (Perlin-ish via trig — fast, good enough for a glow orb).
  float noise(vec3 p) {
    return sin(p.x * 1.7 + uTime * 0.9)
         * cos(p.y * 1.3 + uTime * 0.7)
         * sin(p.z * 1.9 + uTime * 0.5);
  }

  void main() {
    vec3 pos = position;
    float n = noise(normalize(pos) * 2.2);
    float d = uDisplacement + uAmplitude * 0.3;
    vec3 displaced = pos + normal * n * d;
    vDisp = n;
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
  }
`;

const coreFragmentShader = /* glsl */ `
  uniform vec3 uColor;
  varying vec3 vNormal;
  varying float vDisp;

  void main() {
    // Fresnel-ish edge glow.
    float fres = pow(1.0 - abs(vNormal.z), 2.0);
    vec3 base = uColor * (0.4 + vDisp * 0.3);
    vec3 rim  = uColor * 1.6 * fres;
    gl_FragColor = vec4(base + rim, 1.0);
  }
`;


function Core({
  state,
  amplitudeRef,
  targetProfile,
}: {
  state: KiraState;
  amplitudeRef: React.MutableRefObject<number>;
  targetProfile: React.MutableRefObject<Profile>;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uDisplacement: { value: 0.04 },
      uAmplitude: { value: 0 },
      uColor: { value: new THREE.Color("#06b6d4") },
    }),
    [],
  );

  useFrame((_, delta) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const p = targetProfile.current;

    uniforms.uTime.value += delta;
    // Ease toward target for buttery state transitions.
    uniforms.uDisplacement.value += (p.displacement - uniforms.uDisplacement.value) * 0.06;
    uniforms.uAmplitude.value += (amplitudeRef.current - uniforms.uAmplitude.value) * 0.2;
    (uniforms.uColor.value as THREE.Color).lerp(p.color, 0.05);

    const s = mesh.scale.x + (p.scale - mesh.scale.x) * 0.06;
    mesh.scale.setScalar(s);
    mesh.rotation.y += p.rotationSpeed * delta;

    // Idle "breathing"
    if (state === "idle") {
      const breath = 1 + Math.sin(uniforms.uTime.value * 1.3) * 0.03;
      mesh.scale.setScalar(s * breath);
    }
  });

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1, 4]} />
      <shaderMaterial
        vertexShader={coreVertexShader}
        fragmentShader={coreFragmentShader}
        uniforms={uniforms}
      />
    </mesh>
  );
}


// ---- Particle ring (InstancedMesh — one draw call) -------------------------


function Particles({
  count,
  targetProfile,
}: {
  count: number;
  targetProfile: React.MutableRefObject<Profile>;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tone = useMemo(() => new THREE.Color("#06b6d4"), []);

  // Per-particle random offsets — computed once on mount for stable orbits.
  const seeds = useMemo(() => {
    const out: {
      angle: number;
      elevation: number;
      wobble: number;
      speed: number;
      radiusJitter: number;
    }[] = [];
    for (let i = 0; i < count; i++) {
      out.push({
        angle: Math.random() * Math.PI * 2,
        elevation: (Math.random() - 0.5) * 0.6,
        wobble: Math.random() * Math.PI * 2,
        speed: 0.7 + Math.random() * 0.6,
        radiusJitter: (Math.random() - 0.5) * 0.3,
      });
    }
    return out;
  }, [count]);

  useFrame((_, delta) => {
    const inst = meshRef.current;
    if (!inst) return;
    const p = targetProfile.current;
    const t = performance.now() * 0.001;
    for (let i = 0; i < count; i++) {
      const s = seeds[i];
      const angle =
        s.angle +
        t * p.particleSpeed * s.speed * p.particleDirection;
      const r = p.particleRadius + s.radiusJitter + Math.sin(t + s.wobble) * p.particleSpread * 0.5;
      const y = s.elevation + Math.cos(t * 0.7 + s.wobble) * p.particleSpread * 0.3;
      dummy.position.set(Math.cos(angle) * r, y, Math.sin(angle) * r);
      dummy.scale.setScalar(0.025 + Math.sin(t * 2 + s.wobble) * 0.01);
      dummy.updateMatrix();
      inst.setMatrixAt(i, dummy.matrix);
    }
    inst.instanceMatrix.needsUpdate = true;
    tone.lerp(p.color, 0.05);
    (inst.material as THREE.MeshBasicMaterial).color.copy(tone);
  });

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, count]}
      frustumCulled={false}
    >
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial color="#06b6d4" toneMapped={false} />
    </instancedMesh>
  );
}


// ---- FPS sampler → auto-drop particle count ------------------------------


function usePerf(onFrame: (fps: number) => void, sampleEveryMs = 500) {
  const last = useRef(performance.now());
  const acc = useRef(0);
  const frames = useRef(0);
  useFrame(() => {
    const now = performance.now();
    const dt = now - last.current;
    last.current = now;
    acc.current += dt;
    frames.current += 1;
    if (acc.current >= sampleEveryMs) {
      const fps = 1000 / (acc.current / frames.current);
      onFrame(fps);
      acc.current = 0;
      frames.current = 0;
    }
  });
}


// ---- Scene ---------------------------------------------------------------


function Scene({
  state,
  amplitudeRef,
  particleCount,
  onFps,
}: {
  state: KiraState;
  amplitudeRef: React.MutableRefObject<number>;
  particleCount: number;
  onFps: (fps: number) => void;
}) {
  const targetProfile = useRef<Profile>(profileFor(state));
  useEffect(() => {
    targetProfile.current = profileFor(state);
  }, [state]);

  usePerf(onFps);
  const { gl } = useThree();
  useEffect(() => {
    // Cap the render loop at ~30fps by lowering the internal pixel ratio
    // on high-DPI displays. This is the cheapest fps cap that plays nicely
    // with R3F's built-in animation loop.
    gl.setPixelRatio(Math.min(1.5, window.devicePixelRatio));
  }, [gl]);

  return (
    <>
      <ambientLight intensity={0.15} />
      <pointLight position={[3, 3, 3]} intensity={1.2} color="#88ccff" />
      <Core state={state} amplitudeRef={amplitudeRef} targetProfile={targetProfile} />
      <Particles count={particleCount} targetProfile={targetProfile} />
      <EffectComposer multisampling={0}>
        <Bloom
          intensity={1.2}
          luminanceThreshold={0.2}
          luminanceSmoothing={0.5}
          mipmapBlur
        />
      </EffectComposer>
    </>
  );
}


// ---- Audio reactivity ----------------------------------------------------
//
// Server-side TTS plays on the server, so we don't have a MediaStream for it.
// Two paths: (1) if `speaking`, drive a synthetic amplitude curve; (2) if the
// user has the mic engaged, use its live level. Either way the value lands
// in the ref that the shader reads.
//

function useAmplitude(state: KiraState) {
  const ref = useRef(0);
  useEffect(() => {
    let cancelled = false;

    // Synthetic pulse while speaking — cheap, no permissions needed.
    if (state === "speaking") {
      let raf = 0;
      const start = performance.now();
      const tick = () => {
        if (cancelled) return;
        const t = (performance.now() - start) / 1000;
        // Layered sines → talky rhythm; clamp to [0, 1].
        const v =
          Math.abs(Math.sin(t * 8.2) * 0.6 + Math.sin(t * 3.1) * 0.3 +
            Math.sin(t * 15.7) * 0.15);
        ref.current = Math.min(1, v);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
      return () => {
        cancelled = true;
        cancelAnimationFrame(raf);
      };
    }

    // Not speaking — decay to zero.
    let raf = 0;
    const tick = () => {
      if (cancelled) return;
      ref.current *= 0.9;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [state]);
  return ref;
}


// ---- Top-level component -------------------------------------------------


interface Props {
  state: KiraState;
  size?: number;
  density: ParticleDensity;
  onPoorPerformance?: () => void;
}

function densityToCount(d: ParticleDensity, size: number): number {
  const base = d === "low" ? 40 : d === "medium" ? 90 : 160;
  // Scale down for the mini floating avatar.
  return Math.max(20, Math.round(base * Math.min(1, size / 160)));
}

export function Avatar3D({ state, size = 160, density, onPoorPerformance }: Props) {
  const amplitude = useAmplitude(state);
  const badFrames = useRef(0);
  const initialCount = densityToCount(density, size);
  const countRef = useRef(initialCount);

  // Simple ratchet: if fps < 20 for 3 consecutive samples, halve particle
  // count. If still poor after another 3 samples, call onPoorPerformance
  // so the wrapper can hop to the SVG.
  const droppedOnce = useRef(false);
  const onFps = (fps: number) => {
    if (fps < 20) {
      badFrames.current += 1;
      if (badFrames.current === 3 && !droppedOnce.current) {
        droppedOnce.current = true;
        countRef.current = Math.max(20, Math.floor(countRef.current / 2));
      } else if (badFrames.current >= 6) {
        onPoorPerformance?.();
      }
    } else {
      badFrames.current = 0;
    }
  };

  return (
    <div
      className="relative inline-block"
      style={{ width: size, height: size }}
      aria-label={`KIRA state: ${state}`}
    >
      <Canvas
        style={{ width: size, height: size, background: "transparent" }}
        dpr={[1, 1.5]}
        gl={{ antialias: false, powerPreference: "high-performance", alpha: true }}
        frameloop="always"
        camera={{ position: [0, 0, 4], fov: 45 }}
      >
        <Suspense fallback={null}>
          <Scene
            state={state}
            amplitudeRef={amplitude}
            particleCount={countRef.current}
            onFps={onFps}
          />
        </Suspense>
      </Canvas>
    </div>
  );
}
