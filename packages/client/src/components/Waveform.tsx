import { useEffect, useRef, useState } from "react";

interface Props {
  active: boolean;
  height?: number;
  color?: string;
}

// Reads the browser's microphone via getUserMedia and draws a live waveform.
// It's purely a UI cue — server-side capture is the authoritative path for
// STT. When `active` is false the mic is released.
export function Waveform({ active, height = 40, color = "#06b6d4" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>();
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;

    let cancelled = false;

    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const AC = window.AudioContext || (window as any).webkitAudioContext;
        const audioCtx: AudioContext = new AC();
        ctxRef.current = audioCtx;
        const src = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;
        src.connect(analyser);
        const data = new Uint8Array(analyser.fftSize);

        const canvas = canvasRef.current!;
        const draw = () => {
          if (!canvas) return;
          const w = canvas.width;
          const h = canvas.height;
          const ctx = canvas.getContext("2d")!;
          analyser.getByteTimeDomainData(data);
          ctx.clearRect(0, 0, w, h);
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          const slice = w / data.length;
          for (let i = 0; i < data.length; i++) {
            const v = data[i] / 128.0;
            const y = (v * h) / 2;
            const x = i * slice;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
          rafRef.current = requestAnimationFrame(draw);
        };
        draw();
      } catch (e) {
        setErr((e as Error).message);
      }
    })();

    return () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      ctxRef.current?.close().catch(() => {});
      ctxRef.current = null;
    };
  }, [active, color]);

  if (!active) return null;
  if (err) {
    return (
      <div className="text-[10px] text-kira-muted">
        (mic preview unavailable)
      </div>
    );
  }
  return (
    <canvas
      ref={canvasRef}
      width={220}
      height={height}
      className="w-full"
      style={{ height }}
    />
  );
}
