import { ChangeEvent, CSSProperties, Dispatch, FormEvent, MouseEvent as ReactMouseEvent, ReactNode, SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  applyArtifactDiff,
  archiveConversation,
  createAgent,
  createConversation,
  deleteAgent,
  deleteConversation,
  deleteConversationMemory,
  extractMessageMemory,
  getArtifactDiff,
  getArtifactVersions,
  getAgents,
  getConversationArtifacts,
  getConversationAttachments,
  getConversationMessages,
  getConversationMemories,
  getConversations,
  getModels,
  getTools,
  pinConversation,
  pinMessage,
  regenerateChatMessage,
  restoreConversation,
  restoreArtifactVersion,
  runWorkflowArtifact,
  sendChatMessage,
  trashConversation,
  unarchiveConversation,
  unpinConversation,
  unpinMessage,
  updateArtifact,
  updateAgent,
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
  ConversationMemory,
  ModelOption,
  StructuredDiff,
  StructuredDiffLine,
  TraceEvent,
  ToolOption,
  ToolPreferences,
} from "./types";

const API_ORIGIN = "/api";
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
type ConversationDetailState = {
  messages: ChatMessage[];
  artifacts: Artifact[];
  attachments: Attachment[];
  memories: ConversationMemory[];
};
type ConversationRuntimeState = {
  input: string;
  isSending: boolean;
  progressSteps: ProgressStep[];
  pendingAttachments: Attachment[];
  quotedMessage: ChatMessage | null;
  quotedText: string;
  thinkingStartedAt: number | null;
};
const emptyConversationDetail: ConversationDetailState = {
  messages: [],
  artifacts: [],
  attachments: [],
  memories: [],
};
const emptyConversationRuntime: ConversationRuntimeState = {
  input: "",
  isSending: false,
  progressSteps: [],
  pendingAttachments: [],
  quotedMessage: null,
  quotedText: "",
  thinkingStartedAt: null,
};

