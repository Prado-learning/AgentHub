import { ChangeEvent, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import {
  applyArtifactDiff,
  archiveConversation,
  createConversation,
  getAgents,
  getConversationArtifacts,
  getConversationAttachments,
  getConversationMessages,
  getConversations,
  getModels,
  getTools,
  pinConversation,
  pinMessage,
  regenerateChatMessage,
  sendChatMessage,
  unarchiveConversation,
  unpinConversation,
  unpinMessage,
  uploadAttachment,
} from "./api";
import type {
  Agent,
  Artifact,
  Attachment,
  ChatMessage,
  ChatResponse,
  Conversation,
  ConversationMode,
  ModelOption,
  ToolOption,
  ToolPreferences,
} from "./types";

const API_ORIGIN = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const defaultAgentIds = ["orchestrator", "codex", "ui_builder", "code_reviewer"];
const defaultToolPreferences: ToolPreferences = {
  file: true,
  image: true,
  preview: true,
  diff: false,
};

type RightPanelTab = "artifacts" | "agents" | "tools" | "context";
type ProgressStep = {
  id: string;
  label: string;
  detail?: string;
  status: "pending" | "active" | "done" | "error";
};

const labels = {
  appTagline: "多 Agent 协作工作台",
  ready: "已就绪",
  running: "运行中",
  active: "活跃",
  archived: "归档",
  conversations: "会话",
  new: "新建",
  search: "搜索会话...",
  showArchived: "查看归档",
  showActive: "查看活跃",
  pin: "置顶",
  unpin: "取消置顶",
  archive: "归档",
  restore: "恢复",
  title: "标题",
  single: "单 Agent",
  multi: "多 Agent",
  chooseAgent: "选择 Agent",
  cancel: "取消",
  create: "创建",
  emptyTitle: "选择或新建一个会话",
  placeholder: "告诉 AgentHub 你想构建、审查、预览或调用哪个 @tool...",
  send: "发送",
  sending: "执行中",
  regenerate: "重新生成",
  quote: "引用",
  quoted: "正在引用",
  clear: "清除",
  pinMessage: "Pin",
  unpinMessage: "Unpin",
  upload: "上传",
  pendingFiles: "待发送附件",
  artifacts: "产物",
  agents: "Agents",
  tools: "Tools",
  context: "Context",
  copy: "复制",
  preview: "预览",
  close: "关闭",
  applyDiff: "应用 Diff",
  applied: "已应用",
  copied: "复制成功",
  uploadSuccess: "上传成功",
  noMessages: "暂无消息",
  noArtifacts: "代码、预览、文件读取结果和 Diff 会显示在这里。",
  noUserMessage: "没有可重新生成的用户消息。",
  progress: "执行进度",
  model: "模型",
  agentMode: "模式",
  toolSwitches: "工具",
  collapse: "收起",
  expand: "展开",
};

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [tools, setTools] = useState<ToolOption[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("auto");
  const [agentMode, setAgentMode] = useState<"single" | "multi">("single");
  const [toolPreferences, setToolPreferences] = useState<ToolPreferences>(defaultToolPreferences);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  const [conversationSearch, setConversationSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftMode, setDraftMode] = useState<ConversationMode>("single");
  const [draftAgentIds, setDraftAgentIds] = useState<string[]>(["orchestrator"]);
  const [quotedMessage, setQuotedMessage] = useState<ChatMessage | null>(null);
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null);
  const [input, setInput] = useState("请你说一下这个图片给与一种什么感觉");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [progressSteps, setProgressSteps] = useState<ProgressStep[]>([]);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [rightTab, setRightTab] = useState<RightPanelTab>("artifacts");
  const [activeNav, setActiveNav] = useState("chat");

  const activeConversation = conversations.find((item) => item.id === activeConversationId);
  const selectedAgentIds = activeConversation?.agent_ids.length
    ? activeConversation.agent_ids
    : draftAgentIds;
  const attachmentMap = useMemo(
    () => new Map(attachments.map((attachment) => [attachment.id, attachment])),
    [attachments],
  );
  const pinnedMessages = messages.filter((message) => message.is_pinned);

  useEffect(() => {
    getAgents().then(setAgents).catch((err: Error) => setError(err.message));
    getModels()
      .then((items) => setModels(items.length ? items : [{ id: "auto", name: "Auto", provider: "auto" }]))
      .catch((err: Error) => setError(err.message));
    getTools().then(setTools).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timer = window.setTimeout(() => setToast(""), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    reloadConversations();
  }, [conversationSearch, showArchived]);

  useEffect(() => {
    if (!activeConversationId) {
      setMessages([]);
      setArtifacts([]);
      setAttachments([]);
      return;
    }
    reloadConversationDetail(activeConversationId);
  }, [activeConversationId]);

  async function reloadConversations(preferredId?: string) {
    const items = await getConversations({ search: conversationSearch, archived: showArchived });
    setConversations(items);
    setActiveConversationId((current) => {
      if (preferredId && items.some((item) => item.id === preferredId)) {
        return preferredId;
      }
      if (current && items.some((item) => item.id === current)) {
        return current;
      }
      return items[0]?.id ?? "";
    });
  }

  async function reloadConversationDetail(conversationId: string) {
    const [nextMessages, nextArtifacts, nextAttachments] = await Promise.all([
      getConversationMessages(conversationId),
      getConversationArtifacts(conversationId),
      getConversationAttachments(conversationId),
    ]);
    setMessages(nextMessages);
    setArtifacts(nextArtifacts);
    setAttachments(nextAttachments);
  }

  function openCreatePanel() {
    setDraftTitle("新会话");
    setDraftMode(agentMode === "multi" ? "group" : "single");
    setDraftAgentIds(agentMode === "multi" ? defaultAgentIds : ["orchestrator"]);
    setIsCreateOpen(true);
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
    const conversation = await createConversation({
      title: draftTitle.trim() || "新会话",
      mode: draftMode,
      agent_ids: draftMode === "single" ? [draftAgentIds[0] ?? "orchestrator"] : draftAgentIds,
    });
    setIsCreateOpen(false);
    setShowArchived(false);
    setConversationSearch("");
    await reloadConversations(conversation.id);
  }

  async function handleConversationPin(conversation: Conversation) {
    if (conversation.is_pinned) {
      await unpinConversation(conversation.id);
    } else {
      await pinConversation(conversation.id);
    }
    await reloadConversations(conversation.id);
  }

  async function handleArchive(conversation: Conversation) {
    if (conversation.is_archived) {
      await unarchiveConversation(conversation.id);
      setShowArchived(false);
    } else {
      await archiveConversation(conversation.id);
    }
    await reloadConversations();
  }

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    if (!activeConversation || !event.target.files?.length) {
      return;
    }
    setError("");
    try {
      const uploaded = await Promise.all(
        Array.from(event.target.files).map(async (file) => {
          const preparedFile = file.type.startsWith("image/")
            ? await compressImageFile(file)
            : file;
          const contentBase64 = await fileToBase64(preparedFile);
          return uploadAttachment(activeConversation.id, {
            filename: preparedFile.name,
            mime_type: preparedFile.type || undefined,
            content_base64: contentBase64,
          });
        }),
      );
      setAttachments((current) => [...current, ...uploaded]);
      setPendingAttachments((current) => [...current, ...uploaded]);
      setToast(labels.uploadSuccess);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      event.target.value = "";
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content || !activeConversation || isSending) {
      return;
    }

    const attachmentIds = pendingAttachments.map((attachment) => attachment.id);
    const optimisticMessage: ChatMessage = {
      id: `local_${Date.now()}`,
      conversation_id: activeConversation.id,
      role: "user",
      sender: "you",
      content,
      format: "markdown",
      quoted_message_id: quotedMessage?.id,
      attachment_ids: attachmentIds,
    };

    setMessages((current) => [...current, optimisticMessage]);
    setInput("");
    setIsSending(true);
    setError("");
    setProgressSteps(initialProgressSteps(selectedModelId, attachmentIds.length));
    try {
      const response = await sendChatMessage(
        content,
        activeConversation.id,
        selectedAgentIds,
        quotedMessage?.id,
        attachmentIds,
        selectedModelId,
        undefined,
        agentMode,
        toolPreferences,
      );
      applyChatResponse(response);
      setPendingAttachments([]);
      setQuotedMessage(null);
      await reloadConversations(activeConversation.id);
    } catch (err) {
      setProgressSteps((current) => markProgressError(current, err instanceof Error ? err.message : "Send failed"));
      setError(err instanceof Error ? err.message : "Send failed");
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
      setError(labels.noUserMessage);
      return;
    }
    setIsSending(true);
    setProgressSteps(initialProgressSteps(selectedModelId, lastUserMessage.attachment_ids?.length ?? 0));
    try {
      const response = await regenerateChatMessage(
        lastUserMessage.content,
        activeConversation.id,
        selectedAgentIds,
        selectedModelId,
        undefined,
        agentMode,
        toolPreferences,
      );
      applyChatResponse(response);
      await reloadConversations(activeConversation.id);
    } catch (err) {
      setProgressSteps((current) => markProgressError(current, err instanceof Error ? err.message : "Regenerate failed"));
      setError(err instanceof Error ? err.message : "Regenerate failed");
    } finally {
      setIsSending(false);
    }
  }

  function applyChatResponse(response: ChatResponse) {
    setMessages((current) => [...current, ...response.messages]);
    setArtifacts((current) => [...current, ...response.artifacts]);
    setProgressSteps(progressFromEvents(response.events ?? []));
  }

  async function handleMessagePin(message: ChatMessage) {
    if (!activeConversation) {
      return;
    }
    const updated = message.is_pinned
      ? await unpinMessage(activeConversation.id, message.id)
      : await pinMessage(activeConversation.id, message.id);
    setMessages((current) =>
      current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
    );
  }

  async function handleApplyDiff(artifact: Artifact) {
    try {
      await applyArtifactDiff(artifact.id);
      setArtifacts((current) =>
        current.map((item) => (item.id === artifact.id ? { ...item, status: "applied" } : item)),
      );
      setToast("Diff 已应用");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Apply diff failed");
    }
  }

  function toggleToolPreference(key: keyof ToolPreferences) {
    setToolPreferences((current) => ({ ...current, [key]: !current[key] }));
  }

  return (
    <main className={`app-shell ${rightPanelOpen ? "with-right-panel" : "right-panel-collapsed"}`}>
      <nav className="rail">
        <div className="rail-logo">AH</div>
        {[
          ["chat", "对话", "●"],
          ["agents", "Agents", "◎"],
          ["tools", "Tools", "◇"],
          ["artifacts", "产物", "▣"],
          ["settings", "设置", "⚙"],
        ].map(([id, label, icon]) => (
          <button
            className={activeNav === id ? "active" : ""}
            key={id}
            title={label}
            type="button"
            onClick={() => {
              setActiveNav(id);
              if (id === "agents" || id === "tools" || id === "artifacts") {
                setRightPanelOpen(true);
                setRightTab(id === "agents" ? "agents" : id === "tools" ? "tools" : "artifacts");
              }
            }}
          >
            {icon}
          </button>
        ))}
      </nav>

      <aside className="conversation-pane">
        <section className="brand">
          <div>
            <strong>AgentHub</strong>
            <span>{labels.appTagline}</span>
          </div>
          <button type="button" onClick={openCreatePanel}>{labels.new}</button>
        </section>

        <section className="status-row">
          <span className={`status-chip ${isSending ? "running" : ""}`}>
            {isSending ? labels.running : labels.ready}
          </span>
          <button className="archive-toggle small" type="button" onClick={() => setShowArchived((current) => !current)}>
            {showArchived ? labels.showActive : labels.showArchived}
          </button>
        </section>

        {isCreateOpen ? (
          <form className="create-panel" onSubmit={handleCreateConversation}>
            <input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} placeholder={labels.title} />
            <div className="mode-row">
              <button className={draftMode === "single" ? "selected" : ""} type="button" onClick={() => { setDraftMode("single"); setDraftAgentIds([draftAgentIds[0] ?? "orchestrator"]); }}>
                {labels.single}
              </button>
              <button className={draftMode === "group" ? "selected" : ""} type="button" onClick={() => { setDraftMode("group"); setDraftAgentIds(defaultAgentIds); }}>
                {labels.multi}
              </button>
            </div>
            <div className="agent-picker">
              {agents.map((agent) => (
                <label key={agent.id}>
                  <input checked={draftAgentIds.includes(agent.id)} onChange={() => toggleDraftAgent(agent.id)} type={draftMode === "single" ? "radio" : "checkbox"} />
                  <span>{agent.name}</span>
                </label>
              ))}
            </div>
            <div className="create-actions">
              <button type="button" onClick={() => setIsCreateOpen(false)}>{labels.cancel}</button>
              <button type="submit">{labels.create}</button>
            </div>
          </form>
        ) : null}

        <input className="search-input" value={conversationSearch} onChange={(event) => setConversationSearch(event.target.value)} placeholder={labels.search} />

        <section className="conversation-list">
          {conversations.map((conversation) => (
            <article className={`conversation-card ${conversation.id === activeConversationId ? "active" : ""}`} key={conversation.id} onClick={() => setActiveConversationId(conversation.id)}>
              <div className="conversation-avatar">{conversation.agent_ids[0]?.slice(0, 2).toUpperCase() ?? "AH"}</div>
              <div className="conversation-content">
                <div className="conversation-title-row">
                  <strong>{conversation.title}</strong>
                  <span>{formatRelativeTime(conversation.updated_at)}</span>
                </div>
                <small>{conversation.mode} · {conversation.agent_ids.join(", ")}</small>
                <p>{conversation.last_message || labels.noMessages}</p>
                <div className="conversation-actions">
                  <button type="button" onClick={(event) => { event.stopPropagation(); handleConversationPin(conversation); }}>
                    {conversation.is_pinned ? labels.unpin : labels.pin}
                  </button>
                  <button type="button" onClick={(event) => { event.stopPropagation(); handleArchive(conversation); }}>
                    {conversation.is_archived ? labels.restore : labels.archive}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </section>
      </aside>

      <section className="chat-panel">
        <header className="chat-header">
          <div>
            <span>上下文</span>
            <h1>{activeConversation?.title ?? labels.emptyTitle}</h1>
          </div>
          <div className="header-pills">
            <span>{agentMode === "multi" ? labels.multi : labels.single}</span>
            <span>{selectedAgentIds.length} Agents</span>
            <button type="button" onClick={() => setRightPanelOpen((current) => !current)}>
              {rightPanelOpen ? labels.collapse : labels.expand}
            </button>
          </div>
        </header>

        <section className="chat-stream">
          {messages.length === 0 ? (
            <div className="empty-state">{labels.emptyTitle}</div>
          ) : (
            messages.map((message) => (
              <MessageCard
                attachmentMap={attachmentMap}
                key={message.id}
                labels={labels}
                message={message}
                onPin={() => handleMessagePin(message)}
                onQuote={() => setQuotedMessage(message)}
                onToast={setToast}
              />
            ))
          )}
          {progressSteps.length ? <ProgressPanel steps={progressSteps} /> : null}
        </section>

        <form className="composer" onSubmit={handleSubmit}>
          {quotedMessage ? (
            <div className="quote-banner">
              <span>{labels.quoted}: {quotedMessage.content.slice(0, 120)}</span>
              <button type="button" onClick={() => setQuotedMessage(null)}>{labels.clear}</button>
            </div>
          ) : null}
          {pendingAttachments.length ? (
            <div className="pending-files">
              <span>{labels.pendingFiles}</span>
              {pendingAttachments.map((attachment) => (
                <button key={attachment.id} type="button" onClick={() => setPendingAttachments((current) => current.filter((item) => item.id !== attachment.id))}>
                  {attachment.filename} x
                </button>
              ))}
            </div>
          ) : null}
          <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder={labels.placeholder} />
          <div className="composer-footer">
            <div className="composer-left">
              <label className="upload-button">
                + {labels.upload}
                <input multiple type="file" onChange={handleFiles} />
              </label>
              <div className="tool-toggles" aria-label={labels.toolSwitches}>
                {(Object.keys(toolPreferences) as Array<keyof ToolPreferences>).map((key) => (
                  <button
                    className={toolPreferences[key] ? "active" : ""}
                    key={key}
                    type="button"
                    onClick={() => toggleToolPreference(key)}
                  >
                    {toolLabel(key)}
                  </button>
                ))}
              </div>
            </div>
            {error ? <span className="error-text">{error}</span> : <span />}
            <div className="composer-actions">
              <select className="model-select" value={selectedModelId} onChange={(event) => setSelectedModelId(event.target.value)}>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>{model.name}</option>
                ))}
              </select>
              <select className="model-select" value={agentMode} onChange={(event) => setAgentMode(event.target.value as "single" | "multi")}>
                <option value="single">{labels.single}</option>
                <option value="multi">{labels.multi}</option>
              </select>
              <button type="button" onClick={handleRegenerate} disabled={!activeConversation || isSending}>{labels.regenerate}</button>
              <button className="send-button" disabled={!activeConversation || isSending || !input.trim()} type="submit">
                {isSending ? labels.sending : labels.send}
              </button>
            </div>
          </div>
        </form>
      </section>

      <aside className={`right-panel ${rightPanelOpen ? "open" : ""}`}>
        <div className="right-tabs">
          {(["artifacts", "agents", "tools", "context"] as RightPanelTab[]).map((tab) => (
            <button className={rightTab === tab ? "active" : ""} key={tab} type="button" onClick={() => setRightTab(tab)}>
              {rightTabLabel(tab)}
            </button>
          ))}
        </div>
        <RightPanelContent
          activeConversation={activeConversation}
          agents={agents}
          artifacts={artifacts}
          attachments={attachments}
          labels={labels}
          onApply={handleApplyDiff}
          onPreview={setPreviewArtifact}
          onToast={setToast}
          pinnedMessages={pinnedMessages}
          selectedAgentIds={selectedAgentIds}
          tab={rightTab}
          tools={tools}
        />
      </aside>

      {previewArtifact ? (
        <div className="preview-modal" role="dialog" aria-modal="true">
          <div className="preview-card">
            <header>
              <h2>{previewArtifact.title}</h2>
              <button type="button" onClick={() => setPreviewArtifact(null)}>{labels.close}</button>
            </header>
            <iframe title={previewArtifact.title} src={`${API_ORIGIN}${previewArtifact.preview_url}`} />
          </div>
        </div>
      ) : null}
      {toast ? <div className="toast">{toast}</div> : null}
    </main>
  );
}

