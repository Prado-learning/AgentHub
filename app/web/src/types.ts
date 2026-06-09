export type Agent = {
  id: string;
  name: string;
  description: string;
  capabilities?: string[];
  tools?: string[];
  skills?: string[];
  system_prompt?: string;
  model_provider?: string;
  model_name?: string;
  avatar?: string;
  is_custom?: boolean;
};

export type ToolOption = {
  id: string;
  name?: string;
  description?: string;
};

export type ModelOption = {
  id: string;
  name: string;
  provider: string;
  env_prefix?: string;
};

export type ConversationMode = "single" | "group";

export type Conversation = {
  id: string;
  title: string;
  mode: ConversationMode;
  agent_ids: string[];
  is_pinned: boolean;
  is_archived: boolean;
  is_trashed?: boolean;
  created_at: string;
  updated_at: string;
  last_message: string;
};

export type ChatMessage = {
  id: string;
  conversation_id?: string;
  role: "user" | "agent" | "system";
  sender?: string | null;
  content: string;
  format: string;
  artifact_ids?: string[];
  quoted_message_id?: string | null;
  quoted_text?: string | null;
  quoted_artifact_id?: string | null;
  quoted_range?: Record<string, unknown> | null;
  attachment_ids?: string[];
  generation_group_id?: string | null;
  generation_index?: number | null;
  replaces_message_ids?: string[];
  is_active_generation?: boolean;
  is_pinned?: boolean;
  trace_events?: TraceEvent[];
  created_at?: string;
};

export type Attachment = {
  id: string;
  conversation_id: string;
  type: "image" | "file";
  filename: string;
  mime_type: string;
  size: number;
  url: string;
  extracted_text?: string;
};

export type Artifact = {
  id: string;
  type:
    | "code"
    | "review"
    | "preview"
    | "conflict"
    | "diff"
    | "file"
    | "image"
    | "deployment"
    | "document_preview"
    | "presentation_preview"
    | "workflow";
  title: string;
  language?: string;
  content?: string;
  preview_url?: string;
  file_path?: string;
  conflict_group?: string;
  conflict_type?: string;
  conflict_target?: string;
  status?: "pending" | "applied" | "failed" | "rolled_back";
  apply_id?: string;
  target_files?: string[];
  deployment_id?: string;
  deployment_url?: string;
  logs?: string;
  source_attachment_id?: string;
  mime_type?: string;
  filename?: string;
  producer_agent_id?: string;
};

export type ArtifactVersion = {
  id: string;
  artifact_id: string;
  title?: string;
  language?: string;
  content: string;
  reason: string;
  created_at: string;
};

export type StructuredDiffLine = {
  type: "context" | "add" | "remove";
  old_no?: number | null;
  new_no?: number | null;
  content: string;
};

export type StructuredDiff = {
  artifact_id: string;
  files: Array<{
    old_path: string;
    new_path: string;
    hunks: Array<{
      header: string;
      lines: StructuredDiffLine[];
    }>;
  }>;
};

export type ChatResponse = {
  run_id: string;
  status: string;
  messages: ChatMessage[];
  artifacts: Artifact[];
  events?: TraceEvent[];
  created_agent?: Agent | null;
};

export type ConversationMemory = {
  id: string;
  conversation_id: string;
  source_message_id?: string;
  content: string;
  category: "preference" | "constraint" | "decision" | "goal" | "open_task";
  confidence: number;
  created_by: "llm";
  model_provider?: string;
  created_at: string;
};

export type TraceEvent = {
  id?: string;
  run_id?: string;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
  title?: string;
  detail?: string;
  status?: "pending" | "running" | "done" | "error";
  agent_id?: string | null;
  duration_ms?: number | null;
  metadata?: Record<string, unknown>;
};

export type ToolPreferences = {
  file: boolean;
  image: boolean;
  preview: boolean;
  diff: boolean;
};

export type ConversationCreateInput = {
  title?: string;
  mode?: ConversationMode;
  agent_ids?: string[];
};

export type ConversationUpdateInput = {
  title?: string;
  mode?: ConversationMode;
  agent_ids?: string[];
};

export type AgentCreateInput = {
  id?: string;
  name?: string;
  description?: string;
  system_prompt?: string;
  capabilities?: string[];
  tools?: string[];
  model_provider?: string;
  model_name?: string;
  avatar?: string;
};
