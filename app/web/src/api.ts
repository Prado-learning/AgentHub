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
  DebugStage,
  ModelOption,
  PendingDecision,
  StructuredDiff,
  ToolOption,
  ToolPreferences,
  TraceEvent,
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
  return runChat(
    "/chat/start",
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
  return runChat(
    "/chat/start",
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

export async function applyArtifactDiff(artifactId: string, reviewToken: string, hunkIds: string[]): Promise<{
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
  }>(`/artifacts/${artifactId}/apply`, { method: "POST", body: JSON.stringify({review_token: reviewToken, hunk_ids: hunkIds}) });
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

export function runWorkflowArtifact(artifactId: string, modelProvider?: string, modelName?: string, signal?: AbortSignal): Promise<ChatResponse> {
  return runChat(`/artifacts/${artifactId}/start`, {model_provider:modelProvider,model_name:modelName},signal);
}

export async function listPendingDecisions(): Promise<PendingDecision[]> {
  const data = await request<{ pending_confirmations: PendingDecision[] }>(
    "/runs/pending-confirmations",
  );
  return data.pending_confirmations;
}

export async function listPendingDecisionsForRun(
  runId: string,
): Promise<PendingDecision[]> {
  const data = await request<{ pending_confirmations: PendingDecision[] }>(
    `/runs/${runId}/pending-confirmations`,
  );
  return data.pending_confirmations;
}

export async function confirmRunStep(
  runId: string,
  stepId: string,
  input: { actor?: string; note?: string; fingerprint: string },
): Promise<PendingDecision> {
  const data = await request<{ decision: PendingDecision }>(
    `/runs/${runId}/steps/${stepId}/confirm`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
  return data.decision;
}

export async function declineRunStep(
  runId: string,
  stepId: string,
  input: { actor?: string; reason?: string; fingerprint: string },
): Promise<PendingDecision> {
  const data = await request<{ decision: PendingDecision }>(
    `/runs/${runId}/steps/${stepId}/decline`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
  return data.decision;
}

export async function getDebugTrace(runId: string): Promise<DebugStage[]> {
  const data = await request<{ stages: DebugStage[] }>(`/runs/${runId}/debug-trace`);
  return data.stages;
}

async function runChat(path: string, body: unknown, signal?: AbortSignal): Promise<ChatResponse> {
  // Always receive the run id so cancelling the browser request cannot orphan a run.
  const started = await postJSON<{run_id: string; conversation_id: string}>(path, body);
  const conversationId = started.conversation_id;
  const events: TraceEvent[] = [];
  let cursor = 0;
  for (;;) {
    if (signal?.aborted) {
      await postJSON(`/runs/${started.run_id}/cancel`, {});
      throw new DOMException("Cancellation requested", "AbortError");
    }
    const state = await request<{status: string; error?: string; response?: ChatResponse; cursor: number; events: TraceEvent[]}>(`/runs/${started.run_id}?after=${cursor}`);
    events.push(...state.events);
    cursor = state.cursor;
    window.dispatchEvent(new CustomEvent("agenthub:run-progress", {detail: {conversationId, runId: started.run_id, status: state.status, events: [...events]}}));
    if (!["queued", "running", "cancelling"].includes(state.status)) {
      if (state.response) return state.response;
      if (state.status === "cancelled") throw new DOMException("Run cancelled", "AbortError");
      throw new Error(state.error || `Run ended: ${state.status}`);
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
}

export async function listConversationRuns(conversationId: string): Promise<Array<{run_id:string;status:string}>> {
  return (await request<{runs:Array<{run_id:string;status:string}>}>(`/runs?conversation_id=${encodeURIComponent(conversationId)}`)).runs;
}