function MessageCard({
  attachmentMap,
  labels: t,
  message,
  onPin,
  onQuote,
  onToast,
}: {
  attachmentMap: Map<string, Attachment>;
  labels: typeof labels;
  message: ChatMessage;
  onPin: () => void;
  onQuote: () => void;
  onToast: (message: string) => void;
}) {
  const messageAttachments = (message.attachment_ids ?? [])
    .map((id) => attachmentMap.get(id))
    .filter(Boolean) as Attachment[];
  const sender = message.role === "user" ? "你" : message.sender ?? "agent";

  return (
    <article className={`message-card ${message.role}`}>
      <div className="avatar">{sender.slice(0, 2).toUpperCase()}</div>
      <div className="message-bubble">
        <header>
          <strong>{sender}</strong>
          <div className="message-actions">
            <button type="button" onClick={onQuote}>{t.quote}</button>
            <button type="button" onClick={onPin}>{message.is_pinned ? t.unpinMessage : t.pinMessage}</button>
          </div>
        </header>
        {message.quoted_message_id ? <small className="quoted-line">{t.quoted}: {message.quoted_message_id}</small> : null}
        <MarkdownMessage content={message.content} copyLabel={t.copy} copiedLabel={t.copied} onToast={onToast} />
        {messageAttachments.length ? <AttachmentList attachments={messageAttachments} /> : null}
      </div>
    </article>
  );
}

