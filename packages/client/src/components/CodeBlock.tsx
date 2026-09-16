import { useEffect, useRef, useState } from "react";
import Prism from "prismjs";
// Common languages — order MATTERS: a grammar that extends another must be
// imported AFTER its base (tsx extends jsx + typescript; jsx extends
// markup+javascript which are in Prism core). Wrong order throws
// "Cannot set properties of undefined (setting 'comment')" and blanks the app.
import "prismjs/components/prism-clike";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-python";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-rust";
import "prismjs/components/prism-go";

interface Props {
  code: string;
  language?: string;
  filename?: string;
  showLineNumbers?: boolean;
}

export function CodeBlock({
  code,
  language,
  filename,
  showLineNumbers = true,
}: Props) {
  const ref = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);
  const lang = normalizeLanguage(language, filename);

  useEffect(() => {
    if (ref.current) Prism.highlightElement(ref.current);
  }, [code, lang]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* no-op */
    }
  };

  const lines = code.split("\n");

  return (
    <div className="rounded-xl border border-kira-border bg-[#0f0f11] overflow-hidden my-2">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-kira-border bg-kira-panel/50">
        <div className="text-[10px] uppercase tracking-wider text-kira-muted">
          {filename ? (
            <span>
              <span className="text-kira-text">{filename}</span>
              {lang && <span className="ml-2 text-kira-muted">· {lang}</span>}
            </span>
          ) : (
            lang || "code"
          )}
        </div>
        <button
          onClick={copy}
          className="text-[10px] px-2 py-0.5 rounded border border-kira-border hover:border-kira-accent"
        >
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <div className="flex overflow-x-auto text-xs font-mono">
        {showLineNumbers && (
          <div className="text-right pr-3 py-2 select-none text-kira-muted border-r border-kira-border">
            {lines.map((_, i) => (
              <div key={i}>{i + 1}</div>
            ))}
          </div>
        )}
        <pre className="py-2 pl-3 pr-3 flex-1 leading-snug">
          <code ref={ref} className={`language-${lang || "text"}`}>{code}</code>
        </pre>
      </div>
    </div>
  );
}

function normalizeLanguage(lang?: string, filename?: string): string {
  if (lang) return lang;
  if (!filename) return "";
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return (
    {
      py: "python",
      js: "javascript",
      jsx: "jsx",
      ts: "typescript",
      tsx: "tsx",
      rs: "rust",
      go: "go",
      sh: "bash",
      zsh: "bash",
      yml: "yaml",
      yaml: "yaml",
      json: "json",
    } as Record<string, string>
  )[ext] || "";
}