type ToastKind = "info" | "success" | "error";
type ToastEntry = { id: number; message: string; kind: ToastKind };

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
  runWorkflow: "运行 Workflow",
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
  const [openConversationIds, setOpenConversationIds] = useState<string[]>([]);
  const [detailsByConversation, setDetailsByConversation] = useState<Record<string, ConversationDetailState>>({});
  const [runtimeByConversation, setRuntimeByConversation] = useState<Record<string, ConversationRuntimeState>>({});
  const [conversationSearch, setConversationSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftMode, setDraftMode] = useState<ConversationMode>("single");
  const [draftAgentIds, setDraftAgentIds] = useState<string[]>(["orchestrator"]);
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null);
  const [editArtifact, setEditArtifact] = useState<Artifact | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [agentDraft, setAgentDraft] = useState<AgentCreateInput>({
    name: "",
    description: "",
    system_prompt: "",
    capabilities: ["text"],
    tools: [],
    avatar: "",
    model_provider: undefined,
    model_name: "",
  });
  const [editingAgentId, setEditingAgentId] = useState("");
  const [agentEditorDraft, setAgentEditorDraft] = useState<AgentCreateInput | null>(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [rightTab, setRightTab] = useState<RightPanelTab>("artifacts");
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true);
  const [agentRowExpanded, setAgentRowExpanded] = useState(false);
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
  const abortControllersByConversationRef = useRef<Record<string, AbortController>>({});

  const activeConversation = conversations.find((item) => item.id === activeConversationId);
  const activeDetail = detailsByConversation[activeConversationId] ?? emptyConversationDetail;
  const activeRuntime = runtimeByConversation[activeConversationId] ?? emptyConversationRuntime;
  const messages = activeDetail.messages;
  const artifacts = activeDetail.artifacts;
  const attachments = activeDetail.attachments;
  const input = activeRuntime.input;
  const isSending = activeRuntime.isSending;
  const progressSteps = activeRuntime.progressSteps;
  const pendingAttachments = activeRuntime.pendingAttachments;
  const quotedMessage = activeRuntime.quotedMessage;
  const quotedText = activeRuntime.quotedText;
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
  const artifactMap = useMemo(
    () => new Map(artifacts.map((artifact) => [artifact.id, artifact])),
    [artifacts],
  );
  const visibleArtifacts = useMemo(() => latestVisibleArtifacts(artifacts), [artifacts]);
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
    "--conversation-width": leftSidebarOpen ? `${conversationWidth}px` : "60px",
    "--right-panel-width": rightPanelOpen ? `${rightPanelWidth}px` : "0px",
  } as CSSProperties;
  const runningConversationCount = Object.values(runtimeByConversation).filter((runtime) => runtime.isSending).length;
  const visibleRightTabs: RightPanelTab[] = ["artifacts", "agents", "context"];

  function updateConversationDetail(
    conversationId: string,
    update: Partial<ConversationDetailState> | ((current: ConversationDetailState) => ConversationDetailState),
  ) {
    if (!conversationId) {
      return;
    }
    setDetailsByConversation((current) => {
      const detail = current[conversationId] ?? emptyConversationDetail;
      const next = typeof update === "function" ? update(detail) : { ...detail, ...update };
      return { ...current, [conversationId]: next };
    });
  }

  function updateConversationRuntime(
    conversationId: string,
    update: Partial<ConversationRuntimeState> | ((current: ConversationRuntimeState) => ConversationRuntimeState),
  ) {
    if (!conversationId) {
      return;
    }
    setRuntimeByConversation((current) => {
      const runtime = current[conversationId] ?? emptyConversationRuntime;
      const next = typeof update === "function" ? update(runtime) : { ...runtime, ...update };
      return { ...current, [conversationId]: next };
    });
  }

  function openConversation(conversationId: string) {
    setOpenConversationIds((current) => current.includes(conversationId) ? current : [...current, conversationId]);
    setActiveConversationId(conversationId);
    setOpenConversationMenuId("");
  }

  function closeConversationTab(conversationId: string) {
    setOpenConversationIds((current) => {
      const next = current.filter((id) => id !== conversationId);
      if (activeConversationId === conversationId) {
        setActiveConversationId(next[next.length - 1] ?? "");
      }
      return next;
    });
  }

  function setInput(value: SetStateAction<string>) {
    updateConversationRuntime(activeConversationId, (current) => ({
      ...current,
      input: typeof value === "function" ? value(current.input) : value,
    }));
  }

  function setMessages(value: SetStateAction<ChatMessage[]>) {
    updateConversationDetail(activeConversationId, (current) => ({
      ...current,
      messages: typeof value === "function" ? value(current.messages) : value,
    }));
  }

  function setArtifacts(value: SetStateAction<Artifact[]>) {
    updateConversationDetail(activeConversationId, (current) => ({
      ...current,
      artifacts: typeof value === "function" ? value(current.artifacts) : value,
    }));
  }

  function setAttachments(value: SetStateAction<Attachment[]>) {
    updateConversationDetail(activeConversationId, (current) => ({
      ...current,
      attachments: typeof value === "function" ? value(current.attachments) : value,
    }));
  }

  function setPendingAttachments(value: SetStateAction<Attachment[]>) {
    updateConversationRuntime(activeConversationId, (current) => ({
      ...current,
      pendingAttachments: typeof value === "function" ? value(current.pendingAttachments) : value,
    }));
  }

  function setQuotedMessage(value: SetStateAction<ChatMessage | null>) {
    updateConversationRuntime(activeConversationId, (current) => ({
      ...current,
      quotedMessage: typeof value === "function" ? value(current.quotedMessage) : value,
    }));
  }

  function setQuotedText(value: SetStateAction<string>) {
    updateConversationRuntime(activeConversationId, (current) => ({
      ...current,
      quotedText: typeof value === "function" ? value(current.quotedText) : value,
    }));
  }

  function setProgressSteps(value: SetStateAction<ProgressStep[]>) {
    updateConversationRuntime(activeConversationId, (current) => ({
      ...current,
      progressSteps: typeof value === "function" ? value(current.progressSteps) : value,
    }));
  }

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

  const pushToast = useCallback((message: string, kind: ToastKind = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, kind }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((entry) => entry.id !== id));
    }, 4200);
  }, []);

  function cancelInFlight(conversationId: string) {
    const controller = abortControllersByConversationRef.current[conversationId];
    if (controller) {
      controller.abort();
      delete abortControllersByConversationRef.current[conversationId];
    }
  }

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
        setOpenConversationIds((open) => open.includes(preferredId) ? open : [...open, preferredId]);
        return preferredId;
      }
      if (current && visibleItems.some((item) => item.id === current)) {
        return current;
      }
      const nextId = visibleItems[0]?.id ?? "";
      if (nextId) {
        setOpenConversationIds((open) => open.includes(nextId) ? open : [...open, nextId]);
      }
      return nextId;
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
    const [nextMessages, nextArtifacts, nextAttachments, nextMemories] = await Promise.all([
      getConversationMessages(conversationId),
      getConversationArtifacts(conversationId),
      getConversationAttachments(conversationId),
      getConversationMemories(conversationId),
    ]);
    updateConversationDetail(conversationId, {
      messages: nextMessages,
      artifacts: nextArtifacts,
      attachments: nextAttachments,
      memories: nextMemories,
    });
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

  async function handleChangeMode(nextMode: "single" | "multi") {
    if (nextMode === agentMode) {
      return;
    }
    setAgentMode(nextMode);
    const nextAgentIds =
      nextMode === "multi" ? defaultAgentIds : [draftAgentIds[0] ?? "orchestrator"];
    setDraftAgentIds(nextAgentIds);
    if (activeConversation) {
      try {
        await updateConversation(activeConversation.id, {
          mode: nextMode === "multi" ? "group" : "single",
          agent_ids: nextAgentIds,
        });
        await reloadConversations(activeConversation.id);
      } catch (err) {
        setToast(err instanceof Error ? err.message : "模式切换失败");
      }
    }
  }

  function handleToggleAgentForActiveConversation(agentId: string) {
    if (!activeConversation) {
      return;
    }
    const current = activeConversation.agent_ids.length ? activeConversation.agent_ids : draftAgentIds;
    const isMulti = activeConversation.mode !== "single";
    let next: string[];
    if (isMulti) {
      next = current.includes(agentId)
        ? current.filter((id) => id !== agentId)
        : [...current, agentId];
      if (next.length === 0) {
        return;
      }
    } else {
      next = [agentId];
    }
    setDraftAgentIds(next);
    updateConversation(activeConversation.id, {
      agent_ids: next,
    })
      .then(() => reloadConversations(activeConversation.id))
      .catch((err) => setToast(err instanceof Error ? err.message : "Agent 选择失败"));
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
    const conversationId = activeConversation.id;
    setError("");
    try {
      const uploaded = await Promise.all(
        Array.from(event.target.files).map(async (file) => {
          const preparedFile = file.type.startsWith("image/")
            ? await compressImageFile(file)
            : file;
          const contentBase64 = await fileToBase64(preparedFile);
          return uploadAttachment(conversationId, {
            filename: preparedFile.name,
            mime_type: preparedFile.type || undefined,
            content_base64: contentBase64,
          });
        }),
      );
      updateConversationDetail(conversationId, (current) => ({
        ...current,
        attachments: [...current.attachments, ...uploaded],
      }));
      updateConversationRuntime(conversationId, (current) => ({
        ...current,
        pendingAttachments: [...current.pendingAttachments, ...uploaded],
      }));
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

    const conversationId = activeConversation.id;
    const runtimeAtSend = runtimeByConversation[conversationId] ?? emptyConversationRuntime;
    const attachmentIds = pendingAttachments.map((attachment) => attachment.id);
    const optimisticMessage: ChatMessage = {
      id: `local_${Date.now()}`,
      conversation_id: conversationId,
      role: "user",
      sender: "you",
      content,
      format: "markdown",
      quoted_message_id: quotedMessage?.id,
      quoted_text: quotedText || quotedMessage?.content,
      attachment_ids: attachmentIds,
    };

    updateConversationDetail(conversationId, (current) => ({
      ...current,
      messages: [...current.messages, optimisticMessage],
    }));
    const abortController = new AbortController();
    abortControllersByConversationRef.current[conversationId] = abortController;
    updateConversationRuntime(conversationId, (current) => ({
      ...current,
      input: "",
      isSending: true,
      progressSteps: initialProgressSteps(selectedModelId, attachmentIds.length),
      thinkingStartedAt: Date.now(),
    }));
    setError("");
    try {
      const response = await sendChatMessage(
        content,
        conversationId,
        selectedAgentIds,
        runtimeAtSend.quotedMessage?.id,
        runtimeAtSend.quotedText || runtimeAtSend.quotedMessage?.content,
        attachmentIds,
        selectedModelId,
        undefined,
        agentMode,
        toolPreferences,
        abortController.signal,
      );
      applyChatResponse(conversationId, response);
      updateConversationRuntime(conversationId, (current) => ({
        ...current,
        pendingAttachments: [],
        quotedMessage: null,
        quotedText: "",
      }));
      await reloadConversations(conversationId);
      getAgents().then(setAgents).catch(() => undefined);
      pushToast("回复已生成", "success");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        pushToast("已取消发送", "info");
      } else {
        updateConversationRuntime(conversationId, (current) => ({
          ...current,
          progressSteps: markProgressError(current.progressSteps, err instanceof Error ? err.message : "Send failed"),
        }));
        const message = err instanceof Error ? err.message : "Send failed";
        setError(message);
        pushToast(message, "error");
      }
    } finally {
      delete abortControllersByConversationRef.current[conversationId];
      updateConversationRuntime(conversationId, { isSending: false, thinkingStartedAt: null });
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
    const conversationId = activeConversation.id;
    const abortController = new AbortController();
    abortControllersByConversationRef.current[conversationId] = abortController;
    updateConversationRuntime(conversationId, {
      isSending: true,
      progressSteps: initialProgressSteps(selectedModelId, lastUserMessage.attachment_ids?.length ?? 0),
      thinkingStartedAt: Date.now(),
    });
    try {
      const response = await regenerateChatMessage(
        lastUserMessage.content,
        conversationId,
        selectedAgentIds,
        lastUserMessage.id,
        selectedModelId,
        undefined,
        agentMode,
        toolPreferences,
        abortController.signal,
      );
      applyChatResponse(conversationId, response);
      await reloadConversations(conversationId);
      pushToast("已重新生成", "success");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        pushToast("已取消重新生成", "info");
      } else {
        updateConversationRuntime(conversationId, (current) => ({
          ...current,
          progressSteps: markProgressError(current.progressSteps, err instanceof Error ? err.message : "Regenerate failed"),
        }));
        const message = err instanceof Error ? err.message : "Regenerate failed";
        setError(message);
        pushToast(message, "error");
      }
    } finally {
      delete abortControllersByConversationRef.current[conversationId];
      updateConversationRuntime(conversationId, { isSending: false, thinkingStartedAt: null });
    }
  }

  function applyChatResponse(conversationId: string, response: ChatResponse) {
    const traceEvents = response.events ?? [];
    const responseMessages = response.messages.map((message) =>
      message.role === "agent" && !(message.trace_events?.length)
        ? { ...message, trace_events: traceEvents }
        : message,
    );
    updateConversationDetail(conversationId, (current) => ({
      ...current,
      messages: [...current.messages, ...responseMessages],
      artifacts: [...current.artifacts, ...response.artifacts],
    }));
    updateConversationRuntime(conversationId, {
      progressSteps: progressFromEvents(response.events ?? []),
    });
  }

  async function handleMessagePin(message: ChatMessage) {
    if (!activeConversation) {
      return;
    }
    const conversationId = activeConversation.id;
    const updated = message.is_pinned
      ? await unpinMessage(conversationId, message.id)
      : await pinMessage(conversationId, message.id);
    updateConversationDetail(conversationId, (current) => ({
      ...current,
      messages: current.messages.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
    }));
  }

  async function handleExtractMemory(message: ChatMessage) {
    if (!activeConversation) {
      return;
    }
    const conversationId = activeConversation.id;
    try {
      const created = await extractMessageMemory(
        conversationId,
        message.id,
        selectedModelId,
      );
      const refreshed = await getConversationMemories(conversationId);
      updateConversationDetail(conversationId, (current) => ({
        ...current,
        memories: refreshed,
      }));
      setRightPanelOpen(true);
      setRightTab("context");
      setToast(created.length ? `已提取 ${created.length} 条智能记忆` : "没有发现新的长期记忆");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Memory extraction failed");
    }
  }

  async function handleDeleteMemory(memoryId: string) {
    if (!activeConversation) {
      return;
    }
    const conversationId = activeConversation.id;
    await deleteConversationMemory(conversationId, memoryId);
    updateConversationDetail(conversationId, (current) => ({
      ...current,
      memories: current.memories.filter((memory) => memory.id !== memoryId),
    }));
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

  async function handleRunWorkflow(artifact: Artifact) {
    if (!activeConversation || isSending) {
      return;
    }
    const conversationId = activeConversation.id;
    updateConversationRuntime(conversationId, {
      isSending: true,
      progressSteps: initialProgressSteps(selectedModelId, attachments.length),
      thinkingStartedAt: Date.now(),
    });
    setError("");
    try {
      const response = await runWorkflowArtifact(artifact.id, selectedModelId);
      applyChatResponse(conversationId, response);
      setRightPanelOpen(true);
      setRightTab("artifacts");
      setToast("Workflow 已运行");
      await reloadConversations(conversationId);
    } catch (err) {
      updateConversationRuntime(conversationId, (current) => ({
        ...current,
        progressSteps: markProgressError(
          current.progressSteps,
          err instanceof Error ? err.message : "Workflow run failed",
        ),
      }));
      setError(err instanceof Error ? err.message : "Workflow run failed");
    } finally {
      updateConversationRuntime(conversationId, { isSending: false, thinkingStartedAt: null });
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
      avatar: "",
      model_provider: undefined,
      model_name: "",
    });
    setToast("智能体（Agent）已创建");
  }

  function beginEditAgent(agent: Agent) {
    if (!agent.is_custom) {
      return;
    }
    setEditingAgentId(agent.id);
    setAgentEditorDraft({
      id: agent.id,
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt ?? "",
      capabilities: agent.capabilities ?? ["text"],
      tools: agent.tools ?? [],
      model_provider: agent.model_provider,
      model_name: agent.model_name,
      avatar: agent.avatar,
    });
  }

  async function handleSaveAgent(event: FormEvent) {
    event.preventDefault();
    if (!editingAgentId || !agentEditorDraft?.name?.trim()) {
      return;
    }
    const updated = await updateAgent(editingAgentId, agentEditorDraft);
    setAgents((current) => current.map((agent) => (agent.id === updated.id ? updated : agent)));
    setEditingAgentId("");
    setAgentEditorDraft(null);
    setToast("Agent updated");
  }

  async function handleDeleteAgent(agent: Agent) {
    if (!agent.is_custom) {
      return;
    }
    await deleteAgent(agent.id);
    setAgents((current) => current.filter((item) => item.id !== agent.id));
    setConversations((current) =>
      current.map((conversation) => ({
        ...conversation,
        agent_ids: conversation.agent_ids.filter((agentId) => agentId !== agent.id),
      })),
    );
    if (editingAgentId === agent.id) {
      setEditingAgentId("");
      setAgentEditorDraft(null);
    }
    setToast("Agent deleted");
  }

  function openCodeEditor(artifact: Artifact) {
    setEditArtifact(artifact);
    setEditDraft(artifact.content ?? "");
  }

  function openArtifactPreview(artifact: Artifact) {
    setPreviewArtifact(artifact);
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
    setToast("产物已保存，版本已记录");
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
    <main className={`app-shell ${rightPanelOpen ? "with-right-panel" : "right-panel-collapsed"} ${leftSidebarOpen ? "" : "left-pane-collapsed"}`} style={shellStyle}>
      <aside className="conversation-pane">
        <section className="brand">
          <div>
            <strong>AgentHub</strong>
            <span>{labels.appTagline}</span>
          </div>
          <button type="button" onClick={openCreatePanel}>{labels.new}</button>
        </section>

        <section className="status-row">
          <span className={`status-chip ${runningConversationCount ? "running" : ""}`}>
            {runningConversationCount ? `${labels.running} ${runningConversationCount}` : labels.ready}
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
                  openConversation(conversation.id);
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
                      {runtimeByConversation[conversation.id]?.isSending ? <span>{labels.running}</span> : null}
                      {conversation.is_pinned ? (
                        <span
                          aria-label={labels.pin}
                          className="conversation-pin-indicator"
                          title={labels.pin}
                        />
                      ) : null}
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
            <span
              aria-hidden="true"
              className="trash-button-icon"
            />
            <span className="trash-button-label">{labels.trash}</span>
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
        <nav className="conversation-tabs" aria-label="Open conversations">
          {openConversationIds.map((conversationId) => {
            const conversation = conversations.find((item) => item.id === conversationId);
            if (!conversation) {
              return null;
            }
            return (
              <div className={conversationId === activeConversationId ? "active" : ""} key={conversationId}>
                <button type="button" onClick={() => openConversation(conversationId)}>
                  {runtimeByConversation[conversationId]?.isSending ? "● " : ""}
                  {conversation.title}
                </button>
                <button aria-label={`Close ${conversation.title}`} type="button" onClick={() => closeConversationTab(conversationId)}>×</button>
              </div>
            );
          })}
        </nav>
        <header className="chat-header">
          <button
            className="header-icon-button"
            type="button"
            aria-label={leftSidebarOpen ? "收起左栏" : "展开左栏"}
            onClick={() => setLeftSidebarOpen((current) => !current)}
          >
            {leftSidebarOpen ? "‹" : "›"}
          </button>
          <div className="chat-header-title">
            <h1>{activeConversation?.title ?? labels.emptyTitle}</h1>
          </div>
          <div className="header-actions">
            <button
              className="header-icon-button"
              type="button"
              aria-label="Agent 管理"
              title="Agent 管理"
              onClick={() => {
                setRightTab("agents");
                setRightPanelOpen(true);
              }}
            >
              ⌘
            </button>
            <button
              className="header-icon-button"
              type="button"
              aria-label="上下文/调试"
              title="上下文/调试"
              onClick={() => {
                setRightTab("context");
                setRightPanelOpen(true);
              }}
            >
              ⊞
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
                artifactMap={artifactMap}
                key={message.id}
                labels={labels}
                message={message}
                onExtractMemory={() => handleExtractMemory(message)}
                onApply={handleApplyDiff}
                onPin={() => handleMessagePin(message)}
                onQuote={() => {
                  setQuotedMessage(message);
                  setQuotedText("");
                }}
                onQuoteSelected={(text) => {
                  setQuotedMessage(message);
                  setQuotedText(text);
                }}
                onEdit={openCodeEditor}
                onRegenerate={() => handleRegenerate(message)}
                onPreview={openArtifactPreview}
                onRun={handleRunWorkflow}
                onRestoreVersion={handleRestoreArtifactVersion}
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
              startedAt={activeRuntime.thinkingStartedAt}
              toolPreferences={toolPreferences}
            />
          ) : null}
          {!isSending && progressSteps.some((step) => step.status === "error") ? <ProgressPanel steps={progressSteps} /> : null}
        </section>

        <AgentRow
          activeConversation={activeConversation}
          agentMode={agentMode}
          agents={agents}
          draftAgentIds={draftAgentIds}
          expanded={agentRowExpanded}
          isSending={isSending}
          models={models}
          selectedAgentIds={selectedAgentIds}
          selectedModelId={selectedModelId}
          toolPreferences={toolPreferences}
          onChangeMode={handleChangeMode}
          onClearAgent={(agentId) => handleToggleAgentForActiveConversation(agentId)}
          onSelectAgent={(agentId) => handleToggleAgentForActiveConversation(agentId)}
          onSetModel={setSelectedModelId}
          onToggleTool={(key) =>
            setToolPreferences((current) => ({
              ...current,
              [key]: !current[key],
            }))
          }
          onToggleExpanded={() => setAgentRowExpanded((current) => !current)}
        />

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
            <div className="composer-actions">
              <button
                className={`send-button ${isSending ? "sending" : ""}`}
                disabled={!activeConversation || (!isSending && !input.trim())}
                type={isSending ? "button" : "submit"}
                onClick={isSending && activeConversation ? () => cancelInFlight(activeConversation.id) : undefined}
              >
                {isSending ? "停止" : labels.send}
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
          {visibleRightTabs.map((tab) => (
            <button className={rightTab === tab ? "active" : ""} key={tab} type="button" onClick={() => setRightTab(tab)}>
              {rightTabLabel(tab)}
            </button>
          ))}
        </div>
        <RightPanelContent
          activeConversation={activeConversation}
          agents={agents}
          artifacts={visibleArtifacts}
          attachments={attachments}
          labels={labels}
          onApply={handleApplyDiff}
          onCreateAgent={handleCreateAgent}
          onEdit={openCodeEditor}
          onPreview={openArtifactPreview}
          onRun={handleRunWorkflow}
          onRestoreVersion={handleRestoreArtifactVersion}
          onClosePreview={() => setPreviewArtifact(null)}
          onToast={setToast}
          agentDraft={agentDraft}
          agentEditorDraft={agentEditorDraft}
          editingAgentId={editingAgentId}
          models={models}
          onDeleteAgent={handleDeleteAgent}
          setAgentDraft={setAgentDraft}
          setAgentEditorDraft={setAgentEditorDraft}
          onEditAgent={beginEditAgent}
          onSaveAgent={handleSaveAgent}
          pinnedMessages={pinnedMessages}
          memories={activeDetail.memories}
          onDeleteMemory={handleDeleteMemory}
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
      {previewArtifact ? (
        <div className="preview-modal preview-modal--fullscreen" role="dialog" aria-modal="true">
          <div className="preview-card preview-card--fullscreen">
            <ArtifactPreviewPanel artifact={previewArtifact} labels={labels} onClose={() => setPreviewArtifact(null)} />
          </div>
        </div>
      ) : null}
      <ToastStack toasts={toasts} onDismiss={(id) => setToasts((current) => current.filter((entry) => entry.id !== id))} />
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
  artifactMap,
  labels: t,
  message,
  onApply,
  onExtractMemory,
  onEdit,
  onPin,
  onQuote,
  onQuoteSelected,
  onRegenerate,
  onPreview,
  onRestoreVersion,
  onRun,
  regenerating,
  onToast,
}: {
  attachmentMap: Map<string, Attachment>;
  artifactMap: Map<string, Artifact>;
  labels: typeof labels;
  message: ChatMessage;
  onApply: (artifact: Artifact) => void;
  onExtractMemory: () => void;
  onEdit: (artifact: Artifact) => void;
  onPin: () => void;
  onQuote: () => void;
  onQuoteSelected: (text: string) => void;
  onRegenerate: () => void;
  onPreview: (artifact: Artifact) => void;
  onRestoreVersion: (artifact: Artifact, versionId: string) => void;
  onRun: (artifact: Artifact) => void;
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
            <button type="button" onClick={onExtractMemory}>智能记忆</button>
          </div>
        </header>
        {message.quoted_message_id || message.quoted_text ? <small className="quoted-line">{t.quoted}: {message.quoted_text || message.quoted_message_id}</small> : null}
        {message.generation_index && message.generation_index > 1 ? (
          <small className="quoted-line">版本 {message.generation_index}{message.is_active_generation === false ? "（旧版）" : ""}</small>
        ) : null}
        <MarkdownMessage content={message.content} copyLabel={t.copy} copiedLabel={t.copied} onToast={onToast} />
        {messageAttachments.length ? <AttachmentList attachments={messageAttachments} /> : null}
        {message.role === "agent" ? (
          <InlineArtifactList
            artifactIds={message.artifact_ids ?? []}
            artifactMap={artifactMap}
            labels={t}
            onApply={onApply}
            onEdit={onEdit}
            onPreview={onPreview}
            onRestoreVersion={onRestoreVersion}
            onRun={onRun}
            onToast={onToast}
          />
        ) : null}
        {message.role === "user" ? (
          <div className="message-regenerate-row">
            <button type="button" onClick={onRegenerate} disabled={regenerating}>
              {t.regenerate}
            </button>
          </div>
        ) : null}
        {message.role === "agent" ? (
          <ThinkingSummary
            events={message.trace_events ?? []}
            label={t.thinking}
            sender={sender}
            content={message.content}
          />
        ) : null}
      </div>
    </article>
  );
}

