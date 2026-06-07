export type Agent = {
  id: string;
  name: string;
  description: string;
  capabilities?: string[];
  tools?: string[];
  skills?: string[];
  model_provider?: string;
  model_name?: string;
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
  attachment_ids?: string[];
  is_pinned?: boolean;
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
  type: "code" | "review" | "preview" | "conflict" | "diff" | "file" | "image";
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
};

export type ChatResponse = {
  run_id: string;
  status: string;
  messages: ChatMessage[];
  artifacts: Artifact[];
  events?: Array<{
    type: string;
    payload: Record<string, unknown>;
    created_at: string;
  }>;
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

