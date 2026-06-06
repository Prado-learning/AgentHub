import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import {
  archiveConversation,
  createConversation,
  getAgents,
  getConversationArtifacts,
  getConversationMessages,
  getConversations,
  pinConversation,
  regenerateChatMessage,
  sendChatMessage,
  unarchiveConversation,
  unpinConversation,
} from "./api";
import type { Agent, Artifact, ChatMessage, Conversation, ConversationMode } from "./types";

type Language = "zh" | "en";

const copy = {
  zh: {
    appName: "AgentHub",
    appTagline: "多 Agent 协作工作台",
    heroTitle: "用聊天驱动 Agent 协作、产物生成与预览",
    heroSubtitle: "统一调度 Orchestrator、UI Builder、Code Reviewer 和工具链，沉淀每一次会话上下文。",
    language: "语言",
    active: "活跃",
    archived: "归档",
    conversations: "会话",
    newConversation: "新建",
    createConversation: "创建会话",
    cancel: "取消",
    title: "标题",
    chatMode: "会话模式",
    singleChat: "单聊",
    groupChat: "群聊",
    chooseAgent: "选择 Agent",
    search: "搜索会话...",
    showActive: "查看活跃",
    showArchived: "查看归档",
    pinned: "置顶",
    noMessages: "暂无消息",
    pin: "置顶",
    unpin: "取消置顶",
    archive: "归档",
    restore: "恢复",
    agentsOnline: "Agents",
    artifacts: "产物",
    context: "上下文",
    mode: "模式",
    noConversation: "暂无会话",
    emptyTitle: "选择或新建一个会话",
    emptySubtitle: "输入任务后，AgentHub 会根据规则分派 Agent 和 Tool 并生成产物。",
    quote: "引用",
    quoted: "正在引用",
    clear: "清除",
    composerPlaceholder: "告诉 AgentHub 你想构建、审查、预览或调用哪个 @tool...",
    regenerate: "重新生成",
    send: "发送",
    sending: "发送中...",
    generatedArtifacts: "生成的代码、审查、预览和冲突卡片会显示在这里。",
    copy: "复制",
    expandPreview: "展开预览",
    openPreview: "打开预览",
    close: "关闭",
    preview: "预览",
    user: "你",
    statusReady: "已就绪",
    statusRunning: "运行中",
    selectedAgents: "参与 Agent",
    createError: "创建会话失败",
    loadAgentsError: "Agent 列表加载失败",
    loadConversationsError: "会话加载失败",
    loadMessagesError: "消息加载失败",
    loadArtifactsError: "产物加载失败",
    pinError: "置顶状态更新失败",
    archiveError: "归档状态更新失败",
    sendError: "发送失败",
    regenerateError: "重新生成失败",
    noUserMessage: "没有可重新生成的用户消息。",
  },
  en: {
    appName: "AgentHub",
    appTagline: "Multi-agent collaboration workspace",
    heroTitle: "Chat with agents to build, review, and preview artifacts",
    heroSubtitle: "Coordinate Orchestrator, UI Builder, Code Reviewer, and tools with persistent context.",
    language: "Language",
    active: "Active",
    archived: "Archived",
    conversations: "Conversations",
    newConversation: "New",
    createConversation: "Create conversation",
    cancel: "Cancel",
    title: "Title",
    chatMode: "Chat mode",
    singleChat: "Single",
    groupChat: "Group",
    chooseAgent: "Choose Agent",
    search: "Search conversations...",
    showActive: "Show active",
    showArchived: "Show archived",
    pinned: "Pinned",
    noMessages: "No messages yet",
    pin: "Pin",
    unpin: "Unpin",
    archive: "Archive",
    restore: "Restore",
    agentsOnline: "Agents",
    artifacts: "Artifacts",
    context: "Context",
    mode: "Mode",
    noConversation: "No conversation",
    emptyTitle: "Select or create a conversation",
    emptySubtitle: "Send a task and AgentHub will dispatch agents, tools, and artifacts.",
    quote: "Quote",
    quoted: "Quoting",
    clear: "Clear",
    composerPlaceholder: "Tell AgentHub what to build, review, preview, or which @tool to call...",
    regenerate: "Regenerate",
    send: "Send",
    sending: "Sending...",
    generatedArtifacts: "Generated code, reviews, previews, and conflict cards will appear here.",
    copy: "Copy",
    expandPreview: "Expand preview",
    openPreview: "Open preview",
    close: "Close",
    preview: "Preview",
    user: "You",
    statusReady: "Ready",
    statusRunning: "Running",
    selectedAgents: "Selected agents",
    createError: "Create conversation failed",
    loadAgentsError: "Agent list load failed",
    loadConversationsError: "Conversation load failed",
    loadMessagesError: "Message load failed",
    loadArtifactsError: "Artifact load failed",
    pinError: "Pin update failed",
    archiveError: "Archive update failed",
    sendError: "Send failed",
    regenerateError: "Regenerate failed",
    noUserMessage: "No user message to regenerate.",
  },
} satisfies Record<Language, Record<string, string>>;

