export type Role = "user" | "assistant" | "system" | "tool";

export type KiraState =
  | "idle"
  | "listening"
  | "thinking"
  | "searching"
  | "executing"
  | "speaking"
  | "error"
  | "success";

export interface Message {
  id: string;
  conversation_id?: string | null;
  role: Role;
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface ChatResponse {
  message: Message;
  conversation_id: string;
  state: KiraState;
  memories_used: string[];
  model_used: string;
  latency_ms: number;
}

export interface Memory {
  id: string;
  content: string;
  category: "preference" | "fact" | "decision" | "task" | "observation";
  importance: number;
  source_type: string;
  source_id?: string | null;
  entity_id?: string | null;
  created_at: string;
}

export interface Entity {
  id: string;
  type: string;
  name: string;
  metadata?: Record<string, unknown>;
}

export interface Relationship {
  id: string;
  source_id: string;
  target_id: string;
  type: string;
  weight: number;
}

export interface ToolSpec {
  server: string;
  name: string;
  qualified_name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ServerStatus {
  name: string;
  transport: string;
  status: string;
  tool_count: number;
}

export interface ToolEvent {
  step: number;
  phase:
    | "start"
    | "ok"
    | "await_confirmation"
    | "denied"
    | "rate_limited"
    | "error";
  tool: string;
  arguments?: Record<string, unknown>;
  latency_ms?: number;
  message?: string;
  screenshot?: { base64: string; mime: string };
  apps?: string[];
  files?: string[];
  code?: { path: string; language?: string; content: string };
  diff?: { path: string; diff: string };
  proposal?: FixProposal;
}

export interface FixProposalEdit {
  path: string;
  old_text: string;
  new_text: string;
  diff?: string;
  preview_error?: string;
}

export interface FixProposal {
  repo_path?: string;
  diagnosis?: string;
  edits: FixProposalEdit[];
  test_command?: string | null;
}

export interface DocumentHit {
  id: string;
  file_path: string;
  file_name: string;
  chunk_index: number;
  page_number: number | null;
  content: string;
  score: number;
  indexed_at?: string | null;
}

export interface IndexedFile {
  file_path: string;
  file_name: string;
  indexed_at?: string | null;
  chunks: number;
}

export interface DocumentIndexEvent {
  stage: "start" | "parse" | "progress" | "indexed" | "skip" | "done" | "heartbeat";
  message?: string;
  detail?: Record<string, unknown>;
}

export type Intervention = "notify" | "suggest" | "act" | "silent";

export interface ProactiveScoredEvent {
  kind: string;
  title: string;
  message: string;
  urgency: number;
  relevance: number;
  actionability: number;
  score: number;
  intervention: Intervention;
  detail?: Record<string, unknown>;
  generated_at: string;
  dedupe_key?: string;
}

export interface ScheduledTaskSpec {
  name: string;
  cron: string | null;
  tool_chain: Array<{ name?: string; tool: string; arguments?: Record<string, unknown> }>;
  permissions_required: number;
  enabled: boolean;
  last_run: string | null;
  last_result: string | null;
  created_at: string | null;
}

export interface ConfirmationRequest {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
  risk_level: number;
  description: string;
  created_at: string;
}

export type Reliability = "high" | "medium" | "low";

export interface SourceHit {
  url: string;
  title: string;
  snippet: string;
  reliability: Reliability;
}

export interface ImageHit {
  url: string;
  alt?: string;
  source?: string;
  width?: number | null;
  height?: number | null;
  thumbnail?: string | null;
}

export interface VideoHit {
  url: string;
  title: string;
  thumbnail?: string;
  duration?: string;
  source?: string;
}

export interface ResearchPayload {
  summary: string;
  images: ImageHit[];
  videos: VideoHit[];
  sources: SourceHit[];
  related_queries: string[];
  plan?: string[];
}

export interface ResearchProgressEvent {
  stage:
    | "planning"
    | "searching"
    | "reading"
    | "synthesizing"
    | "waiting"
    | "done";
  message: string;
  detail?: Record<string, unknown>;
}
