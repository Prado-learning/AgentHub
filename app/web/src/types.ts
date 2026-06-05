export type Agent = {
  id: string;
  name: string;
  description: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "agent" | "system";
  sender?: string;
  content: string;
  format: string;
};

export type Artifact = {
  id: string;
  type: "code" | "review" | "preview";
  title: string;
  language?: string;
  content?: string;
  preview_url?: string;
};

export type ChatResponse = {
  run_id: string;
  status: string;
  messages: ChatMessage[];
  artifacts: Artifact[];
};

