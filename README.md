# AgentHub

AgentHub 是可在本机运行的多 Agent 工作台，使用 FastAPI、React/Vite 与 Python Harness。聊天、工作流统一编译为依赖图，由 Harness 执行、记录事件、检查权限、保存检查点，并在用户审批后恢复运行。

当前交付范围是**本地单用户、单服务进程**。提供无密钥演示模式，以及 OpenAI-compatible 模型和可信 CLI 接入。演示模式会在界面明确标注，样例输出不代表真实模型调用。

## 立即启动

环境：Python 3.11+、Node.js 20+、npm、uv。无需 Conda、Redis 或 Docker。

Windows PowerShell，在仓库根目录执行：

```powershell
uv sync --locked --group dev
cd app/web
npm ci
npm run build
cd ../..
.\scripts\start.ps1 -Demo
```

打开 **http://127.0.0.1:8000**。API 文档在 http://127.0.0.1:8000/docs 。`Ctrl+C` 停止。

本机已安装依赖时可直接运行：

```powershell
.\scripts\start.ps1 -Demo -Build
```

如果 PowerShell 的脚本策略阻止启动，可用同一入口的 Python 命令：

```powershell
.\.venv\Scripts\python.exe -m agenthub --demo
```

macOS / Linux 在安装并构建前端后执行 `uv run python -m agenthub --demo`。

## 接入真实模型

首次配置时复制 `.env.example` 为 `.env`；已有 `.env` 时直接编辑，保留自己的配置。示例：

```dotenv
ENABLE_REAL_LLM=true
ENABLE_LLM_PLANNER=true
DEFAULT_MODEL_PROVIDER=openai
OPENAI_BASE_URL=https://你的兼容服务地址/v1
OPENAI_API_KEY=你的密钥
MODEL_NAME=服务支持的模型名称
LLM_TIMEOUT_SECONDS=30
RUN_TIMEOUT_SECONDS=300
RUN_MAX_LLM_CALLS=24
```

重新执行 `.\scripts\start.ps1`，**不加 `-Demo`**，界面模型选择 `Auto` 或 `OpenAI-compatible`。StepFun、DeepSeek、Doubao 也可分别填写其专属配置并在界面选择；密钥和 URL 不会在不同供应商之间混用。

`--demo` 会忽略 `.env` 并强制模拟模式。真实模型缺少配置或调用失败会明确报错，不会自动替换为模拟成功。

## 可以做什么

- 单 Agent 对话、多 Agent 任务拆分、依赖执行、独立步骤并行。
- 真实模型通过标准 Chat Completions 工具调用循环获取工具结果，再继续回答；最多 8 轮工具循环，并受调用次数和运行时限约束。
- 显式 Agent / 工具提及、YAML 能力配置、自定义 Agent 与模型选择。
- 文件、图片、PDF、DOCX、PPTX 附件；文本提取、图片模型分析、固定上下文、模型摘要和记忆。
- 代码、审查、工作流、预览、冲突与本地静态部署产物；版本查看和恢复。
- Diff 按实际勾选片段应用；应用前校验审阅指纹；支持新建、修改、删除文件及回滚；拒绝覆盖后续手工修改。
- 后台运行、事件轮询、取消、待审批队列、审批后继续执行，以及历史运行调试记录。
- SQLite 持久化，事件和步骤检查点保存，发布结果与会话/产物记录在同一事务提交。

## Harness 如何执行

```text
消息 / Workflow JSON
        ↓
Orchestrator → Plan（Agent、工具、参数、依赖）
        ↓
Harness → 校验依赖与权限 → 每 run 创建沙箱 → 保存检查点
        ↓
L1 读取 / 生成提案       L2/L3 实际动作
自动执行                 保存待审批动作与指纹 → 用户确认
        ↓                          ↓
模型 ↔ 已授权工具          从同一 run_id 恢复，执行已审阅动作
        └──────────────┬───────────┘
                事件、产物、会话、结果
```

副作用边界：CLI 子进程与工具写文件都经过沙箱，审计报告随运行返回。

生成代码、HTML、工作流定义属于提案；不会因此修改项目文件。文件应用需要在 Diff 面板明确选择片段并点击应用。部署步骤会在代码生成后单独暂停，审批卡展示任务、参数和工作区。拒绝或失败的步骤会阻止其依赖步骤继续执行。