function AttachmentList({ attachments }: { attachments: Attachment[] }) {
  return (
    <div className="attachment-list">
      {attachments.map((attachment) =>
        attachment.type === "image" ? (
          <a href={`${API_ORIGIN}${attachment.url}`} key={attachment.id} target="_blank" rel="noreferrer">
            <img alt={attachment.filename} src={`${API_ORIGIN}${attachment.url}`} />
          </a>
        ) : (
          <a className="file-chip" href={`${API_ORIGIN}${attachment.url}`} key={attachment.id} target="_blank" rel="noreferrer">
            {attachment.filename}
          </a>
        ),
      )}
    </div>
  );
}

function ProgressPanel({ steps }: { steps: ProgressStep[] }) {
  const doneCount = steps.filter((step) => step.status === "done").length;
  const percent = steps.length ? Math.round((doneCount / steps.length) * 100) : 0;

  return (
    <section className="progress-panel">
      <header>
        <strong>{labels.progress}</strong>
        <span>{percent}%</span>
      </header>
      <div className="progress-track">
        <div style={{ width: `${percent}%` }} />
      </div>
      <ol>
        {steps.map((step) => (
          <li className={step.status} key={step.id}>
            <span />
            <div>
              <strong>{step.label}</strong>
              {step.detail ? <small>{step.detail}</small> : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RightPanelContent({
  activeConversation,
  agents,
  artifacts,
  attachments,
  labels: t,
  onApply,
  onPreview,
  onToast,
  pinnedMessages,
  selectedAgentIds,
  tab,
  tools,
}: {
  activeConversation?: Conversation;
  agents: Agent[];
  artifacts: Artifact[];
  attachments: Attachment[];
  labels: typeof labels;
  onApply: (artifact: Artifact) => void;
  onPreview: (artifact: Artifact) => void;
  onToast: (message: string) => void;
  pinnedMessages: ChatMessage[];
  selectedAgentIds: string[];
  tab: RightPanelTab;
  tools: ToolOption[];
}) {
  if (tab === "agents") {
    const selected = agents.filter((agent) => selectedAgentIds.includes(agent.id));
    return (
      <div className="right-content">
        {selected.map((agent) => (
          <section className="side-card" key={agent.id}>
            <strong>{agent.name}</strong>
            <p>{agent.description}</p>
            <TagRow items={agent.capabilities ?? []} />
            <small>Model: {agent.model_provider ?? "conversation model"}</small>
            <small>Skills: {(agent.skills ?? []).join(", ") || "none"}</small>
            <small>Tools: {(agent.tools ?? []).join(", ") || "none"}</small>
          </section>
        ))}
      </div>
    );
  }

  if (tab === "tools") {
    return (
      <div className="right-content">
        {tools.map((tool) => (
          <section className="side-card" key={tool.id}>
            <strong>{tool.name ?? tool.id}</strong>
            <p>{tool.description ?? tool.id}</p>
            <small>{tool.id}</small>
          </section>
        ))}
      </div>
    );
  }

  if (tab === "context") {
    return (
      <div className="right-content">
        <section className="side-card">
          <strong>{activeConversation?.title ?? t.emptyTitle}</strong>
          <p>{activeConversation?.last_message || t.noMessages}</p>
        </section>
        <section className="side-card">
          <strong>Pinned Messages</strong>
          {pinnedMessages.length ? pinnedMessages.map((message) => <p key={message.id}>{message.content}</p>) : <p>暂无长期记忆</p>}
        </section>
        <section className="side-card">
          <strong>Attachments</strong>
          {attachments.length ? attachments.map((attachment) => <p key={attachment.id}>{attachment.filename}</p>) : <p>暂无附件</p>}
        </section>
      </div>
    );
  }

  return (
    <div className="right-content">
      {artifacts.length === 0 ? (
        <section className="side-card"><p>{t.noArtifacts}</p></section>
      ) : (
        artifacts.map((artifact) => (
          <ArtifactCard artifact={artifact} key={artifact.id} labels={t} onApply={() => onApply(artifact)} onPreview={() => onPreview(artifact)} onToast={onToast} />
        ))
      )}
    </div>
  );
}

function ArtifactCard({
  artifact,
  labels: t,
  onApply,
  onPreview,
  onToast,
}: {
  artifact: Artifact;
  labels: typeof labels;
  onApply: () => void;
  onPreview: () => void;
  onToast: (message: string) => void;
}) {
  async function handleCopy() {
    await navigator.clipboard.writeText(artifact.content ?? artifact.preview_url ?? "");
    onToast(t.copied);
  }

  return (
    <article className={`artifact-card ${artifact.type}`}>
      <header>
        <span>{artifact.type}</span>
        <strong>{artifact.title}</strong>
      </header>
      {artifact.content ? <pre>{artifact.content}</pre> : null}
      <footer>
        {artifact.content ? <button type="button" onClick={handleCopy}>{t.copy}</button> : null}
        {artifact.preview_url ? <button type="button" onClick={onPreview}>{t.preview}</button> : null}
        {artifact.type === "diff" ? (
          <button disabled={artifact.status === "applied"} type="button" onClick={onApply}>
            {artifact.status === "applied" ? t.applied : t.applyDiff}
          </button>
        ) : null}
      </footer>
    </article>
  );
}

function MarkdownMessage({
  content,
  copyLabel,
  copiedLabel,
  onToast,
}: {
  content: string;
  copyLabel: string;
  copiedLabel: string;
  onToast: (message: string) => void;
}) {
  const blocks = parseMarkdownBlocks(content);
  return (
    <div className="message-body">
      {blocks.map((block, index) =>
        block.type === "code" ? (
          <CodeBlock block={block} copiedLabel={copiedLabel} copyLabel={copyLabel} key={`${block.type}-${index}`} onToast={onToast} />
        ) : (
          renderTextBlock(block.content, index)
        ),
      )}
    </div>
  );
}

type MarkdownBlock =
  | { type: "text"; content: string }
  | { type: "code"; content: string; language: string };

function parseMarkdownBlocks(content: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const fencePattern = /```([A-Za-z0-9_-]*)\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = fencePattern.exec(content)) !== null) {
    if (match.index > cursor) {
      blocks.push({ type: "text", content: content.slice(cursor, match.index) });
    }
    blocks.push({ type: "code", language: match[1] || "text", content: match[2].replace(/\n$/, "") });
    cursor = match.index + match[0].length;
  }
  if (cursor < content.length) {
    blocks.push({ type: "text", content: content.slice(cursor) });
  }
  return blocks.length ? blocks : [{ type: "text", content }];
}

function renderTextBlock(content: string, key: number): ReactNode {
  const paragraphs = content.split(/\n{2,}/).map((paragraph) => paragraph.trim()).filter(Boolean);
  return paragraphs.map((paragraph, index) => (
    <p key={`text-${key}-${index}`}>
      {paragraph.split("\n").map((line, lineIndex, lines) => (
        <span key={`${line}-${lineIndex}`}>{line}{lineIndex < lines.length - 1 ? <br /> : null}</span>
      ))}
    </p>
  ));
}

function CodeBlock({
  block,
  copyLabel,
  copiedLabel,
  onToast,
}: {
  block: Extract<MarkdownBlock, { type: "code" }>;
  copyLabel: string;
  copiedLabel: string;
  onToast: (message: string) => void;
}) {
  async function handleCopy() {
    await navigator.clipboard.writeText(block.content);
    onToast(copiedLabel);
  }
  return (
    <div className="code-block">
      <header>
        <span>{block.language}</span>
        <button type="button" onClick={handleCopy}>{copyLabel}</button>
      </header>
      <pre><code>{block.content}</code></pre>
    </div>
  );
}

function TagRow({ items }: { items: string[] }) {
  return (
    <div className="tag-row">
      {items.map((item) => <span key={item}>{item}</span>)}
    </div>
  );
}

function initialProgressSteps(modelId: string, attachmentCount: number): ProgressStep[] {
  return [
    { id: "attachments", label: "准备附件", detail: `${attachmentCount} 个附件`, status: attachmentCount ? "active" : "done" },
    { id: "model", label: "选择模型", detail: modelId, status: "pending" },
    { id: "plan", label: "规划任务", status: "pending" },
    { id: "agent", label: "调用 Agent", status: "pending" },
    { id: "complete", label: "汇总结果", status: "pending" },
  ];
}

function progressFromEvents(events: ChatResponse["events"]): ProgressStep[] {
  const steps: ProgressStep[] = [];
  for (const event of events ?? []) {
    if (event.type === "model.selected") {
      steps.push({
        id: "model",
        label: "选择模型",
        detail: String(event.payload.provider ?? "auto"),
        status: "done",
      });
    }
    if (event.type === "attachments.prepared") {
      steps.push({
        id: "attachments",
        label: "准备附件",
        detail: `${event.payload.count ?? 0} 个附件，${event.payload.image_count ?? 0} 张图片`,
        status: "done",
      });
    }
    if (event.type === "run.planned") {
      steps.push({
        id: "plan",
        label: "规划任务",
        detail: String(event.payload.reason ?? ""),
        status: "done",
      });
    }
    if (event.type === "agent.started" || event.type === "agent.parallel_started") {
      steps.push({
        id: `${event.type}-${steps.length}`,
        label: "调用 Agent",
        detail: String(event.payload.agent_id ?? ""),
        status: "done",
      });
    }
    if (event.type === "agent.completed") {
      steps.push({
        id: `${event.type}-${steps.length}`,
        label: "Agent 完成",
        detail: `${event.payload.agent_id ?? ""} · ${event.payload.status ?? ""}`,
        status: event.payload.status === "failed" ? "error" : "done",
      });
    }
    if (event.type === "run.completed") {
      steps.push({
        id: "complete",
        label: "汇总结果",
        detail: String(event.payload.status ?? ""),
        status: "done",
      });
    }
  }
  return dedupeProgress(steps);
}

function dedupeProgress(steps: ProgressStep[]): ProgressStep[] {
  if (!steps.length) {
    return [];
  }
  return steps;
}

function markProgressError(steps: ProgressStep[], detail: string): ProgressStep[] {
  if (!steps.length) {
    return [{ id: "error", label: "执行失败", detail, status: "error" }];
  }
  return steps.map((step, index) =>
    index === steps.length - 1 ? { ...step, status: "error", detail } : step,
  );
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("File read failed"));
    reader.readAsDataURL(file);
  });
}

async function compressImageFile(file: File): Promise<File> {
  const image = await loadImage(file);
  const maxSide = 1280;
  const scale = Math.min(1, maxSide / Math.max(image.width, image.height));
  const width = Math.max(1, Math.round(image.width * scale));
  const height = Math.max(1, Math.round(image.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    return file;
  }
  context.drawImage(image, 0, 0, width, height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
  URL.revokeObjectURL(image.src);
  if (!blob || blob.size >= file.size) {
    return file;
  }
  return new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), { type: "image/jpeg" });
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Image load failed"));
    image.src = URL.createObjectURL(file);
  });
}

function formatRelativeTime(value: string): string {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return "";
  }
  const diff = Date.now() - timestamp;
  const minutes = Math.max(0, Math.round(diff / 60000));
  if (minutes < 1) {
    return "刚刚";
  }
  if (minutes < 60) {
    return `${minutes}分钟前`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours}小时前`;
  }
  return `${Math.round(hours / 24)}天前`;
}

function toolLabel(key: keyof ToolPreferences): string {
  return {
    file: "文件",
    image: "图片",
    preview: "预览",
    diff: "Diff",
  }[key];
}

function rightTabLabel(tab: RightPanelTab): string {
  return {
    artifacts: labels.artifacts,
    agents: labels.agents,
    tools: labels.tools,
    context: labels.context,
  }[tab];
}

export default App;
