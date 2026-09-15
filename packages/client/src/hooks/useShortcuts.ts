import { useEffect } from "react";

type Handler = (e: KeyboardEvent) => void;

/**
 * Simple global keyboard shortcut binding.
 * Keys use the format `mod+K`, `mod+shift+/`, `mod+n`. `mod` = Cmd on
 * macOS, Ctrl elsewhere.
 */
export function useShortcuts(map: Record<string, Handler>) {
  useEffect(() => {
    const isMac = typeof navigator !== "undefined" &&
      /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

    const onKey = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey : e.ctrlKey;
      const parts: string[] = [];
      if (mod) parts.push("mod");
      if (e.shiftKey) parts.push("shift");
      if (e.altKey) parts.push("alt");
      parts.push(e.key.toLowerCase());
      const combo = parts.join("+");
      const handler = map[combo];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [map]);
}
