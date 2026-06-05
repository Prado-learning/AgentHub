import { FormEvent, useEffect, useMemo, useState } from "react";

import { getAgents, sendChatMessage } from "./api";
import type { Agent, Artifact, ChatMessage } from "./types";

const initialPrompt = "帮我做一个 Todo List 页面";

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [input, setInput] = useState(initialPrompt);
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    getAgents()
      .then(setAgents)
      .catch((err: Error) => setError(`Agent 列表加载失败：${err.message}`));
  }, []);

  const hasArtifacts = artifacts.length > 0;
  const canSend = useMemo(() => input.trim().length > 0 && !isSending, [input, isSending]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content || isSending) {
      return;
    }

    const userMessage: ChatMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      sender: "you",
      content,
      format: "markdown",
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setError("");
    setIsSending(true);

    try {
      const response = await sendChatMessage(content);
      setMessages((current) => [...current, ...response.messages]);
      setArtifacts(response.artifacts);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`发送失败：${message}`);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <header className="masthead">
          <div>
            <h1>AgentHub Demo</h1>
            <p>IM-style Multi-Agent Collaboration Demo</p>
          </div>
          <span className="status-pill">Day 1</span>
        </header>

        <section className="agent-strip" aria-label="Agent list">
          {agents.map((agent) => (
            <article className="agent-item" key={agent.id}>
              <strong>{agent.name}</strong>
              <span>{agent.description}</span>
            </article>
          ))}
        </section>

        <section className="chat-panel" aria-label="Chat messages">
          {messages.length === 0 ? (
            <div className="empty-state">
              <strong>Start a demo run</strong>
              <span>Send a message to trigger mock agent collaboration.</span>
            </div>
          ) : (
            messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-meta">
                  <span>{message.role === "user" ? "You" : message.sender}</span>
                  <small>{message.format}</small>
                </div>
                <p>{message.content}</p>
              </article>
            ))
          )}
        </section>

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Tell AgentHub what to build..."
            rows={4}
          />
          <div className="composer-actions">
            {error ? <p className="error-text">{error}</p> : <span />}
            <button disabled={!canSend} type="submit">
              {isSending ? "Sending..." : "Send"}
            </button>
          </div>
        </form>
      </section>

      <aside className="artifact-panel" aria-label="Artifacts">
        <header>
          <h2>Artifacts</h2>
          <span>{artifacts.length}</span>
        </header>
        {!hasArtifacts ? (
          <p className="artifact-empty">Generated code, reviews, and previews will appear here.</p>
        ) : (
          artifacts.map((artifact) => <ArtifactCard artifact={artifact} key={artifact.id} />)
        )}
      </aside>
    </main>
  );
}

function ArtifactCard({ artifact }: { artifact: Artifact }) {
  return (
    <article className="artifact-card">
      <div className="artifact-card-header">
        <span>{artifact.type}</span>
        <strong>{artifact.title}</strong>
      </div>
      {artifact.content ? (
        <pre>{artifact.content}</pre>
      ) : (
        <a href={`http://localhost:8000${artifact.preview_url}`} target="_blank" rel="noreferrer">
          Open preview
        </a>
      )}
    </article>
  );
}

export default App;

