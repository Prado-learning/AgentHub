import { ChangeEvent, CSSProperties, Dispatch, FormEvent, MouseEvent as ReactMouseEvent, ReactNode, SetStateAction, useEffect, useMemo, useRef, useState } from "react";

import {
  applyArtifactDiff,
  archiveConversation,
  createAgent,
  createConversation,
  deleteConversation,
  getArtifactDiff,
  getArtifactVersions,
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
  restoreConversation,
  restoreArtifactVersion,
  sendChatMessage,
  trashConversation,
  unarchiveConversation,
  unpinConversation,
  unpinMessage,
  updateArtifact,
  updateConversation,
  uploadAttachment,
} from "./api";
import type {
  Agent,
  AgentCreateInput,
  Artifact,
  ArtifactVersion,
  Attachment,
  ChatMessage,
  ChatResponse,
  Conversation,
  ConversationMode,
  ModelOption,
  StructuredDiff,
  TraceEvent,
  ToolOption,
  ToolPreferences,
} from "./types";

const API_ORIGIN = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const TRASH_STORAGE_KEY = "agenthub:trashed-conversations";
const defaultAgentIds = ["orchestrator", "codex", "ui_builder", "code_reviewer"];
const defaultToolPreferences: ToolPreferences = {
  file: true,
  image: true,
  preview: true,
  diff: true,
};

type RightPanelTab = "artifacts" | "agents" | "tools" | "context";
type ProgressStep = {
  id: string;
  label: string;
  detail?: string;
  status: "pending" | "active" | "done" | "error";
};