function InlineArtifactList({
  artifactIds,
  artifactMap,
  labels: t,
  onApply,
  onEdit,
  onPreview,
  onRestoreVersion,
  onRun,
  onToast,
}: {
  artifactIds: string[];
  artifactMap: Map<string, Artifact>;
  labels: typeof labels;
  onApply: (artifact: Artifact) => void;
  onEdit: (artifact: Artifact) => void;
  onPreview: (artifact: Artifact) => void;
  onRestoreVersion: (artifact: Artifact, versionId: string) => void;
  onRun: (artifact: Artifact) => void;
  onToast: (message: string) => void;
}) {
  const artifacts = artifactIds
    .map((artifactId) => artifactMap.get(artifactId))
    .filter((artifact): artifact is Artifact => Boolean(artifact));

  if (!artifacts.length) {
    return null;
  }

  return (
    <div className="inline-artifact-list">
      {artifacts.map((artifact) => (
        <InlineArtifactCard
          artifact={artifact}
          key={artifact.id}
          labels={t}
          onApply={() => onApply(artifact)}
          onEdit={() => onEdit(artifact)}
          onPreview={() => onPreview(artifact)}
          onRestoreVersion={(versionId) => onRestoreVersion(artifact, versionId)}
          onRun={() => onRun(artifact)}
          onToast={onToast}
        />
      ))}
    </div>
  );
}

