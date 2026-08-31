import type {
  Agent,
  AgentCreateInput,
  Artifact,
  ArtifactVersion,
  Attachment,
  ChatMessage,
  ChatResponse,
  Conversation,
  ConversationCreateInput,
  ConversationMemory,
  ConversationUpdateInput,
  ModelOption,
  StructuredDiff,
  ToolOption,
  ToolPreferences,
} from "./types";

const API_PREFIX = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
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

export function postJSON<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

export function sendChatMessage(
  content: string,
  conversationId: string,
  selectedAgents: string[],
  quotedMessageId?: string,
  quotedText?: string,
  attachmentIds: string[] = [],
  modelProvider?: string,
  modelName?: string,
  agentMode?: "single" | "multi",
  toolPreferences?: ToolPreferences,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return postJSON<ChatResponse>(
    "/chat",
    {
      conversation_id: conversationId,
      message: {
        role: "user",
        content,
        format: "markdown",
        quoted_message_id: quotedMessageId,
        quoted_text: quotedText,
        attachment_ids: attachmentIds,
      },
      selected_agents: selectedAgents,
      model_provider: modelProvider,
      model_name: modelName,
      agent_mode: agentMode,
      tool_preferences: toolPreferences,
    },
    signal,
  );
}

export function regenerateChatMessage(
  content: string,
  conversationId: string,
  selectedAgents: string[],
  regenerateFromMessageId?: string,
  modelProvider?: string,
  modelName?: string,
  agentMode?: "single" | "multi",
  toolPreferences?: ToolPreferences,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return postJSON<ChatResponse>(
    "/chat/regenerate",
    {
      conversation_id: conversationId,
      message: {
        role: "user",
        content,
        format: "markdown",
      },
      selected_agents: selectedAgents,
      regenerate_from_message_id: regenerateFromMessageId,
      model_provider: modelProvider,
      model_name: modelName,
      agent_mode: agentMode,
      tool_preferences: toolPreferences,
    },
    signal,
  );
}

export async function getAgents(): Promise<Agent[]> {
  const data = await request<{ agents: Agent[] }>("/agents");
  return data.agents;
}

export async function createAgent(input: AgentCreateInput): Promise<Agent> {
  const data = await request<{ agent: Agent }>("/agents", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data.agent;
}

export async function updateAgent(agentId: string, input: AgentCreateInput): Promise<Agent> {
  const data = await request<{ agent: Agent }>(`/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return data.agent;
}

export async function deleteAgent(agentId: string): Promise<void> {
  await request<{ deleted: boolean }>(`/agents/${agentId}`, {
    method: "DELETE",
  });
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
  trashed?: boolean;
}): Promise<Conversation[]> {
  const params = new URLSearchParams();
  if (options?.search) {
    params.set("search", options.search);
  }
  if (options?.archived) {
    params.set("archived", "true");
  }
  if (options?.trashed) {
    params.set("trashed", "true");
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

export async function trashConversation(conversationId: string): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}/trash`,
    { method: "PATCH" },
  );
  return data.conversation;
}

export async function restoreConversation(conversationId: string): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}/restore`,
    { method: "PATCH" },
  );
  return data.conversation;
}

export async function deleteConversation(conversationId: string): Promise<Conversation> {
  const data = await request<{ conversation: Conversation }>(
    `/conversations/${conversationId}`,
    { method: "DELETE" },
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

export async function getConversationMemories(
  conversationId: string,
): Promise<ConversationMemory[]> {
  const data = await request<{ memories: ConversationMemory[] }>(
    `/conversations/${conversationId}/memories`,
  );
  return data.memories;
}

export async function extractMessageMemory(
  conversationId: string,
  messageId: string,
  modelProvider?: string,
  modelName?: string,
): Promise<ConversationMemory[]> {
  const data = await request<{ memories: ConversationMemory[] }>(
    `/conversations/${conversationId}/messages/${messageId}/extract-memory`,
    {
      method: "POST",
      body: JSON.stringify({
        model_provider: modelProvider,
        model_name: modelName,
      }),
    },
  );
  return data.memories;
}

export async function deleteConversationMemory(
  conversationId: string,
  memoryId: string,
): Promise<ConversationMemory> {
  const data = await request<{ memory: ConversationMemory }>(
    `/conversations/${conversationId}/memories/${memoryId}`,
    { method: "DELETE" },
  );
  return data.memory;
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

export async function updateArtifact(
  artifactId: string,
  input: { title?: string; content?: string; language?: string },
): Promise<Artifact> {
  const data = await request<{ artifact: Artifact }>(`/artifacts/${artifactId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return data.artifact;
}

export async function getArtifactVersions(artifactId: string): Promise<ArtifactVersion[]> {
  const data = await request<{ versions: ArtifactVersion[] }>(`/artifacts/${artifactId}/versions`);
  return data.versions;
}

export async function restoreArtifactVersion(
  artifactId: string,
  versionId: string,
): Promise<Artifact> {
  const data = await request<{ artifact: Artifact }>(
    `/artifacts/${artifactId}/versions/${versionId}/restore`,
    { method: "POST" },
  );
  return data.artifact;
}

export async function getArtifactDiff(artifactId: string): Promise<StructuredDiff> {
  return request<StructuredDiff>(`/artifacts/${artifactId}/diff`);
}

export function runWorkflowArtifact(
  artifactId: string,
  modelProvider?: string,
  modelName?: string,
): Promise<ChatResponse> {
  return request<ChatResponse>(`/artifacts/${artifactId}/run`, {
    method: "POST",
    body: JSON.stringify({
      model_provider: modelProvider,
      model_name: modelName,
    }),
  });
}
