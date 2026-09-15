import type { ConfirmationRequest, Message, ToolEvent } from "../types";
import { ConfidenceBadge, SourceTags } from "./SourceTags";
import { FactCheckButton } from "./FactCheckButton";
import { RichMessage } from "./RichMessage";
import { ToolConfirmation } from "./ToolConfirmation";
import { ToolIndicator } from "./ToolIndicator";

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

export function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const tier = (msg.metadata?.model_tier as string) || "";
  const events = (msg.metadata?.tool_events as ToolEvent[] | undefined) ?? [];
  const confirmation = msg.metadata?.confirmation as
    | ConfirmationRequest
    | undefined;
  const research = msg.metadata?.research;
  const researchMode = msg.metadata?.research_mode;

  const hasScreenshotEvent = events.some((e) => e.screenshot);
  const hasAppsEvent = events.some((e) => e.apps?.length);
  const hasFilesEvent = events.some((e) => e.files?.length);
  const hasCodeEvent = events.some((e) => e.code);
  const hasDiffEvent = events.some((e) => e.diff);
  const hasProposalEvent = events.some((e) => e.proposal);
  const hasDocCitations = Array.isArray(msg.metadata?.document_citations)
    && (msg.metadata?.document_citations as unknown[]).length > 0;

  // Assistant messages with rich content go through the richer renderer.
  if (
    !isUser &&
    (research ||
      researchMode ||
      hasScreenshotEvent ||
      hasAppsEvent ||
      hasFilesEvent ||
      hasCodeEvent ||
      hasDiffEvent ||
      hasProposalEvent ||
      hasDocCitations)
  ) {
    return <RichMessage msg={msg} />;
  }

  return (
    <div
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"} mb-4`}
    >
      <div className="max-w-[80%] w-full">
        {!isUser && events.length > 0 && <ToolIndicator events={events} />}
        <div
          className={`px-4 py-3 rounded-2xl whitespace-pre-wrap leading-relaxed ${
            isUser
              ? "bg-kira-accent text-black"
              : "bg-kira-panel text-kira-text"
          }`}
        >
          {isUser ? msg.content : linkify(msg.content)}
        </div>
        {!isUser && (
          <div className="text-[10px] uppercase tracking-wider text-kira-muted mt-1 ml-1 flex items-center flex-wrap gap-2">
            {tier && <span>{tier}</span>}
            {Array.isArray(msg.metadata?.source_tags) && (
              <SourceTags tags={msg.metadata!.source_tags as string[]} />
            )}
            {msg.metadata?.confidence && (
              <ConfidenceBadge
                confidence={(msg.metadata!.confidence as any).confidence}
                reason={(msg.metadata!.confidence as any).reason}
              />
            )}
            <FactCheckButton claim={msg.content} />
          </div>
        )}
        {!isUser && confirmation && (
          <ToolConfirmation confirmation={confirmation} />
        )}
      </div>
    </div>
  );
}
