import type { DocumentHit, Message, ResearchPayload } from "../types";
import { AppList, FileList, ScreenshotBlock } from "./AppFileCards";
import { CodeBlock } from "./CodeBlock";
import { DiffViewer } from "./DiffViewer";
import { ConfidenceBadge, SourceTags } from "./SourceTags";
import { DocumentCitations } from "./DocumentQuote";
import { FactCheckButton } from "./FactCheckButton";
import { FixProposalCard } from "./FixProposalCard";
import { ImageGrid } from "./ImageGrid";
import { SearchResults } from "./SearchResults";
import { VideoGrid } from "./VideoCard";
import { ToolIndicator } from "./ToolIndicator";
import { ToolConfirmation } from "./ToolConfirmation";
import type { ConfirmationRequest, ToolEvent } from "../types";

const URL_RE = /(https?:\/\/[^\s<>()"']+)/g;

function linkify(text: string): (string | JSX.Element)[] {
  const parts: (string | JSX.Element)[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(URL_RE);
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(
      <a
        key={match.index}
        href={match[0]}
        target="_blank"
        rel="noreferrer"
        className="text-kira-accent underline break-all"
      >
        {match[0]}
      </a>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// Renders inline [1]-style citations as small links to the corresponding
// source card via anchor navigation.
function renderWithCitations(
  text: string,
  sources: { url: string }[] | undefined,
): (string | JSX.Element)[] {
  const out: (string | JSX.Element)[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(...linkify(text.slice(last, m.index)));
    const idx = parseInt(m[1], 10) - 1;
    const src = sources?.[idx];
    if (src) {
      out.push(
        <a
          key={`c-${m.index}`}
          href={src.url}
          target="_blank"
          rel="noreferrer"
          className="text-kira-accent text-[10px] align-super mx-0.5"
        >
          [{m[1]}]
        </a>,
      );
    } else {
      out.push(m[0]);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(...linkify(text.slice(last)));
  return out;
}

export function RichMessage({ msg }: { msg: Message }) {
  const tier = (msg.metadata?.model_tier as string) || "";
  const events = (msg.metadata?.tool_events as ToolEvent[] | undefined) ?? [];
  const confirmation = msg.metadata?.confirmation as
    | ConfirmationRequest
    | undefined;
  const research = msg.metadata?.research as ResearchPayload | undefined;
  const researchMode = msg.metadata?.research_mode as string | undefined;
  const docCitations =
    (msg.metadata?.document_citations as DocumentHit[] | undefined) ?? [];
  const sourceTags = (msg.metadata?.source_tags as string[] | undefined) ?? [];
  const confidence = msg.metadata?.confidence as
    | { confidence: number; reason?: string }
    | undefined;

  // Tool result hints surfaced by the chat route.
  const screenshots = events
    .filter((e) => e.screenshot)
    .map((e) => e.screenshot!);
  const appLists = events.flatMap((e) => e.apps ?? []);
  const fileLists = events.flatMap((e) => e.files ?? []);
  const codeSnippets = events
    .filter((e) => e.code)
    .map((e) => e.code!);
  const diffs = events.filter((e) => e.diff).map((e) => e.diff!);
  const proposals = events.filter((e) => e.proposal).map((e) => e.proposal!);

  return (
    <div className="flex w-full justify-start mb-4">
      <div className="max-w-[80%] w-full">
        {events.length > 0 && <ToolIndicator events={events} />}
        <div className="px-4 py-3 rounded-2xl bg-kira-panel text-kira-text leading-relaxed whitespace-pre-wrap">
          {renderWithCitations(msg.content, research?.sources)}
        </div>

        {screenshots.map((s, i) => (
          <ScreenshotBlock
            key={`shot-${i}`}
            base64={s.base64}
            mime={s.mime}
            caption={i === 0 ? "screenshot" : undefined}
          />
        ))}

        {appLists.length > 0 && <AppList apps={appLists} />}
        {fileLists.length > 0 && <FileList files={fileLists} />}

        {codeSnippets.map((c, i) => (
          <CodeBlock
            key={`code-${i}`}
            code={c.content}
            language={c.language}
            filename={c.path}
          />
        ))}

        {diffs.map((d, i) => (
          <DiffViewer key={`diff-${i}`} diff={d.diff} path={d.path} />
        ))}

        {proposals.map((p, i) => (
          <FixProposalCard key={`proposal-${i}`} proposal={p} />
        ))}

        {docCitations.length > 0 && <DocumentCitations hits={docCitations} />}

        {research && (
          <div className="mt-1">
            {research.sources.length > 0 && (
              <SearchResults sources={research.sources} />
            )}
            {research.images.length > 0 && <ImageGrid images={research.images} />}
            {research.videos.length > 0 && <VideoGrid videos={research.videos} />}
            {research.related_queries?.length ? (
              <div className="mt-3">
                <div className="text-[10px] uppercase tracking-wider text-kira-muted mb-1">
                  Related
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {research.related_queries.map((q, i) => (
                    <span
                      key={i}
                      className="text-xs bg-kira-panel border border-kira-border px-2 py-0.5 rounded-full text-kira-muted"
                    >
                      {q}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}

        <div className="text-[10px] uppercase tracking-wider text-kira-muted mt-1 ml-1 flex items-center gap-2 flex-wrap">
          {tier && <span>{tier}</span>}
          {researchMode && <span>research · {researchMode}</span>}
          {sourceTags.length > 0 && <SourceTags tags={sourceTags} />}
          {confidence && (
            <ConfidenceBadge
              confidence={confidence.confidence}
              reason={confidence.reason}
            />
          )}
          <FactCheckButton claim={msg.content} />
        </div>

        {confirmation && <ToolConfirmation confirmation={confirmation} />}
      </div>
    </div>
  );
}