function InlineArtifactCard({
  artifact,
  labels: t,
  onApply,
  onEdit,
  onPreview,
  onRestoreVersion,
  onRun,
  onToast,
}: {
  artifact: Artifact;
  labels: typeof labels;
  onApply: () => void;
  onEdit: () => void;
  onPreview: () => void;
  onRestoreVersion: (versionId: string) => void;
  onRun: () => void;
  onToast: (message: string) => void;
}) {
  const [diff, setDiff] = useState<StructuredDiff | null>(null);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const showPreviewButton = artifact.type === "code" || artifact.type === "workflow" || Boolean(artifact.preview_url);

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
    <article className={`inline-artifact ${artifact.type}`}>
      <header>
        <div>
          <span>{artifact.type}</span>
          <strong>{artifact.title}</strong>
        </div>
        <div className="inline-artifact-meta">
          {artifact.render_mode ? <small>{artifact.render_mode}</small> : null}
          {artifact.source_artifact_id ? <small>derived from {artifact.source_artifact_id}</small> : null}
        </div>
      </header>
      {artifact.type === "code" ? (
        <pre><code>{artifact.content ?? ""}</code></pre>
      ) : null}
      {artifact.type === "preview" ? (
        <div className="inline-artifact-body">
          <p>{artifact.content ?? "Preview artifact."}</p>
          {artifact.preview_url ? (
            <button type="button" onClick={onPreview}>{t.preview}</button>
          ) : null}
        </div>
      ) : null}
      {artifact.type === "deployment" ? (
        <div className="inline-artifact-body">
          <p>{artifact.logs ?? artifact.content}</p>
          {artifact.preview_url ? <a href={`${API_ORIGIN}${artifact.preview_url}`} target="_blank" rel="noreferrer">{t.deployOpen}</a> : null}
        </div>
      ) : null}
      {artifact.type === "workflow" ? (
        <div className="inline-artifact-body">
          <p>{artifact.content ? "Workflow definition ready to run." : "Workflow artifact."}</p>
          <div className="inline-actions">
            <button type="button" onClick={onRun}>{t.runWorkflow}</button>
            {artifact.content ? <button type="button" onClick={onEdit}>{t.edit}</button> : null}
          </div>
        </div>
      ) : null}
      {artifact.type === "diff" ? (
        <div className="inline-artifact-body">
          {diff ? <DiffViewer diff={diff} /> : <pre><code>{artifact.content ?? ""}</code></pre>}
          <div className="inline-actions">
            <button type="button" onClick={handleToggleDiff}>{diff ? t.close : t.viewDiff}</button>
            <button type="button" onClick={onApply} disabled={artifact.status === "applied"}>{artifact.status === "applied" ? t.applied : t.applyDiff}</button>
          </div>
        </div>
      ) : null}
      {artifact.type === "conflict" ? (
        <div className="inline-artifact-body">
          <p>{artifact.content}</p>
          {artifact.conflict_candidates?.length ? (
            <div className="conflict-candidate-list">
              {artifact.conflict_candidates.map((candidate) => (
                <article key={candidate.artifact_id}>
                  <strong>{candidate.title}</strong>
                  <small>{candidate.producer_agent_id}</small>
                  <pre><code>{candidate.content_preview}</code></pre>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {(artifact.type === "document_preview" || artifact.type === "presentation_preview") ? (
        <div className="inline-artifact-body">
          <p>{artifact.content}</p>
          {artifact.preview_url ? <a href={`${API_ORIGIN}${artifact.preview_url}`} target="_blank" rel="noreferrer">{t.preview}</a> : null}
        </div>
      ) : null}
      {artifact.content && artifact.type !== "code" ? (
        <small className="artifact-meta">
          {artifact.language ?? artifact.type} 路 {artifact.file_path ?? artifact.id}
        </small>
      ) : null}
      {versions.length ? (
        <div className="inline-version-list">
          {versions.map((version) => (
            <button key={version.id} type="button" onClick={() => onRestoreVersion(version.id)}>
              {t.restore} {version.reason}
            </button>
          ))}
        </div>
      ) : null}
      <footer>
        {artifact.content ? <button type="button" onClick={handleCopy}>{t.copy}</button> : null}
        {artifact.content ? <button type="button" onClick={handleToggleVersions}>{t.versions}</button> : null}
        {showPreviewButton ? <button type="button" onClick={onPreview}>{t.preview}</button> : null}
      </footer>
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
  const hasEvents = events.length > 0;
  const steps = hasEvents ? [] : buildThinkingSummary(sender, content);
  const duration = traceDuration(events);
  const stepCount = events.length || steps.length;
  if (!hasEvents && !steps.length) {
    return null;
  }
  return (
    <details className="thinking-summary">
      <summary>
        <span className="thinking-summary-icon" aria-hidden="true">⌛</span>
        <span className="thinking-summary-text">
          {duration ? `已思考 ${duration}` : label}
          {stepCount ? ` · ${stepCount} 步` : ""}
        </span>
        <span className="thinking-summary-toggle" aria-hidden="true">展开</span>
      </summary>
      {hasEvents ? (
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
  startedAt,
  toolPreferences,
}: {
  agentIds: string[];
  agentMode: "single" | "multi";
  attachmentCount: number;
  modelId: string;
  startedAt: number | null;
  toolPreferences: ToolPreferences;
}) {
  const selectedAgents = agentIds.length ? agentIds.map((agentId) => displayAgentName(agentId)).join("、") : "智能体（Agent）";
  const primaryAgentId = agentIds[0] ?? "orchestrator";
  const enabledTools = (Object.keys(toolPreferences) as Array<keyof ToolPreferences>)
    .filter((key) => toolPreferences[key])
    .map(toolLabel);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!startedAt) {
      return;
    }
    setNow(Date.now());
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const elapsedSeconds = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0;

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
  agentEditorDraft,
  agents,
  artifacts,
  attachments,
  labels: t,
  memories,
  onApply,
  onClosePreview,
  onCreateAgent,
  onDeleteAgent,
  onDeleteMemory,
  onEditAgent,
  onEdit,
  onPreview,
  onRun,
  onRestoreVersion,
  onSaveAgent,
  onToast,
  pinnedMessages,
  previewArtifact,
  selectedAgentIds,
  tab,
  editingAgentId,
  models,
  tools,
  setAgentDraft,
  setAgentEditorDraft,
}: {
  activeConversation?: Conversation;
  agentDraft: AgentCreateInput;
  agentEditorDraft: AgentCreateInput | null;
  agents: Agent[];
  artifacts: Artifact[];
  attachments: Attachment[];
  labels: typeof labels;
  memories: ConversationMemory[];
  onApply: (artifact: Artifact) => void;
  onClosePreview: () => void;
  onCreateAgent: (event: FormEvent) => void;
  onDeleteAgent: (agent: Agent) => void;
  onDeleteMemory: (memoryId: string) => void;
  onEditAgent: (agent: Agent) => void;
  onEdit: (artifact: Artifact) => void;
  onPreview: (artifact: Artifact) => void;
  onRun: (artifact: Artifact) => void;
  onRestoreVersion: (artifact: Artifact, versionId: string) => void;
  onSaveAgent: (event: FormEvent) => void;
  onToast: (message: string) => void;
  pinnedMessages: ChatMessage[];
  previewArtifact: Artifact | null;
  selectedAgentIds: string[];
  tab: RightPanelTab;
  editingAgentId: string;
  models: ModelOption[];
  tools: ToolOption[];
  setAgentDraft: Dispatch<SetStateAction<AgentCreateInput>>;
  setAgentEditorDraft: Dispatch<SetStateAction<AgentCreateInput | null>>;
}) {
  if (tab === "agents") {
    const selected = agents;
    return (
      <div className="right-content">
        <form className="side-card agent-create-form" onSubmit={onCreateAgent}>
          <div className="agent-form-title">
            <AvatarBadge value="custom_agent" className="agent-form-avatar" />
            <div>
              <strong>创建智能体（Agent）</strong>
              <small>Create a custom agent with tools and skills.</small>
            </div>
          </div>
          <label className="agent-form-field">
            <span>智能体名称（Agent name）</span>
            <input
              value={agentDraft.name ?? ""}
              onChange={(event) => setAgentDraft((current) => ({ ...current, name: event.target.value }))}
              placeholder="例如：数据分析智能体（Data Analyst）"
            />
          </label>
          <label className="agent-form-field">
            <span>职责描述（Description）</span>
            <input
              value={agentDraft.description ?? ""}
              onChange={(event) => setAgentDraft((current) => ({ ...current, description: event.target.value }))}
              placeholder="说明这个智能体负责什么任务"
            />
          </label>
          <label className="agent-form-field">
            <span>系统提示词（System Prompt）</span>
            <textarea
              value={agentDraft.system_prompt ?? ""}
              onChange={(event) => setAgentDraft((current) => ({ ...current, system_prompt: event.target.value }))}
              placeholder="定义角色、边界、输出格式和工作约束"
            />
          </label>
          <span className="agent-form-label">可用工具（Available tools）</span>
          <label className="agent-form-field">
            <span>Avatar</span>
            <input
              value={agentDraft.avatar ?? ""}
              onChange={(event) => setAgentDraft((current) => ({ ...current, avatar: event.target.value }))}
              placeholder="AG"
            />
          </label>
          <label className="agent-form-field">
            <span>Model provider</span>
            <select
              value={agentDraft.model_provider ?? "auto"}
              onChange={(event) => setAgentDraft((current) => ({ ...current, model_provider: event.target.value || undefined }))}
            >
              <option value="auto">Auto</option>
              {models.map((model) => (
                <option key={model.id} value={model.id}>{model.name}</option>
              ))}
            </select>
          </label>
          <label className="agent-form-field">
            <span>Model name</span>
            <input
              value={agentDraft.model_name ?? ""}
              onChange={(event) => setAgentDraft((current) => ({ ...current, model_name: event.target.value }))}
              placeholder="Optional model override"
            />
          </label>
          <div className="agent-picker">
            {tools.map((tool) => (
              <label className="tool-choice" key={tool.id}>
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
                <span>
                  {tool.name ?? tool.id}
                  <small>{tool.id}</small>
                </span>
              </label>
            ))}
          </div>
          <button type="submit">创建智能体（Agent）</button>
        </form>
        {editingAgentId && agentEditorDraft ? (
          <form className="side-card agent-create-form" onSubmit={onSaveAgent}>
            <div className="agent-form-title">
              <AvatarBadge value={agentEditorDraft.avatar ?? editingAgentId} className="agent-form-avatar" />
              <div>
                <strong>Edit Agent</strong>
                <small>Update the selected custom agent.</small>
              </div>
            </div>
            <label className="agent-form-field">
              <span>Name</span>
              <input
                value={agentEditorDraft.name ?? ""}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), name: event.target.value }))}
              />
            </label>
            <label className="agent-form-field">
              <span>Description</span>
              <input
                value={agentEditorDraft.description ?? ""}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), description: event.target.value }))}
              />
            </label>
            <label className="agent-form-field">
              <span>System Prompt</span>
              <textarea
                value={agentEditorDraft.system_prompt ?? ""}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), system_prompt: event.target.value }))}
              />
            </label>
            <label className="agent-form-field">
              <span>Avatar</span>
              <input
                value={agentEditorDraft.avatar ?? ""}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), avatar: event.target.value }))}
              />
            </label>
            <label className="agent-form-field">
              <span>Model provider</span>
              <select
                value={agentEditorDraft.model_provider ?? "auto"}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), model_provider: event.target.value || undefined }))}
              >
                <option value="auto">Auto</option>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>{model.name}</option>
                ))}
              </select>
            </label>
            <label className="agent-form-field">
              <span>Model name</span>
              <input
                value={agentEditorDraft.model_name ?? ""}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), model_name: event.target.value }))}
              />
            </label>
            <label className="agent-form-field">
              <span>Capabilities</span>
              <input
                value={(agentEditorDraft.capabilities ?? []).join(", ")}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), capabilities: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) }))}
              />
            </label>
            <label className="agent-form-field">
              <span>Tools</span>
              <input
                value={(agentEditorDraft.tools ?? []).join(", ")}
                onChange={(event) => setAgentEditorDraft((current) => ({ ...(current ?? {}), tools: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) }))}
              />
            </label>
            <div className="inline-actions">
              <button type="submit">Save</button>
              <button type="button" onClick={() => setAgentEditorDraft(null)}>Cancel</button>
            </div>
          </form>
        ) : null}
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
            {agent.is_custom ? (
              <div className="inline-actions">
                <button type="button" onClick={() => onEditAgent(agent)}>Edit</button>
                <button type="button" onClick={() => onDeleteAgent(agent)}>Delete</button>
              </div>
            ) : null}
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
        <section className="side-card">
          <strong>Tools module hidden</strong>
          <p>工具能力仍可被智能体调用，但不再作为独立右侧模块展示。</p>
        </section>
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
          <strong>LLM 智能记忆</strong>
          {memories.length ? memories.map((memory) => (
            <div className="memory-item" key={memory.id}>
              <small>{memory.category} · {Math.round(memory.confidence * 100)}%</small>
              <p>{memory.content}</p>
              <button type="button" onClick={() => onDeleteMemory(memory.id)}>删除</button>
            </div>
          )) : <p>暂无 LLM 提取的长期记忆</p>}
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
          <ArtifactCard
            artifact={artifact}
            key={artifact.id}
            labels={t}
            onApply={() => onApply(artifact)}
            onEdit={() => onEdit(artifact)}
            onPreview={() => onPreview(artifact)}
            onRun={() => onRun(artifact)}
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
  onRun,
  onRestoreVersion,
  onToast,
}: {
  artifact: Artifact;
  labels: typeof labels;
  onApply: () => void;
  onEdit: () => void;
  onPreview: () => void;
  onRun: () => void;
  onRestoreVersion: (versionId: string) => void;
  onToast: (message: string) => void;
}) {
  const [diff, setDiff] = useState<StructuredDiff | null>(null);
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const workflow = artifact.type === "workflow" ? parseWorkflowArtifact(artifact) : null;
  const showPreviewButton = artifact.type === "code" || artifact.type === "workflow" || Boolean(artifact.preview_url);

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
      {artifact.type === "workflow" ? (
        <div className="workflow-card">
          <p>{workflow?.description ?? "Editable workflow definition."}</p>
          <div className="workflow-stats">
            <span>{workflow?.nodes.length ?? 0} 个节点</span>
            <span>{workflow ? workflowNodeKinds(workflow.nodes).join(" / ") : "JSON"}</span>
          </div>
        </div>
      ) : null}
      {artifact.type === "conflict" ? (
        <div className="conflict-card">
          <p>{artifact.content}</p>
          {artifact.conflict_candidates?.length ? (
            <div className="conflict-candidate-list">
              {artifact.conflict_candidates.map((candidate) => (
                <article key={candidate.artifact_id}>
                  <strong>{candidate.title}</strong>
                  <small>{candidate.producer_agent_id}</small>
                  <pre><code>{candidate.content_preview}</code></pre>
                </article>
              ))}
            </div>
          ) : null}
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
        {artifact.type === "code" || artifact.type === "workflow" ? <button type="button" onClick={onEdit}>{t.edit}</button> : null}
        {artifact.content ? <button type="button" onClick={handleToggleVersions}>{t.versions}</button> : null}
        {artifact.type === "diff" ? <button type="button" onClick={handleToggleDiff}>{t.viewDiff}</button> : null}
        {showPreviewButton ? <button type="button" onClick={onPreview}>{t.preview}</button> : null}
        {artifact.type === "workflow" ? <button type="button" onClick={onRun}>{t.runWorkflow}</button> : null}
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
      {artifact.type === "workflow" ? (
        <WorkflowPreview artifact={artifact} />
      ) : inlineHtml ? (
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

function WorkflowPreview({ artifact }: { artifact: Artifact }) {
  const workflow = parseWorkflowArtifact(artifact);
  if (!workflow) {
    return (
      <div className="artifact-preview-empty">
        <strong>Workflow JSON 无法解析</strong>
        <p>请先修复这个 workflow artifact 的 JSON 内容，再重新预览或运行。</p>
      </div>
    );
  }
  return (
    <div className="workflow-preview">
      <section className="workflow-summary">
        <strong>{workflow.title}</strong>
        <p>{workflow.description || "Editable workflow definition."}</p>
        <div className="workflow-stats">
          <span>{workflow.nodes.length} 个节点</span>
          <span>版本 {workflow.version}</span>
          <span>{workflow.kind}</span>
        </div>
      </section>
      <section className="workflow-node-list">
        {workflow.nodes.map((node) => (
          <article className="workflow-node" key={node.id}>
            <header>
              <strong>{node.label || node.id}</strong>
              <span>{node.type}</span>
            </header>
            <p>{node.task || node.prompt || "No task configured."}</p>
            <small>
              {node.type === "tool"
                ? `Tool: ${node.tool_id || "unknown"}`
                : `Agent: ${node.agent_id || "orchestrator"}`}
            </small>
            {node.depends_on.length ? (
              <small>Depends on: {node.depends_on.join(", ")}</small>
            ) : (
              <small>Depends on: none</small>
            )}
            {node.tools.length ? <small>Tools: {node.tools.join(", ")}</small> : null}
          </article>
        ))}
      </section>
    </div>
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

type WorkflowNode = {
  id: string;
  type: string;
  label?: string;
  agent_id?: string;
  tool_id?: string;
  task?: string;
  prompt?: string;
  tools: string[];
  depends_on: string[];
};

type WorkflowDefinition = {
  version: number;
  kind: string;
  title: string;
  description?: string;
  source_prompt?: string;
  nodes: WorkflowNode[];
};

function parseWorkflowArtifact(artifact: Artifact): WorkflowDefinition | null {
  if (artifact.type !== "workflow" || !artifact.content) {
    return null;
  }
  try {
    const parsed = JSON.parse(stripJsonFence(artifact.content)) as Record<string, unknown>;
    const nodes = Array.isArray(parsed.nodes)
      ? parsed.nodes.map((node) => normalizeWorkflowNode(node)).filter(Boolean) as WorkflowNode[]
      : [];
    return {
      version: Number(parsed.version ?? 1),
      kind: String(parsed.kind ?? "agenthub.workflow"),
      title: String(parsed.title ?? artifact.title),
      description: parsed.description ? String(parsed.description) : undefined,
      source_prompt: parsed.source_prompt ? String(parsed.source_prompt) : undefined,
      nodes,
    };
  } catch {
    return null;
  }
}

function normalizeWorkflowNode(node: unknown): WorkflowNode | null {
  if (!node || typeof node !== "object") {
    return null;
  }
  const value = node as Record<string, unknown>;
  const id = String(value.id ?? "").trim();
  if (!id) {
    return null;
  }
  return {
    id,
    type: String(value.type ?? "agent"),
    label: value.label ? String(value.label) : undefined,
    agent_id: value.agent_id ? String(value.agent_id) : undefined,
    tool_id: value.tool_id ? String(value.tool_id) : undefined,
    task: value.task ? String(value.task) : undefined,
    prompt: value.prompt ? String(value.prompt) : undefined,
    tools: toStringList(value.tools),
    depends_on: toStringList(value.depends_on),
  };
}

function stripJsonFence(content: string): string {
  const trimmed = content.trim();
  if (!trimmed.startsWith("```")) {
    return trimmed;
  }
  return trimmed
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

function workflowNodeKinds(nodes: WorkflowNode[]): string[] {
  const unique = new Set(nodes.map((node) => node.type).filter(Boolean));
  return [...unique];
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
  const [reviewedHunks, setReviewedHunks] = useState<Set<string>>(new Set());

  function toggleHunkReview(hunkKey: string) {
    setReviewedHunks((current) => {
      const next = new Set(current);
      if (next.has(hunkKey)) {
        next.delete(hunkKey);
      } else {
        next.add(hunkKey);
      }
      return next;
    });
  }

  return (
    <div className="diff-viewer split">
      {diff.files.map((file) => (
        <section key={`${file.old_path}-${file.new_path}`}>
          <header>
            <strong>{file.old_path}</strong>
            <strong>{file.new_path}</strong>
          </header>
          {file.hunks.map((hunk) => {
            const hunkKey = `${file.old_path}-${file.new_path}-${hunk.header}`;
            const reviewed = reviewedHunks.has(hunkKey);
            return (
            <div className={`diff-hunk ${reviewed ? "reviewed" : ""}`} key={hunk.header}>
              <div className="diff-hunk-header">
                <small>{hunk.header}</small>
                <button type="button" onClick={() => toggleHunkReview(hunkKey)}>
                  {reviewed ? "Reviewed" : "Confirm hunk"}
                </button>
              </div>
              {splitDiffRows(hunk.lines).map((row, index) => (
                <div className="diff-split-row" key={`${hunk.header}-${index}`}>
                  <div className={`diff-split-cell ${row.old?.type ?? "empty"}`}>
                    <span>{row.old?.old_no ?? ""}</span>
                    <code>{row.old ? `${row.old.type === "remove" ? "-" : " "}${row.old.content}` : ""}</code>
                  </div>
                  <div className={`diff-split-cell ${row.next?.type ?? "empty"}`}>
                    <span>{row.next?.new_no ?? ""}</span>
                    <code>{row.next ? `${row.next.type === "add" ? "+" : " "}${row.next.content}` : ""}</code>
                  </div>
                </div>
              ))}
            </div>
          );
          })}
        </section>
      ))}
    </div>
  );
}

function splitDiffRows(lines: StructuredDiffLine[]): Array<{ old?: StructuredDiffLine; next?: StructuredDiffLine }> {
  const rows: Array<{ old?: StructuredDiffLine; next?: StructuredDiffLine }> = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const nextLine = lines[index + 1];
    if (line.type === "remove" && nextLine?.type === "add") {
      rows.push({ old: line, next: nextLine });
      index += 2;
      continue;
    }
    if (line.type === "remove") {
      rows.push({ old: line });
    } else if (line.type === "add") {
      rows.push({ next: line });
    } else {
      rows.push({ old: line, next: line });
    }
    index += 1;
  }
  return rows;
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
  const lines = content.split("\n");
  const nodes: ReactNode[] = [];
  let paragraphLines: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let listItems: string[] = [];

  const flushParagraph = () => {
    if (!paragraphLines.length) {
      return;
    }
    const paragraph = paragraphLines.join(" ").trim();
    if (paragraph) {
      nodes.push(
        <p key={`text-${key}-p-${nodes.length}`}>
          {renderInlineMarkdown(paragraph, `text-${key}-p-${nodes.length}`)}
        </p>,
      );
    }
    paragraphLines = [];
  };

  const flushList = () => {
    if (!listType || !listItems.length) {
      listType = null;
      listItems = [];
      return;
    }
    const listKey = `text-${key}-${listType}-${nodes.length}`;
    const items = listItems.map((item, index) => (
      <li key={`${listKey}-${index}`}>
        {renderInlineMarkdown(item, `${listKey}-${index}`)}
      </li>
    ));
    nodes.push(listType === "ul" ? <ul key={listKey}>{items}</ul> : <ol key={listKey}>{items}</ol>);
    listType = null;
    listItems = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = Math.min(4, headingMatch[1].length);
      const title = headingMatch[2].trim();
      if (level === 1) {
        nodes.push(<h1 key={`text-${key}-h1-${nodes.length}`}>{renderInlineMarkdown(title, `text-${key}-h1-${nodes.length}`)}</h1>);
      } else if (level === 2) {
        nodes.push(<h2 key={`text-${key}-h2-${nodes.length}`}>{renderInlineMarkdown(title, `text-${key}-h2-${nodes.length}`)}</h2>);
      } else if (level === 3) {
        nodes.push(<h3 key={`text-${key}-h3-${nodes.length}`}>{renderInlineMarkdown(title, `text-${key}-h3-${nodes.length}`)}</h3>);
      } else {
        nodes.push(<h4 key={`text-${key}-h4-${nodes.length}`}>{renderInlineMarkdown(title, `text-${key}-h4-${nodes.length}`)}</h4>);
      }
      continue;
    }

    if (/^(?:[-*_]\s*){3,}$/.test(trimmed)) {
      flushParagraph();
      flushList();
      nodes.push(<hr key={`text-${key}-hr-${nodes.length}`} />);
      continue;
    }

    const quoteMatch = trimmed.match(/^>\s?(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      nodes.push(
        <blockquote key={`text-${key}-quote-${nodes.length}`}>
          {renderInlineMarkdown(quoteMatch[1], `text-${key}-quote-${nodes.length}`)}
        </blockquote>,
      );
      continue;
    }

    const unorderedMatch = trimmed.match(/^[-*+]\s+(.+)$/);
    if (unorderedMatch) {
      flushParagraph();
      if (listType && listType !== "ul") {
        flushList();
      }
      listType = "ul";
      listItems.push(unorderedMatch[1].trim());
      continue;
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType && listType !== "ol") {
        flushList();
      }
      listType = "ol";
      listItems.push(orderedMatch[1].trim());
      continue;
    }

    flushList();
    paragraphLines.push(trimmed);
  }

  flushParagraph();
  flushList();

  return nodes.length ? nodes : <p key={`text-${key}-empty`}>{content}</p>;
}

function renderInlineMarkdown(content: string, keyPrefix: string): ReactNode[] {
  const match = findNextInlineMarkdown(content);
  if (!match) {
    return [content];
  }

  const before = content.slice(0, match.index);
  const after = content.slice(match.index + match.raw.length);
  const nodes: ReactNode[] = [];

  if (before) {
    nodes.push(before);
  }

  if (match.kind === "link") {
    nodes.push(
      <a href={match.value} key={`${keyPrefix}-link-${match.index}`} rel="noreferrer" target="_blank">
        {renderInlineMarkdown(match.label, `${keyPrefix}-link-${match.index}`)}
      </a>,
    );
  }
  if (match.kind === "code") {
    nodes.push(<code key={`${keyPrefix}-code-${match.index}`}>{match.value}</code>);
  }
  if (match.kind === "strong_em") {
    nodes.push(
      <strong key={`${keyPrefix}-strong-em-${match.index}`}>
        <em>{renderInlineMarkdown(match.value, `${keyPrefix}-strong-em-${match.index}`)}</em>
      </strong>,
    );
  }
  if (match.kind === "strong") {
    nodes.push(
      <strong key={`${keyPrefix}-strong-${match.index}`}>
        {renderInlineMarkdown(match.value, `${keyPrefix}-strong-${match.index}`)}
      </strong>,
    );
  }
  if (match.kind === "em") {
    nodes.push(
      <em key={`${keyPrefix}-em-${match.index}`}>
        {renderInlineMarkdown(match.value, `${keyPrefix}-em-${match.index}`)}
      </em>,
    );
  }

  if (after) {
    nodes.push(...renderInlineMarkdown(after, `${keyPrefix}-tail-${match.index}`));
  }

  return nodes;
}

function findNextInlineMarkdown(content: string): {
  index: number;
  raw: string;
  kind: "link" | "code" | "strong_em" | "strong" | "em";
  label: string;
  value: string;
} | null {
  const patterns = [
    { kind: "link" as const, regex: /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/ },
    { kind: "code" as const, regex: /`([^`]+)`/ },
    { kind: "strong_em" as const, regex: /\*\*\*([^*]+)\*\*\*/ },
    { kind: "strong" as const, regex: /\*\*([^*]+)\*\*/ },
    { kind: "em" as const, regex: /\*([^*]+)\*/ },
  ];

  let bestMatch: {
    index: number;
    raw: string;
    kind: "link" | "code" | "strong_em" | "strong" | "em";
    label: string;
    value: string;
  } | null = null;

  for (const pattern of patterns) {
    const result = pattern.regex.exec(content);
    if (!result) {
      continue;
    }
    if (!bestMatch || result.index < bestMatch.index) {
      bestMatch = {
        index: result.index,
        raw: result[0],
        kind: pattern.kind,
        label: result[1] ?? "",
        value: pattern.kind === "link" ? (result[2] ?? "") : (result[1] ?? ""),
      };
    }
  }

  return bestMatch;
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

function latestVisibleArtifacts(artifacts: Artifact[]): Artifact[] {
  const preferredTypes: Artifact["type"][] = [
    "workflow",
    "preview",
    "code",
    "diff",
    "conflict",
    "deployment",
    "document_preview",
    "presentation_preview",
    "review",
  ];
  const selectedIds = new Set<string>();
  for (const type of preferredTypes) {
    const latest = [...artifacts].reverse().find((artifact) => artifact.type === type);
    if (latest) {
      selectedIds.add(latest.id);
    }
  }
  const visible = artifacts.filter((artifact) => selectedIds.has(artifact.id));
  if (visible.length) {
    return visible;
  }
  const latest = artifacts[artifacts.length - 1];
  return latest ? [latest] : [];
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

function AgentRow({
  activeConversation,
  agentMode,
  agents,
  draftAgentIds,
  expanded,
  isSending,
  models,
  selectedAgentIds,
  selectedModelId,
  toolPreferences,
  onChangeMode,
  onClearAgent,
  onSelectAgent,
  onSetModel,
  onToggleTool,
  onToggleExpanded,
}: {
  activeConversation: Conversation | undefined;
  agentMode: "single" | "multi";
  agents: Agent[];
  draftAgentIds: string[];
  expanded: boolean;
  isSending: boolean;
  models: ModelOption[];
  selectedAgentIds: string[];
  selectedModelId: string;
  toolPreferences: ToolPreferences;
  onChangeMode: (mode: "single" | "multi") => void;
  onClearAgent: (agentId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onSetModel: (id: string) => void;
  onToggleTool: (key: keyof ToolPreferences) => void;
  onToggleExpanded: () => void;
}) {
  const isMulti = agentMode === "multi";
  const selectedSet = new Set(selectedAgentIds);
  const toolMeta: Array<{ key: keyof ToolPreferences; label: string; symbol: string }> = [
    { key: "file", label: "文件", symbol: "📎" },
    { key: "image", label: "图片", symbol: "🖼" },
    { key: "preview", label: "预览", symbol: "👁" },
    { key: "diff", label: "Diff", symbol: "🔀" },
  ];
  return (
    <section className="agent-row" aria-label="Agent 与工具">
      <div className="agent-row-mode">
        <button
          className="mode-badge"
          type="button"
          onClick={() => onChangeMode(isMulti ? "single" : "multi")}
          disabled={!activeConversation || isSending}
          aria-pressed={isMulti}
          title={!activeConversation ? "请先选择或新建会话" : "切换 Agent 模式"}
        >
          {isMulti ? "多智能体" : "单智能体"}
        </button>
      </div>
      <div className="agent-row-chips">
        {selectedAgentIds.map((agentId) => {
          const agent = agents.find((item) => item.id === agentId);
          return (
            <span className="agent-chip" key={agentId}>
              <AvatarBadge value={agentId} className="agent-chip-avatar" />
              <span className="agent-chip-name">{agentNameForDisplay(agent ?? { id: agentId, name: agentId } as Agent)}</span>
              <button
                aria-label={`移除 ${agentId}`}
                className="agent-chip-remove"
                type="button"
                onClick={() => onClearAgent(agentId)}
                disabled={!activeConversation || isSending || (isMulti && selectedAgentIds.length <= 1)}
              >
                ×
              </button>
            </span>
          );
        })}
        <button
          aria-label="添加 Agent"
          className="agent-chip agent-chip-add"
          type="button"
          onClick={onToggleExpanded}
          disabled={!activeConversation || isSending}
        >
          +
        </button>
      </div>
      <div className="agent-row-tools">
        {toolMeta.map((tool) => (
          <button
            key={tool.key}
            className={`tool-toggle ${toolPreferences[tool.key] ? "on" : ""}`}
            type="button"
            aria-pressed={toolPreferences[tool.key]}
            title={tool.label}
            onClick={() => onToggleTool(tool.key)}
          >
            <span aria-hidden="true">{tool.symbol}</span>
          </button>
        ))}
      </div>
      <div className="agent-row-model">
        <select
          aria-label="模型"
          className="model-select compact"
          value={selectedModelId}
          onChange={(event) => onSetModel(event.target.value)}
          disabled={isSending}
        >
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name}
            </option>
          ))}
        </select>
      </div>
      {expanded ? (
        <div className="agent-row-picker" role="listbox">
          {agents.map((agent) => {
            const isSelected = selectedSet.has(agent.id);
            return (
              <button
                className={`picker-option ${isSelected ? "selected" : ""}`}
                key={agent.id}
                type="button"
                role="option"
                aria-selected={isSelected}
                title={`${agentNameForDisplay(agent)} · @${agent.id}`}
                onClick={() => onSelectAgent(agent.id)}
                disabled={isSending}
              >
                <AvatarBadge value={agent.id} className="agent-chip-avatar" />
                <span className="picker-option-name">{agentNameForDisplay(agent)}</span>
                <span className="picker-option-mark" aria-hidden="true">
                  {isSelected ? "✓" : "+"}
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function ToastStack({
  toasts,
  onDismiss,
}: {
  toasts: ToastEntry[];
  onDismiss: (id: number) => void;
}) {
  if (toasts.length === 0) {
    return null;
  }
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((entry) => (
        <div className={`toast-card toast-${entry.kind}`} key={entry.id}>
          <span className="toast-message">{entry.message}</span>
          <button
            aria-label="Dismiss"
            className="toast-close"
            type="button"
            onClick={() => onDismiss(entry.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
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
    workflow_builder_tool: "工作流生成工具（workflow_builder_tool）",
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