const defaultAgentIds = ["orchestrator", "codex", "ui_builder", "code_reviewer"];
const initialPrompt = "帮我生成一个现代 Todo List 页面，并给出代码审查建议";

function App() {
  const [language, setLanguage] = useState<Language>("zh");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [conversationSearch, setConversationSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [quotedMessage, setQuotedMessage] = useState<ChatMessage | null>(null);
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null);
  const [input, setInput] = useState(initialPrompt);
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftMode, setDraftMode] = useState<ConversationMode>("group");
  const [draftAgentIds, setDraftAgentIds] = useState<string[]>(defaultAgentIds);

  const t = copy[language];

  useEffect(() => {
    getAgents()
      .then(setAgents)
      .catch((err: Error) => setError(`${t.loadAgentsError}: ${err.message}`));
  }, [t.loadAgentsError]);

  useEffect(() => {
    let shouldIgnore = false;

    getConversations({ search: conversationSearch, archived: showArchived })
      .then((items) => {
        if (shouldIgnore) {
          return;
        }
        setConversations(items);
        setActiveConversationId((current) => {
          if (current && items.some((item) => item.id === current)) {
            return current;
          }
          return items[0]?.id ?? "";
        });
      })
      .catch((err: Error) => setError(`${t.loadConversationsError}: ${err.message}`));

    return () => {
      shouldIgnore = true;
    };
  }, [conversationSearch, showArchived, t.loadConversationsError]);

  useEffect(() => {
    if (!activeConversationId) {
      setMessages([]);
      return;
    }

    let shouldIgnore = false;
    getConversationMessages(activeConversationId)
      .then((items) => {
        if (!shouldIgnore) {
          setMessages(items);
        }
      })
      .catch((err: Error) => setError(`${t.loadMessagesError}: ${err.message}`));

    return () => {
      shouldIgnore = true;
    };
  }, [activeConversationId, t.loadMessagesError]);

  useEffect(() => {
    if (!activeConversationId) {
      setArtifacts([]);
      return;
    }

    let shouldIgnore = false;
    getConversationArtifacts(activeConversationId)
      .then((items) => {
        if (!shouldIgnore) {
          setArtifacts(items);
        }
      })
      .catch((err: Error) => setError(`${t.loadArtifactsError}: ${err.message}`));

    return () => {
      shouldIgnore = true;
    };
  }, [activeConversationId, t.loadArtifactsError]);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId),
    [activeConversationId, conversations],
  );
  const canSend = useMemo(
    () => input.trim().length > 0 && !isSending && Boolean(activeConversation),
    [activeConversation, input, isSending],
  );
  const hasArtifacts = artifacts.length > 0;

  async function reloadConversations(preferredId?: string) {
    const items = await getConversations({ search: conversationSearch, archived: showArchived });
    setConversations(items);
    if (preferredId && items.some((item) => item.id === preferredId)) {
      setActiveConversationId(preferredId);
      return;
    }
    setActiveConversationId((current) => {
      if (current && items.some((item) => item.id === current)) {
        return current;
      }
      return items[0]?.id ?? "";
    });
  }

  function openCreatePanel() {
    setDraftTitle(language === "zh" ? "新会话" : "New Conversation");
    setDraftMode("group");
    setDraftAgentIds(defaultAgentIds);
    setIsCreateOpen(true);
  }

  function handleDraftModeChange(mode: ConversationMode) {
    setDraftMode(mode);
    setDraftAgentIds(mode === "single" ? [draftAgentIds[0] ?? "orchestrator"] : defaultAgentIds);
  }

  function toggleDraftAgent(agentId: string) {
    if (draftMode === "single") {
      setDraftAgentIds([agentId]);
      return;
    }
    setDraftAgentIds((current) => {
      if (current.includes(agentId)) {
        const next = current.filter((id) => id !== agentId);
        return next.length ? next : ["orchestrator"];
      }
      return [...current, agentId];
    });
  }

  async function handleCreateConversation(event: FormEvent) {
    event.preventDefault();
    try {
      const conversation = await createConversation({
        title: draftTitle.trim() || (language === "zh" ? "新会话" : "New Conversation"),
        mode: draftMode,
        agent_ids: draftMode === "single" ? [draftAgentIds[0] ?? "orchestrator"] : draftAgentIds,
      });
      setIsCreateOpen(false);
      setShowArchived(false);
      setConversationSearch("");
      await reloadConversations(conversation.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`${t.createError}: ${message}`);
    }
  }

  async function handlePinConversation(conversation: Conversation) {
    try {
      if (conversation.is_pinned) {
        await unpinConversation(conversation.id);
      } else {
        await pinConversation(conversation.id);
      }
      await reloadConversations(conversation.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`${t.pinError}: ${message}`);
    }
  }

  async function handleArchiveConversation(conversation: Conversation) {
    try {
      if (conversation.is_archived) {
        await unarchiveConversation(conversation.id);
        setShowArchived(false);
      } else {
        await archiveConversation(conversation.id);
      }
      await reloadConversations();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`${t.archiveError}: ${message}`);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content || isSending || !activeConversation) {
      return;
    }

    const userMessage: ChatMessage = {
      id: `user_${Date.now()}`,
      conversation_id: activeConversation.id,
      role: "user",
      sender: "you",
      content,
      format: "markdown",
      quoted_message_id: quotedMessage?.id,
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setError("");
    setIsSending(true);

    try {
      const response = await sendChatMessage(
        content,
        activeConversation.id,
        activeConversation.agent_ids,
        quotedMessage?.id,
      );
      setMessages((current) => [...current, ...response.messages]);
      setArtifacts((current) => [...current, ...response.artifacts]);
      setQuotedMessage(null);
      await reloadConversations(activeConversation.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`${t.sendError}: ${message}`);
    } finally {
      setIsSending(false);
    }
  }

  async function handleRegenerate() {
    if (!activeConversation || isSending) {
      return;
    }
    const lastUserMessage = [...messages].reverse().find((message) => message.role === "user");
    if (!lastUserMessage) {
      setError(t.noUserMessage);
      return;
    }

    setError("");
    setIsSending(true);
    try {
      const response = await regenerateChatMessage(
        lastUserMessage.content,
        activeConversation.id,
        activeConversation.agent_ids,
      );
      setMessages((current) => [...current, ...response.messages]);
      setArtifacts((current) => [...current, ...response.artifacts]);
      await reloadConversations(activeConversation.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(`${t.regenerateError}: ${message}`);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">AH</div>
          <div>
            <strong>{t.appName}</strong>
            <span>{t.appTagline}</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className={`live-dot ${isSending ? "running" : ""}`}>
            {isSending ? t.statusRunning : t.statusReady}
          </span>
          <label className="language-switch">
            <span>{t.language}</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value as Language)}>
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>
      </section>

      <aside className="conversation-sidebar" aria-label={t.conversations}>
        <header className="panel-header">
          <div>
            <span className="eyebrow">{showArchived ? t.archived : t.active}</span>
            <h2>{t.conversations}</h2>
          </div>
          <button className="primary-mini" type="button" onClick={openCreatePanel}>
            {t.newConversation}
          </button>
        </header>

        {isCreateOpen ? (
          <form className="create-panel" onSubmit={handleCreateConversation}>
            <label>
              <span>{t.title}</span>
              <input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} />
            </label>
            <fieldset>
              <legend>{t.chatMode}</legend>
              <label>
                <input
                  checked={draftMode === "single"}
                  name="chat-mode"
                  onChange={() => handleDraftModeChange("single")}
                  type="radio"
                />
                <span>{t.singleChat}</span>
              </label>
              <label>
                <input
                  checked={draftMode === "group"}
                  name="chat-mode"
                  onChange={() => handleDraftModeChange("group")}
                  type="radio"
                />
                <span>{t.groupChat}</span>
              </label>
            </fieldset>
            <fieldset>
              <legend>{t.chooseAgent}</legend>
              {agents.map((agent) => (
                <label key={agent.id}>
                  <input
                    checked={draftAgentIds.includes(agent.id)}
                    onChange={() => toggleDraftAgent(agent.id)}
                    type={draftMode === "single" ? "radio" : "checkbox"}
                  />
                  <span>{agent.name}</span>
                </label>
              ))}
            </fieldset>
            <div className="create-actions">
              <button className="ghost-button" type="button" onClick={() => setIsCreateOpen(false)}>
                {t.cancel}
              </button>
              <button className="primary-mini" type="submit">
                {t.createConversation}
              </button>
            </div>
          </form>
        ) : null}

        <input
          className="conversation-search"
          value={conversationSearch}
          onChange={(event) => setConversationSearch(event.target.value)}
          placeholder={t.search}
        />

        <button
          className="ghost-button full"
          type="button"
          onClick={() => setShowArchived((current) => !current)}
        >
          {showArchived ? t.showActive : t.showArchived}
        </button>

        <section className="conversation-list">
          {conversations.length === 0 ? (
            <p className="muted">{t.noConversation}</p>
          ) : (
            conversations.map((conversation) => (
              <article
                className={`conversation-item ${
                  conversation.id === activeConversationId ? "active" : ""
                }`}
                key={conversation.id}
                onClick={() => setActiveConversationId(conversation.id)}
              >
                <div className="conversation-title-row">
                  <strong>{conversation.title}</strong>
                  {conversation.is_pinned ? <span className="pin-mark">{t.pinned}</span> : null}
                </div>
                <span className="conversation-meta">
                  {conversation.mode} · {conversation.agent_ids.join(", ")}
                </span>
                <p>{conversation.last_message || t.noMessages}</p>
                <div className="conversation-actions">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      handlePinConversation(conversation);
                    }}
                  >
                    {conversation.is_pinned ? t.unpin : t.pin}
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      handleArchiveConversation(conversation);
                    }}
                  >
                    {conversation.is_archived ? t.restore : t.archive}
                  </button>
                </div>
              </article>
            ))
          )}
        </section>
      </aside>

      <section className="workspace">
        <header className="hero-card">
          <div>
            <span className="eyebrow">AgentHub Runtime</span>
            <h1>{t.heroTitle}</h1>
            <p>{t.heroSubtitle}</p>
          </div>
          <div className="hero-metrics">
            <Metric label={t.agentsOnline} value={agents.length.toString()} />
            <Metric label={t.artifacts} value={artifacts.length.toString()} />
            <Metric label={t.mode} value={activeConversation?.mode ?? "-"} />
          </div>
        </header>

        <section className="agent-strip" aria-label={t.selectedAgents}>
          {agents.map((agent) => (
            <article className="agent-item" key={agent.id}>
              <span className="agent-avatar">{agent.name.slice(0, 2).toUpperCase()}</span>
              <div>
                <strong>{agent.name}</strong>
                <span>{agent.description}</span>
              </div>
            </article>
          ))}
        </section>

        <section className="chat-panel" aria-label="Chat messages">
          <div className="chat-panel-header">
            <div>
              <span className="eyebrow">{t.context}</span>
              <h2>{activeConversation?.title ?? t.emptyTitle}</h2>
            </div>
            <span className="status-pill">{activeConversation?.mode ?? t.noConversation}</span>
          </div>

          <div className="chat-stream">
            {messages.length === 0 ? (
              <div className="empty-state">
                <strong>{activeConversation ? activeConversation.title : t.emptyTitle}</strong>
                <span>{t.emptySubtitle}</span>
              </div>
            ) : (
              messages.map((message) => (
                <article className={`message ${message.role}`} key={message.id}>
                  <div className="message-meta">
                    <span>{message.role === "user" ? t.user : message.sender}</span>
                    <small>{message.format}</small>
                  </div>
                  {message.quoted_message_id ? (
                    <small className="quoted-line">
                      {t.quoted}: {message.quoted_message_id}
                    </small>
                  ) : null}
                  <MarkdownMessage content={message.content} copyLabel={t.copy} />
                  <button
                    className="message-action"
                    type="button"
                    onClick={() => setQuotedMessage(message)}
                  >
                    {t.quote}
                  </button>
                </article>
              ))
            )}
          </div>
        </section>

        <form className="composer" onSubmit={handleSubmit}>
          {quotedMessage ? (
            <div className="quote-banner">
              <span>
                {t.quoted}: {quotedMessage.content.slice(0, 96)}
              </span>
              <button type="button" onClick={() => setQuotedMessage(null)}>
                {t.clear}
              </button>
            </div>
          ) : null}
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={t.composerPlaceholder}
            rows={4}
          />
          <div className="composer-actions">
            {error ? <p className="error-text">{error}</p> : <span />}
            <div className="composer-button-row">
              <button disabled={!activeConversation || isSending} type="button" onClick={handleRegenerate}>
                {t.regenerate}
              </button>
              <button className="send-button" disabled={!canSend} type="submit">
                {isSending ? t.sending : t.send}
              </button>
            </div>
          </div>
        </form>
      </section>

      <aside className="artifact-panel" aria-label={t.artifacts}>
        <header className="panel-header">
          <div>
            <span className="eyebrow">{t.preview}</span>
            <h2>{t.artifacts}</h2>
          </div>
          <span className="count-pill">{artifacts.length}</span>
        </header>
        {!hasArtifacts ? (
          <p className="artifact-empty">{t.generatedArtifacts}</p>
        ) : (
          artifacts.map((artifact) => (
            <ArtifactCard
              artifact={artifact}
              key={artifact.id}
              labels={t}
              onPreview={() => setPreviewArtifact(artifact)}
            />
          ))
        )}
      </aside>

      {previewArtifact ? (
        <div className="preview-modal" role="dialog" aria-modal="true">
          <div className="preview-modal-card">
            <header>
              <h2>{previewArtifact.title}</h2>
              <button type="button" onClick={() => setPreviewArtifact(null)}>
                {t.close}
              </button>
            </header>
            <iframe
              title={previewArtifact.title}
              src={`http://localhost:8000${previewArtifact.preview_url}`}
            />
          </div>
        </div>
      ) : null}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function MarkdownMessage({
  content,
  copyLabel,
}: {
  content: string;
  copyLabel: string;
}) {
  const blocks = parseMarkdownBlocks(content);

  return (
    <div className="message-body">
      {blocks.map((block, index) => {
        if (block.type === "code") {
          return <CodeBlock block={block} copyLabel={copyLabel} key={`${block.type}-${index}`} />;
        }
        return renderTextBlock(block.content, index);
      })}
    </div>
  );
}