const labels = {
  appTagline: "多智能体（Agent）协作工作台",
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
  rename: "重命名",
  delete: "删除",
  permanentDelete: "永久删除",
  confirmDeleteTitle: "永久删除对话？",
  confirmDeleteBody: "删除后无法恢复。",
  yes: "是",
  trash: "回收站",
  trashEmpty: "回收站为空",
  noConversations: "暂无会话",
  title: "标题",
  single: "单智能体（Agent）",
  multi: "多智能体（Agent）",
  chooseAgent: "选择智能体（Agent）",
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
  thinking: "思考摘要",
  pinMessage: "Pin",
  unpinMessage: "Unpin",
  upload: "上传",
  pendingFiles: "待发送附件",
  artifacts: "产物",
  agents: "智能体（Agents）",
  tools: "Tools",
  context: "Context",
  copy: "复制",
  preview: "预览",
  close: "关闭",
  applyDiff: "应用 Diff",
  viewDiff: "查看 Diff",
  edit: "编辑",
  save: "保存",
  versions: "版本",
  createAgent: "创建智能体（Agent）",
  systemPrompt: "System Prompt",
  selectedQuote: "引用选中",
  deployOpen: "打开部署",
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
  const [quotedText, setQuotedText] = useState("");
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null);
  const [editArtifact, setEditArtifact] = useState<Artifact | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [agentDraft, setAgentDraft] = useState<AgentCreateInput>({
    name: "",
    description: "",
    system_prompt: "",
    capabilities: ["text"],
    tools: [],
  });
  const [input, setInput] = useState("请你说一下这个图片给与一种什么感觉");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [progressSteps, setProgressSteps] = useState<ProgressStep[]>([]);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [rightTab, setRightTab] = useState<RightPanelTab>("artifacts");
  const [conversationWidth, setConversationWidth] = useState(280);
  const [rightPanelWidth, setRightPanelWidth] = useState(410);
  const [trashedConversations, setTrashedConversations] = useState<Conversation[]>(readLegacyTrashedConversations);
  const [isTrashOpen, setIsTrashOpen] = useState(false);
  const [deleteTargetConversation, setDeleteTargetConversation] = useState<Conversation | null>(null);
  const [openConversationMenuId, setOpenConversationMenuId] = useState("");
  const [renamingConversationId, setRenamingConversationId] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [mentionStart, setMentionStart] = useState<number | null>(null);
  const [mentionQuery, setMentionQuery] = useState("");
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const hasMigratedLegacyTrashRef = useRef(false);

  const activeConversation = conversations.find((item) => item.id === activeConversationId);
  const selectedAgentIds = activeConversation?.agent_ids.length
    ? activeConversation.agent_ids
    : draftAgentIds;
  const trashedConversationIds = useMemo(
    () => new Set(trashedConversations.map((conversation) => conversation.id)),
    [trashedConversations],
  );
  const visibleConversations = useMemo(
    () => conversations.filter((conversation) => !trashedConversationIds.has(conversation.id)),
    [conversations, trashedConversationIds],
  );
  const attachmentMap = useMemo(
    () => new Map(attachments.map((attachment) => [attachment.id, attachment])),
    [attachments],
  );
  const mentionAgents = useMemo(() => {
    if (activeConversation?.mode !== "group") {
      return [];
    }
    const selectedIds = new Set(selectedAgentIds);
    const selectedAgents = agents.filter((agent) => selectedIds.has(agent.id));
    return selectedAgents.length ? selectedAgents : agents;
  }, [activeConversation?.mode, agents, selectedAgentIds]);
  const mentionCandidates = useMemo(() => {
    if (mentionStart === null) {
      return [];
    }
    const query = mentionQuery.toLowerCase();
    return mentionAgents
      .filter((agent) => {
        const label = `${agent.id} ${agent.name} ${agent.description}`.toLowerCase();
        return !query || label.includes(query);
      })
      .slice(0, 8);
  }, [mentionAgents, mentionQuery, mentionStart]);
  const pinnedMessages = messages.filter((message) => message.is_pinned);
  const shellStyle = {
    "--conversation-width": `${conversationWidth}px`,
    "--right-panel-width": rightPanelOpen ? `${rightPanelWidth}px` : "0px",
  } as CSSProperties;

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
    resizeComposerInput();
  }, [input]);

  useEffect(() => {
    migrateLegacyTrashToServer();
  }, []);

  useEffect(() => {
    reloadConversations();
  }, [conversationSearch, showArchived]);

  useEffect(() => {
    if (!activeConversation) {
      return;
    }
    setAgentMode(activeConversation.mode === "single" ? "single" : "multi");
  }, [activeConversation?.id, activeConversation?.mode]);

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
    const [items, trashedItems] = await Promise.all([
      getConversations({ search: conversationSearch, archived: showArchived }),
      getConversations({ trashed: true }),
    ]);
    setConversations(items);
    setTrashedConversations(trashedItems);
    const nextTrashedIds = new Set(trashedItems.map((conversation) => conversation.id));
    const visibleItems = items.filter((item) => !nextTrashedIds.has(item.id));
    setActiveConversationId((current) => {
      if (preferredId && visibleItems.some((item) => item.id === preferredId)) {
        return preferredId;
      }
      if (current && visibleItems.some((item) => item.id === current)) {
        return current;
      }
      return visibleItems[0]?.id ?? "";
    });
  }

  async function migrateLegacyTrashToServer() {
    if (hasMigratedLegacyTrashRef.current) {
      return;
    }
    hasMigratedLegacyTrashRef.current = true;
    const legacyTrash = readLegacyTrashedConversations();
    if (!legacyTrash.length) {
      return;
    }
    const migrated = await Promise.all(
      legacyTrash.map(async (conversation) => {
        try {
          await trashConversation(conversation.id);
          return true;
        } catch {
          return false;
        }
      }),
    );
    if (!migrated.some(Boolean)) {
      return;
    }
    clearLegacyTrashedConversations();
    await reloadConversations();
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

  function beginRenameConversation(conversation: Conversation) {
    setRenamingConversationId(conversation.id);
    setRenameDraft(conversation.title);
    setOpenConversationMenuId("");
  }

  async function handleRenameConversation(event: FormEvent<HTMLFormElement>, conversation: Conversation) {
    event.preventDefault();
    event.stopPropagation();
    const nextTitle = renameDraft.trim();
    if (!nextTitle) {
      return;
    }
    if (nextTitle === conversation.title) {
      setRenamingConversationId("");
      return;
    }
    try {
      const updated = await updateConversation(conversation.id, { title: nextTitle });
      setConversations((current) =>
        current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
      );
      setRenamingConversationId("");
      setRenameDraft("");
      setOpenConversationMenuId("");
      setToast("会话已重命名");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    }
  }

  async function handleDeleteConversation(conversation: Conversation) {
    try {
      await trashConversation(conversation.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Move to trash failed");
      return;
    }
    if (activeConversationId === conversation.id) {
      const fallback = visibleConversations.find((item) => item.id !== conversation.id);
      setActiveConversationId(fallback?.id ?? "");
      setQuotedMessage(null);
      setQuotedText("");
      setPendingAttachments([]);
    }
    await reloadConversations();
    setToast(`已移动到${labels.trash}`);
  }

  async function handleRestoreConversation(conversationId: string) {
    const restoredConversation = trashedConversations.find((item) => item.id === conversationId);
    const shouldSelectRestored = Boolean(
      restoredConversation && (!restoredConversation.is_archived || showArchived),
    );
    try {
      await restoreConversation(conversationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restore failed");
      return;
    }
    await reloadConversations(shouldSelectRestored ? restoredConversation?.id : undefined);
    if (!activeConversationId && restoredConversation && shouldSelectRestored) {
      setActiveConversationId(restoredConversation.id);
    }
    setToast("已恢复到会话列表");
  }

  async function handlePermanentDeleteConversation() {
    if (!deleteTargetConversation) {
      return;
    }
    const targetConversation = deleteTargetConversation;
    setError("");
    try {
      await deleteConversation(targetConversation.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      return;
    }
    setTrashedConversations((current) =>
      current.filter((conversation) => conversation.id !== targetConversation.id),
    );
    setDeleteTargetConversation(null);
    if (activeConversationId === targetConversation.id) {
      setActiveConversationId("");
      setMessages([]);
      setArtifacts([]);
      setAttachments([]);
    }
    await reloadConversations();
    setToast("已永久删除");
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
      quoted_text: quotedText || quotedMessage?.content,
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
        quotedText || quotedMessage?.content,
        attachmentIds,
        selectedModelId,
        undefined,
        agentMode,
        toolPreferences,
      );
      applyChatResponse(response);
      setPendingAttachments([]);
      setQuotedMessage(null);
      setQuotedText("");
      await reloadConversations(activeConversation.id);
    } catch (err) {
      setProgressSteps((current) => markProgressError(current, err instanceof Error ? err.message : "Send failed"));
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setIsSending(false);
    }
  }

  async function handleRegenerate(sourceMessage?: ChatMessage) {
    if (!activeConversation || isSending) {
      return;
    }
    const lastUserMessage = sourceMessage ?? [...messages].reverse().find((message) => message.role === "user");
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
        lastUserMessage.id,
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
    const traceEvents = response.events ?? [];
    const responseMessages = response.messages.map((message) =>
      message.role === "agent" && !(message.trace_events?.length)
        ? { ...message, trace_events: traceEvents }
        : message,
    );
    setMessages((current) => [...current, ...responseMessages]);
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

  async function handleCreateAgent(event: FormEvent) {
    event.preventDefault();
    if (!agentDraft.name?.trim()) {
      setError("智能体（Agent）名称不能为空");
      return;
    }
    const agent = await createAgent(agentDraft);
    setAgents((current) => [...current, agent]);
    setAgentDraft({
      name: "",
      description: "",
      system_prompt: "",
      capabilities: ["text"],
      tools: [],
    });
    setToast("智能体（Agent）已创建");
  }

  function openCodeEditor(artifact: Artifact) {
    setEditArtifact(artifact);
    setEditDraft(artifact.content ?? "");
  }

  function openArtifactPreview(artifact: Artifact) {
    setPreviewArtifact(artifact);
    setRightPanelOpen(true);
    setRightTab("artifacts");
  }

  async function handleSaveArtifact() {
    if (!editArtifact) {
      return;
    }
    const updated = await updateArtifact(editArtifact.id, {
      content: editDraft,
      language: editArtifact.language,
      title: editArtifact.title,
    });
    setArtifacts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setEditArtifact(updated);
    setToast("代码已保存，版本已记录");
  }

  async function handleRestoreArtifactVersion(artifact: Artifact, versionId: string) {
    const updated = await restoreArtifactVersion(artifact.id, versionId);
    setArtifacts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setToast("版本已恢复");
  }

  function startPaneResize(pane: "conversation" | "right", event: ReactMouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startConversationWidth = conversationWidth;
    const startRightPanelWidth = rightPanelWidth;
    document.body.classList.add("is-resizing");

    function handleMove(moveEvent: MouseEvent) {
      const delta = moveEvent.clientX - startX;
      if (pane === "conversation") {
        setConversationWidth(clamp(startConversationWidth + delta, 280, 480));
      } else {
        setRightPanelWidth(clamp(startRightPanelWidth - delta, 320, 620));
      }
    }

    function handleUp() {
      document.body.classList.remove("is-resizing");
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    }

    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  }

  function resizeComposerInput(target: HTMLTextAreaElement | null = composerTextareaRef.current) {
    if (!target) {
      return;
    }
    target.style.height = "auto";
    target.style.height = `${clamp(target.scrollHeight, 76, 220)}px`;
  }

  function updateMentionState(value: string, cursor: number) {
    if (activeConversation?.mode !== "group") {
      setMentionStart(null);
      setMentionQuery("");
      return;
    }
    const beforeCursor = value.slice(0, cursor);
    const atIndex = beforeCursor.lastIndexOf("@");
    if (atIndex < 0 || (atIndex > 0 && !/\s/.test(beforeCursor[atIndex - 1]))) {
      setMentionStart(null);
      setMentionQuery("");
      return;
    }
    const query = beforeCursor.slice(atIndex + 1);
    if (/\s/.test(query) || /[^A-Za-z0-9_]/.test(query)) {
      setMentionStart(null);
      setMentionQuery("");
      return;
    }
    setMentionStart(atIndex);
    setMentionQuery(query);
  }

  function insertAgentMention(agent: Agent) {
    if (mentionStart === null) {
      return;
    }
    const textarea = composerTextareaRef.current;
    const cursor = textarea?.selectionStart ?? input.length;
    const mention = `@${agent.id} `;
    const nextInput = `${input.slice(0, mentionStart)}${mention}${input.slice(cursor)}`;
    const nextCursor = mentionStart + mention.length;
    setInput(nextInput);
    setMentionStart(null);
    setMentionQuery("");
    window.requestAnimationFrame(() => {
      composerTextareaRef.current?.focus();
      composerTextareaRef.current?.setSelectionRange(nextCursor, nextCursor);
      resizeComposerInput();
    });
  }

  return (
    <main className={`app-shell ${rightPanelOpen ? "with-right-panel" : "right-panel-collapsed"}`} style={shellStyle}>
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
                <label className="agent-choice" key={agent.id}>
                  <input checked={draftAgentIds.includes(agent.id)} onChange={() => toggleDraftAgent(agent.id)} type={draftMode === "single" ? "radio" : "checkbox"} />
                  <AvatarBadge value={agent.id} className="agent-picker-avatar" />
                  <span>{agentNameForDisplay(agent)}</span>
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
          {visibleConversations.length ? (
            visibleConversations.map((conversation) => (
              <article
                className={`conversation-card ${conversation.id === activeConversationId ? "active" : ""}`}
                key={conversation.id}
                onClick={() => {
                  setActiveConversationId(conversation.id);
                  setOpenConversationMenuId("");
                }}
              >
                <div className="conversation-content">
                  {renamingConversationId === conversation.id ? (
                    <form
                      className="conversation-rename-form"
                      onClick={(event) => event.stopPropagation()}
                      onSubmit={(event) => handleRenameConversation(event, conversation)}
                    >
                      <input
                        autoFocus
                        value={renameDraft}
                        onChange={(event) => setRenameDraft(event.target.value)}
                      />
                      <button type="submit">{labels.save}</button>
                      <button
                        type="button"
                        onClick={() => {
                          setRenamingConversationId("");
                          setRenameDraft("");
                        }}
                      >
                        {labels.cancel}
                      </button>
                    </form>
                  ) : (
                    <div className="conversation-title-row">
                      <strong>{conversation.title}</strong>
                      {conversation.is_pinned ? <span>{labels.pin}</span> : null}
                    </div>
                  )}
                </div>
                {renamingConversationId !== conversation.id ? (
                  <div className={`conversation-actions ${openConversationMenuId === conversation.id ? "menu-open" : ""}`}>
                    <button
                      className="conversation-menu-button"
                      type="button"
                      aria-label="会话操作"
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpenConversationMenuId((current) => current === conversation.id ? "" : conversation.id);
                      }}
                    >
                      <span />
                      <span />
                      <span />
                    </button>
                    {openConversationMenuId === conversation.id ? (
                      <div className="conversation-menu" onClick={(event) => event.stopPropagation()}>
                        <button type="button" onClick={() => beginRenameConversation(conversation)}>
                          {labels.rename}
                        </button>
                        <button type="button" onClick={() => { setOpenConversationMenuId(""); handleConversationPin(conversation); }}>
                          {conversation.is_pinned ? labels.unpin : labels.pin}
                        </button>
                        <button type="button" onClick={() => { setOpenConversationMenuId(""); handleArchive(conversation); }}>
                          {conversation.is_archived ? labels.restore : labels.archive}
                        </button>
                        <button className="danger" type="button" onClick={() => { setOpenConversationMenuId(""); handleDeleteConversation(conversation); }}>
                          {labels.delete}
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <div className="conversation-empty">{labels.noConversations}</div>
          )}
        </section>

        <section className="conversation-footer">
          <button className="trash-button" type="button" onClick={() => setIsTrashOpen((current) => !current)}>
            {labels.trash}
            <strong>{trashedConversations.length}</strong>
          </button>
        </section>
      </aside>
      <button
        aria-label="调整会话列表宽度"
        className="pane-resizer conversation-resizer"
        type="button"
        onMouseDown={(event) => startPaneResize("conversation", event)}
      />

      <section className="chat-panel">
        <header className="chat-header">
          <div>
            <h1>{activeConversation?.title ?? labels.emptyTitle}</h1>
          </div>
          <div className="header-pills">
            <span>{agentMode === "multi" ? labels.multi : labels.single}</span>
            <span>{selectedAgentIds.length} 智能体（Agents）</span>
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
                onQuote={() => {
                  setQuotedMessage(message);
                  setQuotedText("");
                }}
                onQuoteSelected={(text) => {
                  setQuotedMessage(message);
                  setQuotedText(text);
                }}
                onRegenerate={() => handleRegenerate(message)}
                regenerating={isSending}
                onToast={setToast}
              />
            ))
          )}
          {isSending ? (
            <LiveThinkingPanel
              agentIds={selectedAgentIds}
              agentMode={agentMode}
              attachmentCount={pendingAttachments.length}
              modelId={selectedModelId}
              toolPreferences={toolPreferences}
            />
          ) : null}
          {!isSending && progressSteps.some((step) => step.status === "error") ? <ProgressPanel steps={progressSteps} /> : null}
        </section>

        <form className="composer" onSubmit={handleSubmit}>
          {quotedMessage ? (
            <div className="quote-banner">
              <span>{labels.quoted}: {(quotedText || quotedMessage.content).slice(0, 160)}</span>
              <button type="button" onClick={() => { setQuotedMessage(null); setQuotedText(""); }}>{labels.clear}</button>
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
          <textarea
            ref={composerTextareaRef}
            rows={2}
            value={input}
            onChange={(event) => {
              setInput(event.target.value);
              resizeComposerInput(event.currentTarget);
              updateMentionState(event.currentTarget.value, event.currentTarget.selectionStart);
            }}
            onClick={(event) => updateMentionState(event.currentTarget.value, event.currentTarget.selectionStart)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setMentionStart(null);
                setMentionQuery("");
              }
            }}
            onKeyUp={(event) => {
              if (event.key !== "Escape") {
                updateMentionState(event.currentTarget.value, event.currentTarget.selectionStart);
              }
            }}
            placeholder={labels.placeholder}
          />
          {mentionCandidates.length ? (
            <div className="mention-menu">
              {mentionCandidates.map((agent) => (
                <button
                  key={agent.id}
                  type="button"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    insertAgentMention(agent);
                  }}
                >
                  <AvatarBadge value={agent.id} className="mention-avatar" />
                  <span>{agentNameForDisplay(agent)}</span>
                  <small>@{agent.id}</small>
                </button>
              ))}
            </div>
          ) : null}
          <div className="composer-footer">
            <div className="composer-left">
              <label className="upload-button">
                + {labels.upload}
                <input multiple type="file" onChange={handleFiles} />
              </label>
            </div>
            {error ? <span className="error-text">{error}</span> : <span />}
            <div className="composer-actions">
              <select className="model-select" value={selectedModelId} onChange={(event) => setSelectedModelId(event.target.value)}>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>{model.name}</option>
                ))}
              </select>
              <button className="send-button" disabled={!activeConversation || isSending || !input.trim()} type="submit">
                {isSending ? labels.sending : labels.send}
              </button>
            </div>
          </div>
        </form>
      </section>

      <button
        aria-label="调整右侧面板宽度"
        className="pane-resizer right-resizer"
        type="button"
        onMouseDown={(event) => startPaneResize("right", event)}
      />
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
          onCreateAgent={handleCreateAgent}
          onEdit={openCodeEditor}
          onPreview={openArtifactPreview}
          onRestoreVersion={handleRestoreArtifactVersion}
          onClosePreview={() => setPreviewArtifact(null)}
          onToast={setToast}
          agentDraft={agentDraft}
          setAgentDraft={setAgentDraft}
          pinnedMessages={pinnedMessages}
          previewArtifact={previewArtifact}
          selectedAgentIds={selectedAgentIds}
          tab={rightTab}
          tools={tools}
        />
      </aside>

      {editArtifact ? (
        <div className="preview-modal" role="dialog" aria-modal="true">
          <div className="editor-card">
            <header>
              <div>
                <h2>{editArtifact.title}</h2>
                <small>{editArtifact.language ?? "text"} · {editArtifact.file_path ?? editArtifact.id}</small>
              </div>
              <button type="button" onClick={() => setEditArtifact(null)}>{labels.close}</button>
            </header>
            <textarea value={editDraft} onChange={(event) => setEditDraft(event.target.value)} />
            <footer>
              <button type="button" onClick={() => navigator.clipboard.writeText(editDraft).then(() => setToast(labels.copied))}>{labels.copy}</button>
              <button type="button" onClick={handleSaveArtifact}>{labels.save}</button>
            </footer>
          </div>
        </div>
      ) : null}
      {toast ? <div className="toast">{toast}</div> : null}

      <aside className={`trash-drawer ${isTrashOpen ? "open" : ""}`}>
        <header className="trash-header">
          <div>
            <strong>{labels.trash}</strong>
            <small>{trashedConversations.length}</small>
          </div>
          <button type="button" onClick={() => setIsTrashOpen(false)}>{labels.close}</button>
        </header>
        <div className="trash-list">
          {trashedConversations.length ? (
            trashedConversations.map((conversation) => (
              <article className="trash-item" key={conversation.id}>
                <div>
                  <strong>{conversation.title}</strong>
                  <small>{conversation.mode} · {displayAgentIds(conversation.agent_ids)}</small>
                  <p>{conversation.last_message || labels.noMessages}</p>
                </div>
                <div className="trash-actions">
                  <button type="button" onClick={() => handleRestoreConversation(conversation.id)}>
                    {labels.restore}
                  </button>
                  <button type="button" onClick={() => setDeleteTargetConversation(conversation)}>
                    {labels.delete}
                  </button>
                </div>
              </article>
            ))
          ) : (
            <div className="conversation-empty">{labels.trashEmpty}</div>
          )}
        </div>
      </aside>

      {deleteTargetConversation ? (
        <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-delete-title">
          <section className="confirm-card">
            <div>
              <h2 id="confirm-delete-title">{labels.confirmDeleteTitle}</h2>
              <p>
                {labels.confirmDeleteBody}
                <span>{deleteTargetConversation.title}</span>
              </p>
            </div>
            <footer>
              <button type="button" onClick={() => setDeleteTargetConversation(null)}>
                {labels.cancel}
              </button>
              <button className="danger" type="button" onClick={handlePermanentDeleteConversation}>
                {labels.yes}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </main>
  );
}

