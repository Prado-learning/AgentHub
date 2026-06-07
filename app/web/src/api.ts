import type {
  Agent,
  Artifact,
  ChatMessage,
  ChatResponse,
  Conversation,
  ConversationCreateInput,
  ConversationUpdateInput,
} from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
      },
      selected_agents: selectedAgents,
    }),
  });
}

export function regenerateChatMessage(
  content: string,
  conversationId: string,
  selectedAgents: string[],
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
    }),
  });
}

export async function getAgents(): Promise<Agent[]> {
  const data = await request<{ agents: Agent[] }>("/agents");
  return data.agents;
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