type MarkdownBlock =
  | {
      type: "text";
      content: string;
    }
  | {
      type: "code";
      content: string;
      language: string;
    };

function parseMarkdownBlocks(content: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const fencePattern = /```([A-Za-z0-9_-]*)\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = fencePattern.exec(content)) !== null) {
    if (match.index > cursor) {
      blocks.push({
        type: "text",
        content: content.slice(cursor, match.index),
      });
    }
    blocks.push({
      type: "code",
      language: match[1] || "text",
      content: match[2].replace(/\n$/, ""),
    });
    cursor = match.index + match[0].length;
  }

  if (cursor < content.length) {
    blocks.push({
      type: "text",
      content: content.slice(cursor),
    });
  }

  return blocks.length ? blocks : [{ type: "text", content }];
}

function renderTextBlock(content: string, key: number): ReactNode {
  const paragraphs = content
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  if (!paragraphs.length) {
    return null;
  }

  return paragraphs.map((paragraph, index) => (
    <p key={`text-${key}-${index}`}>
      {paragraph.split("\n").map((line, lineIndex) => (
        <span key={`${line}-${lineIndex}`}>
          {line}
          {lineIndex < paragraph.split("\n").length - 1 ? <br /> : null}
        </span>
      ))}
    </p>
  ));
}

function CodeBlock({
  block,
  copyLabel,
}: {
  block: Extract<MarkdownBlock, { type: "code" }>;
  copyLabel: string;
}) {
  async function handleCopy() {
    await navigator.clipboard.writeText(block.content);
  }

  return (
    <div className="message-code-block">
      <div className="message-code-header">
        <span>{block.language}</span>
        <button type="button" onClick={handleCopy}>
          {copyLabel}
        </button>
      </div>
      <pre>
        <code>{block.content}</code>
      </pre>
    </div>
  );
}

function ArtifactCard({
  artifact,
  labels,
  onPreview,
}: {
  artifact: Artifact;
  labels: (typeof copy)[Language];
  onPreview: () => void;
}) {
  async function handleCopy() {
    await navigator.clipboard.writeText(artifact.content ?? artifact.preview_url ?? "");
  }

  return (
    <article className={`artifact-card ${artifact.type === "conflict" ? "conflict" : ""}`}>
      <div className="artifact-card-header">
        <span>{artifact.type}</span>
        <strong>{artifact.title}</strong>
      </div>
      <div className="artifact-actions">
        {artifact.content ? (
          <button type="button" onClick={handleCopy}>
            {labels.copy}
          </button>
        ) : null}
        {artifact.preview_url ? (
          <button type="button" onClick={onPreview}>
            {labels.expandPreview}
          </button>
        ) : null}
      </div>
      {artifact.content ? (
        <pre>{artifact.content}</pre>
      ) : (
        <a href={`http://localhost:8000${artifact.preview_url}`} target="_blank" rel="noreferrer">
          {labels.openPreview}
        </a>
      )}
    </article>
  );
}

export default App;