function MessageCard({
  attachmentMap,
  labels: t,
  message,
  onPin,
  onQuote,
  onQuoteSelected,
  onRegenerate,
  regenerating,
  onToast,
}: {
  attachmentMap: Map<string, Attachment>;
  labels: typeof labels;
  message: ChatMessage;
  onPin: () => void;
  onQuote: () => void;
  onQuoteSelected: (text: string) => void;
  onRegenerate: () => void;
  regenerating: boolean;
  onToast: (message: string) => void;
}) {
  const messageAttachments = (message.attachment_ids ?? [])
    .map((id) => attachmentMap.get(id))
    .filter(Boolean) as Attachment[];
  const sender = message.role === "user" ? "user" : message.sender ?? "agent";
  const displayName = displayNameForSender(sender);

  return (
    <article className={`message-card ${message.role}`}>
      <AvatarBadge value={sender} className="avatar" />
      <div className="message-bubble">
        <header>
          <strong>{displayName}</strong>
          <div className="message-actions">
            <button type="button" onClick={onQuote}>{t.quote}</button>
            <button type="button" onClick={() => {
              const selected = window.getSelection()?.toString().trim() ?? "";
              if (selected) {
                onQuoteSelected(selected);
              } else {
                onQuote();
              }
            }}>{t.selectedQuote}</button>
            <button type="button" onClick={onPin}>{message.is_pinned ? t.unpinMessage : t.pinMessage}</button>
          </div>
        </header>
        {message.role === "agent" ? (
          <ThinkingSummary events={message.trace_events ?? []} label={t.thinking} sender={sender} content={message.content} />
        ) : null}
        {message.quoted_message_id || message.quoted_text ? <small className="quoted-line">{t.quoted}: {message.quoted_text || message.quoted_message_id}</small> : null}
        {message.generation_index && message.generation_index > 1 ? (
          <small className="quoted-line">版本 {message.generation_index}{message.is_active_generation === false ? "（旧版）" : ""}</small>
        ) : null}
        <MarkdownMessage content={message.content} copyLabel={t.copy} copiedLabel={t.copied} onToast={onToast} />
        {messageAttachments.length ? <AttachmentList attachments={messageAttachments} /> : null}
        {message.role === "user" ? (
          <div className="message-regenerate-row">
            <button type="button" onClick={onRegenerate} disabled={regenerating}>
              {t.regenerate}
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function ThinkingSummary({
  content,
  events,
  label,
  sender,
}: {
  content: string;
  events: TraceEvent[];
  label: string;
  sender: string;
}) {
  const steps = events.length ? [] : buildThinkingSummary(sender, content);
  const duration = traceDuration(events);
  return (
    <details className="thinking-summary">
      <summary>{duration ? `已思考（用时 ${duration}）` : label}</summary>
      {events.length ? (
        <ol className="thinking-trace">
          {events.map((event, index) => (
            <li className={event.status === "error" ? "error" : ""} key={event.id ?? `${event.type}-${index}`}>
              <span />
              <div>
                <strong>{traceEventTitle(event)}</strong>
                {traceEventDetail(event) ? <p>{traceEventDetail(event)}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <ol>
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}
    </details>
  );
}

function LiveThinkingPanel({
  agentIds,
  agentMode,
  attachmentCount,
  modelId,
  toolPreferences,
}: {
  agentIds: string[];
  agentMode: "single" | "multi";
  attachmentCount: number;
  modelId: string;
  toolPreferences: ToolPreferences;
}) {
  const selectedAgents = agentIds.length ? agentIds.map((agentId) => displayAgentName(agentId)).join("、") : "智能体（Agent）";
  const primaryAgentId = agentIds[0] ?? "orchestrator";
  const enabledTools = (Object.keys(toolPreferences) as Array<keyof ToolPreferences>)
    .filter((key) => toolPreferences[key])
    .map(toolLabel);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    setElapsedSeconds(0);
    const timer = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <article className="message-card agent live-thinking-row">
      <AvatarBadge value={primaryAgentId} className="avatar" />
      <div className="message-bubble live-thinking-bubble">
        <header>
          <strong>思考中（已用时 {elapsedSeconds} 秒）</strong>
          <small>{agentMode === "multi" ? labels.multi : labels.single}</small>
        </header>
        <div className="live-thinking-text" aria-live="polite">
          正在执行真实流程，等待后端返回 Orchestrator、Agent 和 Tool 事件。
          本轮将调用 {selectedAgents}；模型策略 {modelId || "Auto"}；附件 {attachmentCount} 个；工具 {enabledTools.length ? enabledTools.join("、") : "无额外工具"}。
          完成后这里会自动收起，并在正文上方展示真实思考过程。
          <span className="thinking-cursor" />
        </div>
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
  agentDraft,
  agents,
  artifacts,
  attachments,
  labels: t,
  onApply,
  onClosePreview,
  onCreateAgent,
  onEdit,
  onPreview,
  onRestoreVersion,
  onToast,
  pinnedMessages,
  previewArtifact,
  selectedAgentIds,
  tab,
  tools,
  setAgentDraft,
}: {
  activeConversation?: Conversation;
  agentDraft: AgentCreateInput;
  agents: Agent[];
  artifacts: Artifact[];
  attachments: Attachment[];
  labels: typeof labels;
  onApply: (artifact: Artifact) => void;
  onClosePreview: () => void;
  onCreateAgent: (event: FormEvent) => void;
  onEdit: (artifact: Artifact) => void;
  onPreview: (artifact: Artifact) => void;
  onRestoreVersion: (artifact: Artifact, versionId: string) => void;
  onToast: (message: string) => void;
  pinnedMessages: ChatMessage[];
  previewArtifact: Artifact | null;
  selectedAgentIds: string[];
  tab: RightPanelTab;
  tools: ToolOption[];
  setAgentDraft: Dispatch<SetStateAction<AgentCreateInput>>;
}) {
  if (tab === "agents") {
    const selected = agents;
    return (
      <div className="right-content">
        <form className="side-card agent-create-form" onSubmit={onCreateAgent}>
          <strong>{t.createAgent}</strong>
          <input
            value={agentDraft.name ?? ""}
            onChange={(event) => setAgentDraft((current) => ({ ...current, name: event.target.value }))}
            placeholder="智能体名称（Agent name）"
          />
          <input
            value={agentDraft.description ?? ""}
            onChange={(event) => setAgentDraft((current) => ({ ...current, description: event.target.value }))}
            placeholder="Description"
          />
          <textarea
            value={agentDraft.system_prompt ?? ""}
            onChange={(event) => setAgentDraft((current) => ({ ...current, system_prompt: event.target.value }))}
            placeholder={t.systemPrompt}
          />
          <div className="agent-picker">
            {tools.map((tool) => (
              <label key={tool.id}>
                <input
                  checked={(agentDraft.tools ?? []).includes(tool.id)}
                  type="checkbox"
                  onChange={() =>
                    setAgentDraft((current) => {
                      const currentTools = current.tools ?? [];
                      return {
                        ...current,
                        tools: currentTools.includes(tool.id)
                          ? currentTools.filter((item) => item !== tool.id)
                          : [...currentTools, tool.id],
                      };
                    })
                  }
                />
                <span>{tool.name ?? tool.id}</span>
              </label>
            ))}
          </div>
          <button type="submit">{t.createAgent}</button>
        </form>
        {selected.map((agent) => (
          <section className="side-card agent-side-card" key={agent.id}>
            <div className="agent-side-header">
              <AvatarBadge value={agent.id} className="agent-avatar" />
              <div>
                <strong>{agentNameForDisplay(agent)}</strong>
                {agent.is_custom ? <small>自定义智能体（Custom Agent）</small> : null}
              </div>
            </div>
            <p>{agent.description}</p>
            <TagRow items={agent.capabilities ?? []} />
            {agent.system_prompt ? <small>Prompt: {agent.system_prompt.slice(0, 120)}</small> : null}
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
      {previewArtifact ? (
        <ArtifactPreviewPanel artifact={previewArtifact} labels={t} onClose={onClosePreview} />
      ) : null}
      {artifacts.length === 0 ? (
        <section className="side-card"><p>{t.noArtifacts}</p></section>
      ) : (
        artifacts.map((artifact) => (
          <ArtifactCard
            artifact={artifact}
            key={artifact.id}
            labels={t}
            onApply={() => onApply(artifact)}
            onEdit={() => onEdit(artifact)}
            onPreview={() => onPreview(artifact)}
            onRestoreVersion={(versionId) => onRestoreVersion(artifact, versionId)}
            onToast={onToast}
          />
        ))
      )}
    </div>
  );
}

function ArtifactCard({
  artifact,
  labels: t,
  onApply,
  onEdit,
  onPreview,
  onRestoreVersion,
  onToast,
}: {
  artifact: Artifact;
  labels: typeof labels;
  onApply: () => void;
  onEdit: () => void;
  onPreview: () => void;
  onRestoreVersion: (versionId: string) => void;
  onToast: (message: string) => void;
}) {
  const [diff, setDiff] = useState<StructuredDiff | null>(null);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const showPreviewButton = artifact.type === "code" || Boolean(artifact.preview_url);

  async function handleCopy() {
    await navigator.clipboard.writeText(artifact.content ?? artifact.preview_url ?? "");
    onToast(t.copied);
  }

  async function handleToggleDiff() {
    if (diff) {
      setDiff(null);
      return;
    }
    setDiff(await getArtifactDiff(artifact.id));
  }

  async function handleToggleVersions() {
    if (versions.length) {
      setVersions([]);
      return;
    }
    setVersions(await getArtifactVersions(artifact.id));
  }

  return (
    <article className={`artifact-card ${artifact.type}`}>
      <header>
        <span>{artifact.type}</span>
        <strong>{artifact.title}</strong>
      </header>
      {artifact.type === "deployment" ? (
        <div className="deployment-card">
          <strong>{artifact.status ?? "success"}</strong>
          <p>{artifact.logs ?? artifact.content}</p>
          {artifact.preview_url ? <a href={`${API_ORIGIN}${artifact.preview_url}`} target="_blank" rel="noreferrer">{t.deployOpen}</a> : null}
        </div>
      ) : null}
      {artifact.type === "document_preview" || artifact.type === "presentation_preview" ? (
        <div className="deployment-card">
          <p>{artifact.content}</p>
          {artifact.preview_url ? <a href={`${API_ORIGIN}${artifact.preview_url}`} target="_blank" rel="noreferrer">{t.preview}</a> : null}
        </div>
      ) : null}
      {artifact.content && artifact.type !== "deployment" && artifact.type !== "document_preview" && artifact.type !== "presentation_preview" ? (
        <small className="artifact-meta">
          {artifact.language ?? artifact.type} · {artifact.file_path ?? artifact.id}
        </small>
      ) : null}
      {diff ? <DiffViewer diff={diff} /> : null}
      {versions.length ? (
        <div className="version-list">
          {versions.map((version) => (
            <button key={version.id} type="button" onClick={() => onRestoreVersion(version.id)}>
              {t.restore} {version.reason} · {new Date(version.created_at).toLocaleString()}
            </button>
          ))}
        </div>
      ) : null}
      <footer>
        {artifact.content ? <button type="button" onClick={handleCopy}>{t.copy}</button> : null}
        {artifact.type === "code" ? <button type="button" onClick={onEdit}>{t.edit}</button> : null}
        {artifact.content ? <button type="button" onClick={handleToggleVersions}>{t.versions}</button> : null}
        {artifact.type === "diff" ? <button type="button" onClick={handleToggleDiff}>{t.viewDiff}</button> : null}
        {showPreviewButton ? <button type="button" onClick={onPreview}>{t.preview}</button> : null}
        {artifact.type === "diff" ? (
          <button disabled={artifact.status === "applied"} type="button" onClick={onApply}>
            {artifact.status === "applied" ? t.applied : t.applyDiff}
          </button>
        ) : null}
      </footer>
    </article>
  );
}

function ArtifactPreviewPanel({
  artifact,
  labels: t,
  onClose,
}: {
  artifact: Artifact;
  labels: typeof labels;
  onClose: () => void;
}) {
  const inlineHtml = htmlPreviewContent(artifact);
  const previewUrl = artifact.preview_url ? `${API_ORIGIN}${artifact.preview_url}` : "";

  return (
    <section className="artifact-preview-panel">
      <header>
        <div>
          <strong>{t.preview}</strong>
          <small>{artifact.title}</small>
        </div>
        <button type="button" onClick={onClose}>{t.close}</button>
      </header>
      {inlineHtml ? (
        <iframe
          title={`${artifact.title} preview`}
          sandbox="allow-forms allow-modals allow-scripts"
          srcDoc={inlineHtml}
        />
      ) : previewUrl ? (
        <iframe title={`${artifact.title} preview`} src={previewUrl} />
      ) : (
        <div className="artifact-preview-empty">
          <strong>暂不支持直接预览</strong>
          <p>当前产物不是完整 HTML。TSX/JSX 代码需要生成 HTML，或通过 preview_tool 生成预览产物后再查看。</p>
        </div>
      )}
    </section>
  );
}

function htmlPreviewContent(artifact: Artifact): string {
  const content = artifact.content?.trim();
  if (!content) {
    return "";
  }

  const metadata = `${artifact.language ?? ""} ${artifact.file_path ?? ""} ${artifact.title ?? ""}`.toLowerCase();
  const fencedHtml = extractHtmlFence(content);
  if (fencedHtml) {
    return fencedHtml;
  }

  const looksLikeHtml =
    /<!doctype\s+html/i.test(content) ||
    /<html[\s>]/i.test(content) ||
    /<body[\s>]/i.test(content);

  const languageMatches = /(^|\b)(html|htm)(\b|$)/i.test(metadata);
  if (looksLikeHtml || languageMatches) {
    return content;
  }

  return "";
}

function extractHtmlFence(content: string): string {
  const fencePattern = /```(?:html)?\n?([\s\S]*?)```/gi;
  let match: RegExpExecArray | null;
  while ((match = fencePattern.exec(content)) !== null) {
    const candidate = match[1].trim();
    if (
      /<!doctype\s+html/i.test(candidate) ||
      /<html[\s>]/i.test(candidate) ||
      /<body[\s>]/i.test(candidate)
    ) {
      return candidate;
    }
  }
  return "";
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

function DiffViewer({ diff }: { diff: StructuredDiff }) {
  return (
    <div className="diff-viewer">
      {diff.files.map((file) => (
        <section key={`${file.old_path}-${file.new_path}`}>
          <strong>{file.new_path}</strong>
          {file.hunks.map((hunk) => (
            <div className="diff-hunk" key={hunk.header}>
              <small>{hunk.header}</small>
              {hunk.lines.map((line, index) => (
                <div className={`diff-line ${line.type}`} key={`${hunk.header}-${index}`}>
                  <span>{line.old_no ?? ""}</span>
                  <span>{line.new_no ?? ""}</span>
                  <code>{line.type === "add" ? "+" : line.type === "remove" ? "-" : " "}{line.content}</code>
                </div>
              ))}
            </div>
          ))}
        </section>
      ))}
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
    { id: "agent", label: "调用智能体（Agent）", status: "pending" },
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
        label: "调用智能体（Agent）",
        detail: displayAgentName(String(event.payload.agent_id ?? "")),
        status: "done",
      });
    }
    if (event.type === "agent.completed") {
      steps.push({
        id: `${event.type}-${steps.length}`,
        label: "智能体（Agent）完成",
        detail: `${displayAgentName(String(event.payload.agent_id ?? ""))} · ${event.payload.status ?? ""}`,
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

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
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

function readLegacyTrashedConversations(): Conversation[] {
  try {
    const raw = window.localStorage.getItem(TRASH_STORAGE_KEY);
    return raw ? JSON.parse(raw) as Conversation[] : [];
  } catch {
    return [];
  }
}

function clearLegacyTrashedConversations() {
  try {
    window.localStorage.removeItem(TRASH_STORAGE_KEY);
  } catch {
    // The server-side trash state is the source of truth now.
  }
}

function AvatarBadge({ value, className = "" }: { value: string; className?: string }) {
  const profile = avatarProfile(value);
  return (
    <span className={`avatar-badge ${profile.tone} ${className}`} aria-hidden="true">
      <span className="avatar-hair" />
      <span className="avatar-face">
        <span className="avatar-eye left" />
        <span className="avatar-eye right" />
        <span className="avatar-mouth" />
      </span>
      {profile.symbol ? <span className="avatar-symbol">{profile.symbol}</span> : null}
    </span>
  );
}

function agentNameForDisplay(agent: Agent): string {
  return displayAgentName(agent.id, agent.name);
}

function displayAgentIds(agentIds: string[]): string {
  return agentIds.map((agentId) => displayAgentName(agentId)).join(", ");
}

function displayAgentName(value: string, fallback?: string): string {
  const name = (fallback ?? value).trim();
  const normalized = `${value} ${name}`.toLowerCase();

  if (normalized.includes("orchestrator")) {
    return "协调器（Orchestrator）";
  }
  if (normalized.includes("codex")) {
    return "代码智能体（Codex）";
  }
  if (normalized.includes("code_agent") || normalized.includes("code agent")) {
    return "代码智能体（Code Agent）";
  }
  if (normalized.includes("ui_builder") || normalized.includes("ui builder")) {
    return "界面构建智能体（UI Builder）";
  }
  if (normalized.includes("code_reviewer") || normalized.includes("code reviewer")) {
    return "代码审查智能体（Code Reviewer）";
  }
  if (normalized.includes("vision")) {
    return "视觉智能体（Vision Agent）";
  }
  if (normalized.includes("file")) {
    return "文件分析智能体（File Analyst）";
  }
  if (normalized.trim() === "agent") {
    return "智能体（Agent）";
  }
  if (!name) {
    return "智能体（Agent）";
  }
  if (/[（(]/.test(name)) {
    return name;
  }
  return `${name}（Custom Agent）`;
}

function avatarProfile(value: string): { symbol: string; tone: string } {
  const normalized = value.toLowerCase();
  if (normalized === "user" || normalized === "you" || normalized === "你") {
    return { symbol: "", tone: "avatar-user" };
  }
  if (normalized.includes("orchestrator")) {
    return { symbol: "PL", tone: "avatar-orchestrator" };
  }
  if (normalized.includes("codex") || normalized.includes("code_agent")) {
    return { symbol: "</>", tone: "avatar-code" };
  }
  if (normalized.includes("ui_builder") || normalized.includes("ui")) {
    return { symbol: "UI", tone: "avatar-ui" };
  }
  if (normalized.includes("review")) {
    return { symbol: "OK", tone: "avatar-review" };
  }
  if (normalized.includes("vision")) {
    return { symbol: "VI", tone: "avatar-vision" };
  }
  if (normalized.includes("file")) {
    return { symbol: "FI", tone: "avatar-file" };
  }
  return { symbol: normalized.slice(0, 2).toUpperCase() || "AG", tone: "avatar-custom" };
}

function displayNameForSender(sender: string): string {
  const normalized = sender.toLowerCase();
  if (normalized === "user" || normalized === "you" || normalized === "你") {
    return "你";
  }
  return displayAgentName(sender);
}

function traceDuration(events: TraceEvent[]): string {
  const durationMs = Math.max(
    0,
    ...events.map((event) => Number(event.duration_ms ?? 0)).filter((value) => Number.isFinite(value)),
  );
  if (!durationMs) {
    return "";
  }
  const seconds = Math.max(1, Math.round(durationMs / 1000));
  return `${seconds} 秒`;
}

function traceEventTitle(event: TraceEvent): string {
  const payload = event.payload ?? {};
  switch (event.type) {
    case "message.received":
      return "收到用户消息";
    case "context.loaded":
      return "读取会话上下文";
    case "model.selected":
      return "选择模型";
    case "attachments.prepared":
      return "准备附件";
    case "run.started":
      return "启动协调器（Orchestrator）";
    case "run.planned":
      return "完成任务拆解";
    case "agent.started":
    case "agent.parallel_started":
      return `调用 ${displayAgentName(String(payload.agent_id ?? event.agent_id ?? ""))}`;
    case "agent.completed":
      return `${displayAgentName(String(payload.agent_id ?? event.agent_id ?? ""))} 完成`;
    case "agent.skipped":
      return `跳过 ${displayAgentName(String(payload.agent_id ?? event.agent_id ?? ""))}`;
    case "tool.started":
      return `调用 ${displayToolName(String(payload.tool_id ?? ""))}`;
    case "tool.completed":
      return `${displayToolName(String(payload.tool_id ?? ""))} 完成`;
    case "tool.failed":
      return `${displayToolName(String(payload.tool_id ?? ""))} 失败`;
    case "run.completed":
      return "汇总执行结果";
    default:
      return event.title ?? event.type;
  }
}

function traceEventDetail(event: TraceEvent): string {
  const payload = event.payload ?? {};
  if (event.type === "context.loaded") {
    return [
      `${Number(payload.history_count ?? 0)} 条历史`,
      `${Number(payload.pinned_count ?? 0)} 条长期上下文`,
      `模式 ${String(payload.mode ?? "")}`,
      `Agent ${displayAgentIds(toStringList(payload.selected_agents)) || "auto"}`,
    ].join("，");
  }
  if (event.type === "agent.started" || event.type === "agent.parallel_started") {
    const tools = toStringList(payload.tools).map(displayToolName);
    const task = String(payload.task ?? "");
    return tools.length ? `${task}；工具 ${tools.join("、")}` : task;
  }
  if (event.type === "agent.completed") {
    const status = String(payload.status ?? "");
    const artifactCount = Number(payload.artifact_count ?? 0);
    const error = payload.error ? `，错误：${String(payload.error)}` : "";
    return `状态 ${status || "done"}，产物 ${artifactCount} 个${error}`;
  }
  if (event.type === "tool.started") {
    const keys = toStringList(payload.argument_keys);
    return `参数：${keys.length ? keys.join("、") : "none"}`;
  }
  if (event.type === "tool.completed") {
    return `生成 ${String(payload.artifact_type ?? "")}：${String(payload.artifact_title ?? "")}`;
  }
  if (event.type === "tool.failed") {
    return String(payload.error ?? "");
  }
  if (event.type === "run.planned") {
    const steps = Array.isArray(payload.steps) ? payload.steps.length : 0;
    return `${steps} 个步骤：${String(payload.reason ?? "")}`;
  }
  if (event.type === "run.completed") {
    return [
      `状态 ${String(payload.status ?? "")}`,
      `Agent ${Number(payload.agent_count ?? 0)} 个`,
      `产物 ${Number(payload.artifact_count ?? 0)} 个`,
      `冲突 ${Number(payload.conflict_count ?? 0)} 个`,
    ].join("，");
  }
  return event.detail ?? "";
}

function toStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function displayToolName(toolId: string): string {
  const normalized = toolId.toLowerCase();
  const names: Record<string, string> = {
    ui_builder_tool: "界面构建工具（ui_builder_tool）",
    code_review_tool: "代码审查工具（code_review_tool）",
    preview_tool: "预览工具（preview_tool）",
    deploy_tool: "部署工具（deploy_tool）",
    document_preview_tool: "文档预览工具（document_preview_tool）",
    file_reader_tool: "文件读取工具（file_reader_tool）",
    image_reader_tool: "图片读取工具（image_reader_tool）",
  };
  return names[normalized] ?? (toolId ? `${toolId}（Tool）` : "工具（Tool）");
}

function buildThinkingSummary(sender: string, content: string): string[] {
  const normalized = sender.toLowerCase();
  const summaryHint = buildThinkingSummaryHint(content);
  const steps = [
    "读取当前会话上下文",
    "判断当前问题需要的智能体（Agent）与工具",
    summaryHint,
  ];
  if (normalized.includes("orchestrator")) {
    steps.splice(1, 2, "拆分任务并安排执行顺序", "协调可用智能体（Agent）与工具返回结果");
  } else if (normalized.includes("ui_builder")) {
    steps.splice(1, 2, "提炼页面结构、布局和状态", "生成可继续预览或审查的前端产物");
  } else if (normalized.includes("review")) {
    steps.splice(1, 2, "检查代码风险、可维护性和遗漏点", "按优先级整理审查建议");
  } else if (normalized.includes("codex") || normalized.includes("code_agent")) {
    steps.splice(1, 2, "定位代码任务和约束", "组织实现方案并输出代码片段");
  } else if (normalized.includes("vision")) {
    steps.splice(1, 2, "读取图片或截图的视觉线索", "转成可执行的界面与内容建议");
  } else if (normalized.includes("file")) {
    steps.splice(1, 2, "读取附件内容和结构", "提取需求、约束和可执行信息");
  }
  if (/fallback|failed|失败|error/i.test(content)) {
    return [...steps, "检测到异常时保留回退结果"];
  }
  return steps;
}

function buildThinkingSummaryHint(content: string): string {
  const text = content.toLowerCase();
  if (/<!doctype\s+html|<html[\s>]|<body[\s>]/i.test(content)) {
    return "识别到 HTML 产物，保留结构以便预览和复用";
  }
  if (/```[\s\S]*?```/.test(content)) {
    return "识别到代码块，整理为可复制的输出内容";
  }
  if (/\btsx\b|\bjsx\b|\breact\b/i.test(text)) {
    return "识别到前端代码意图，优先保持组件结构和可视层";
  }
  if (/\bpython\b|\bfastapi\b|\bapi\b/i.test(text)) {
    return "识别到后端或接口意图，优先整理为可执行逻辑";
  }
  if (content.length > 220) {
    return "内容较长，先压缩关键结论，再输出正文";
  }
  return "整理关键结论后输出到对话框正文";
}

export default App;
