import type {
  Agent,
  Artifact,
  Attachment,
  ChatMessage,
  ChatResponse,
  Conversation,
  ConversationCreateInput,
  ConversationUpdateInput,
  ModelOption,
  ToolOption,
  ToolPreferences,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function sendChatMessage(
  content: string,
  conversationId: string,
  selectedAgents: string[],
  quotedMessageId?: string,
  attachmentIds: string[] = [],
  modelProvider?: string,
  modelName?: string,
  agentMode?: "single" | "multi",
  toolPreferences?: ToolPreferences,
): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: conversationId,
      message: {
        role: "user",
        content,
        format: "markdown",
        quoted_message_id: quotedMessageId,
        attachment_ids: attachmentIds,
      },
      selected_agents: selectedAgents,
      model_provider: modelProvider,
      model_name: modelName,
      agent_mode: agentMode,
      tool_preferences: toolPreferences,
    }),
  });
}

export function regenerateChatMessage(
  content: string,
  conversationId: string,
  selectedAgents: string[],
  modelProvider?: string,
  modelName?: string,
  agentMode?: "single" | "multi",
  toolPreferences?: ToolPreferences,
): Promise<ChatResponse> {
  return request<ChatResponse>("/chat/regenerate", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: conversationId,
      message: {
        role: "user",
        content,
        format: "markdown",
      },
      selected_agents: selectedAgents,
      model_provider: modelProvider,
      model_name: modelName,
      agent_mode: agentMode,
      tool_preferences: toolPreferences,
    }),
  });
}

export async function getAgents(): Promise<Agent[]> {
  const data = await request<{ agents: Agent[] }>("/agents");
  return data.agents;
}

export async function getModels(): Promise<ModelOption[]> {
  const data = await request<{ models: ModelOption[] }>("/models");
  return data.models;
}

export async function getTools(): Promise<ToolOption[]> {
  const data = await request<{ tools: ToolOption[] }>("/tools");
  return data.tools;
}

export async function getConversations(options?: {
  search?: string;
  archived?: boolean;
}): Promise<Conversation[]> {
  const params = new URLSearchParams();
  if (options?.search) {
    params.set("search", options.search);
  }
  if (options?.archived) {
    params.set("archived", "true");
  }
  const query = params.toString();
  const data = await request<{ conversations: Conversation[] }>(
    `/conversations${query ? `?${query}` : ""}`,
  );
  return data.conversations;
}

export async function createConversation(
  input: ConversationCreateInput = {},
): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>("/conversations", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data.conversation;
}

export async function updateConversation(
  conversationId: string,
  input: ConversationUpdateInput,
): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}`,
    {
      method: "PATCH",
      body: JSON.stringify(input),
    },
  );
  return data.conversation;
}

export async function pinConversation(conversationId: string): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}/pin`,
    { method: "PATCH" },
  );
  return data.conversation;
}

export async function unpinConversation(conversationId: string): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}/unpin`,
    { method: "PATCH" },
  );
  return data.conversation;
}

export async function archiveConversation(conversationId: string): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}/archive`,
    { method: "PATCH" },
  );
  return data.conversation;
}

export async function unarchiveConversation(conversationId: string): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}/unarchive`,
    { method: "PATCH" },
  );
  return data.conversation;
}

export async function getConversationMessages(
  conversationId: string,
): Promise<ChatMessage[]> {
  const data = await request<{ messages: ChatMessage[] }>(
    `/conversations/${conversationId}/messages`,
  );
  return data.messages;
}

export async function getConversationArtifacts(
  conversationId: string,
): Promise<Artifact[]> {
  const data = await request<{ artifacts: Artifact[] }>(
    `/conversations/${conversationId}/artifacts`,
  );
  return data.artifacts;
}

export async function uploadAttachment(
  conversationId: string,
  input: {
    filename: string;
    content_base64: string;
    mime_type?: string;
  },
): Promise<Attachment> {
  const data = await request<{ attachment: Attachment }>(
    `/conversations/${conversationId}/attachments`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
  return data.attachment;
}

export async function getConversationAttachments(
  conversationId: string,
): Promise<Attachment[]> {
  const data = await request<{ attachments: Attachment[] }>(
    `/conversations/${conversationId}/attachments`,
  );
  return data.attachments;
}

export async function pinMessage(
  conversationId: string,
  messageId: string,
): Promise<ChatMessage> {
  const data = await request<{ message: ChatMessage }>(
    `/conversations/${conversationId}/messages/${messageId}/pin`,
    { method: "PATCH" },
  );
  return data.message;
}

export async function unpinMessage(
  conversationId: string,
  messageId: string,
): Promise<ChatMessage> {
  const data = await request<{ message: ChatMessage }>(
    `/conversations/${conversationId}/messages/${messageId}/unpin`,
    { method: "PATCH" },
  );
  return data.message;
}

export async function applyArtifactDiff(artifactId: string): Promise<{
  id: string;
  artifact_id: string;
  changed_files: string[];
  status: string;
}> {
  const data = await request<{
    application: {
      id: string;
      artifact_id: string;
      changed_files: string[];
      status: string;
    };
  }>(`/artifacts/${artifactId}/apply`, { method: "POST" });
  return data.application;
}

