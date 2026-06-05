import type { Agent, ChatResponse } from "./types";

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

export function sendChatMessage(content: string): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: "conv_demo",
      message: {
        role: "user",
        content,
        format: "markdown",
      },
      selected_agents: ["orchestrator", "ui_builder", "code_reviewer"],
    }),
  });
}

export async function getAgents(): Promise<Agent[]> {
  const data = await request<{ agents: Agent[] }>("/agents");
  return data.agents;
}