默认每次运行最多执行 12 个步骤，独立读取步骤最多并行 4 个；调用预算包括模型重试。缓存默认关闭；配置 Redis 后仅缓存明确允许缓存的读取步骤，键包含会话、历史、上游内容、工作区、模型、凭据身份和 Skills。TTL 为 0 会完全禁用缓存。

## 数据与恢复

默认数据目录：`agent-workspace/`，可用 `AGENTHUB_DATA_DIR` 改为其他绝对路径。

```text
agent-workspace/
  runtime/agenthub.sqlite3    会话、消息、产物、版本、运行、审批和补丁日志
  projects/<conversation>/   当前会话的 CLI / Diff 工作区
  uploads/                   上传文件
  previews/                  预览文件
  deployments/               已审批的本地静态部署
```

首次访问会导入旧 JSON 数据，原文件保留。后续 SQLite 为数据来源。备份时先停止服务，再复制整个数据目录。

服务重启后，`waiting_approval` 运行仍可审批恢复。执行中遭遇进程中断的运行标记为 `interrupted`，不会自动重放可能已经产生效果的步骤；检查工作区后重新提交任务。补丁写入前有恢复日志；多文件应用正常失败时撤回已写文件，进程硬中断时需检查日志和文件状态。

## 开发与检查

```powershell
uv run pytest -q
uv run ruff check --select E9,F63,F7,F82 src app/api tests
cd app/web
npm run build
```

开发模式开两个终端：`uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000`，以及在 `app/web` 中执行 `npm run dev`。前端访问 http://127.0.0.1:5173 。仓库 CI 配置会在 Windows 和 Linux 上运行后端检查与前端构建。

测试使用临时目录并忽略用户 `.env`。HTTP 模型工具循环使用受控响应验证，不消耗真实 API 额度。

## CLI 与适用边界

- `CODEX_MODE=cli`、`CODEX_COMMAND`、`CLAUDE_CODE_COMMAND`、`OPENCODE_COMMAND` 可配置已安装且已完成认证的非交互 CLI。命令通过 stdin 接收任务，stdout 返回文本或 fenced code；路径含空格时加引号。启用模型模式后，选择相应 CLI Agent，审批后执行。
- CLI 的工作目录是会话目录；它仍是本机进程，**工作目录隔离不是操作系统沙箱**。只接入可信 CLI 和任务。

## 沙箱边界

每次运行有一个沙箱实例，所有跨出进程的副作用都经过它：CLI 子进程走 `sandbox.exec()`，工具写文件走 `sandbox.write_path()`，两者都会被记录到审计报告并随 `sandbox.report` 事件返回。

默认 backend 是 `local`，它提供进程树纳管（Windows Job Object / POSIX 进程组）、资源限额、环境变量白名单和文件系统边界——**但不提供操作系统沙箱**：没有 namespace、seccomp 或网络封禁，沙箱内的 CLI 仍以 AgentHub 用户身份运行。更强的隔离是同一接口下的另一个 backend，通过 `AGENTHUB_SANDBOX_BACKEND` 选择，不需要改调用方代码。

CLI 子进程不再全量继承 AgentHub 的环境变量，只拿到白名单内的变量加上声明的凭据。需要额外变量时用 `AGENTHUB_SANDBOX_EXTRA_ENV` 显式放宽。资源限额与网络策略见 `.env.example` 中的 `AGENTHUB_SANDBOX_*`。

审批卡除了展示任务、参数和工作区，还会展示该步骤的沙箱边界（网络策略、是否可写文件、是否可起进程）。
- 此版本没有多用户登录、租户隔离、分布式队列或云部署管理。服务默认只绑定回环地址，并限制 Host 和浏览器写入来源；不要作为公共多人服务直接暴露。
- 取消为协作式：阻止后续步骤并终止受管 CLI 进程树；已经发出的 HTTP 模型请求可能等到响应或请求超时才结束。
- PDF 仅做文本提取，不包含 OCR；DOCX/PPTX 提取文本，不还原 Office 排版。代码静态检查不等于测试通过。TSX 预览依赖生成的预览页，不替代真实项目构建。
- 本地静态“部署”是在当前服务下提供 HTML，不是发布到公网。

代码职责及关键约束见 [ARCHITECTURE.md](ARCHITECTURE.md)。

本轮本机验收范围见 [VALIDATION.md](VALIDATION.md)。
