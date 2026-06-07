# AgentHub

AgentHub is a Web-based multi-agent collaboration workspace. It uses an IM-style chat experience to coordinate agents, tools, files, images, previews, diffs, deployments, and generated artifacts in one product interface.

The current implementation includes a FastAPI backend, a React/Vite frontend, configurable built-in agents, user-created custom agents, OpenAI-compatible model providers, file/image attachments, artifact persistence, preview cards, deployment cards, diff application, version history, pinned context, long-context summaries, progress events, and a soft four-column Web app layout with resizable side panels.

## Product Positioning

AgentHub is designed as a simplified practical version of a multi-agent product workspace. Users interact through conversations, and each Agent behaves like a chat contact with specific capabilities.

Typical use cases:

- Single-agent work: choose Code Agent, Vision Agent, or File Analyst for focused tasks such as writing code, reviewing code, reading a file, or analyzing an uploaded image.
- Group collaboration: select multiple Agents or use `@agent` / `@tool` mentions, then let Orchestrator plan, route, execute, and summarize the work.
- Artifact workflow: generate code, preview HTML, inspect structured diff, apply patches, edit code artifacts, restore artifact versions, and publish a local static deployment.
- Context workflow: continue a multi-turn conversation with chat history, manually pinned messages, quoted selected text, and automatic long-context summaries.
- Custom Agent workflow: create a user-defined Agent with name, description, System Prompt, capabilities, selected tools, and optional model settings.

## Current Capabilities

- IM-style conversation list with create, search, pin, archive, restore, active sorting, and multi-conversation tabs.
- Single-agent and multi-agent chat modes.
- Orchestrator-based task routing with explicit `@agent` / `@tool` dispatch, rule dispatch, optional LLM JSON planner, dependency handling, parallel execution, fallback, and artifact aggregation.
- Built-in agents:
  - Orchestrator
  - Code Agent
  - UI Builder
  - Code Reviewer
  - Vision Agent
  - File Analyst
- User-created custom agents stored under `agent-workspace/runtime/custom_agents.json`.
- Built-in tools:
  - `file_reader_tool`
  - `image_reader_tool`
  - `preview_tool`
  - `code_review_tool`
  - `ui_builder_tool`
  - `deploy_tool`
  - `document_preview_tool`
- Model selector with Auto, StepFun, DeepSeek, and Doubao.
- Skill files under `skills/*.md` used as formal agent instructions.
- Image and file upload.
- Image-aware prompt flow for vision-capable OpenAI-compatible models.
- File text extraction for text-like attachments.
- PDF/Word/PowerPoint preview or download cards through document preview artifacts.
- Chat history, pinned messages, partial quotes, and long-context summaries passed into agent context.
- Regenerate flow with generation group metadata and answer version markers.
- Artifact persistence under `agent-workspace/runtime`.
- Preview HTML persistence under `agent-workspace/previews`.
- Local static deployment output under `agent-workspace/deployments`.
- Diff artifact apply API with workspace path checks, backup records, rollback support, and structured diff output for frontend display.
- Artifact version history and restore support for edited code/content artifacts.
- Four-column Web UI:
  - left rail navigation
  - resizable conversation list
  - main chat workspace
  - resizable/collapsible right panel for Artifacts / Agents / Tools / Context
- Execution progress display based on backend run events.
- Softer Coze/GPT-like visual treatment with rounded cards, translucent panels, subtle shadows, and draggable pane separators.

## Requirement Checklist

Done:

- Conversation list: active sorting, create, pin, archive, restore, and search.
- Single chat mode: selected Agent receives the task through the unified runtime.
- Group chat mode: supports explicit `@agent` / `@tool` and automatic Orchestrator dispatch.
- Message content: text, code blocks, images, file attachments, web preview cards, diff cards, deployment cards, document/PPT preview cards.
- Message actions: reply, partial quote, regenerate with version metadata, copy code, apply diff, expand preview.
- Context management: chat history, pinned messages, and automatic long-context summary.
- Orchestrator: intent recognition, task split, route, aggregation, parallel scheduling, fallback, and basic conflict artifact generation.
- Multi-agent access: unified adapter layer, built-in Agent configs, OpenAI-compatible model providers, and user-created custom Agents.
- Artifact preview and editing: iframe preview, code artifact editor, structured diff viewer, artifact versions, version restore.
- Deployment: local static deployment tool, deployment artifact, deployment status content, and generated preview URL.
- Web client: primary Web interface with IM workspace and side panels.
- Image understanding path: image metadata fallback plus vision-capable model prompt path.

Not complete or still basic:

- Claude Code, OpenCode, and official Codex CLI are still placeholders or adapter abstractions, not full CLI/process integrations.
- Diff viewer is unified and structured, but not yet a professional split diff with per-hunk confirmation and advanced conflict UI.
- Document/PPT preview is preview/download-card level, not full Office rendering and editing.
- Deployment is local static preview deployment; remote deployment, container deployment, and source package download are not complete.
- Desktop and mobile clients are not implemented.
- Source-level merge conflict resolution is still basic.

## Project Structure

```text
app/
  api/
    main.py
    routers/
      agents.py          Agent catalog and custom Agent CRUD
      artifacts.py       Artifact read/update/preview/diff/apply/version APIs
      attachments.py     File/image upload and download APIs
      chat.py            Chat and regenerate endpoints
      conversations.py   Conversation/message/pin/archive APIs
      deployments.py     Local static deployment file serving
    services/
      agent_service.py             Custom Agent persistence
      artifact_service.py          Artifact persistence and versions
      attachment_service.py        Upload persistence and text extraction
      context_summary_service.py   Long-context summary storage
      conversation_service.py      Conversation and message persistence
      diff_service.py              Diff parse/apply/rollback/structured diff
  configs/
    agents.yaml          built-in agent definitions
    models.yaml          model provider definitions
    tools.yaml           tool metadata
  web/
    src/
      App.tsx            Main React workspace
      api.ts             Frontend API client
      styles.css         Layout and visual styling
      types.ts           Frontend types

src/agenthub/
  adapters/              Mock, OpenAI-compatible, Codex-style adapters
  application/           Agent catalog and chat use case
  artifacts/             Artifact builders and conflict resolver
  domain/                RunContext, RunResult, messages, plans, artifacts
  harness/               Runtime policy/tool-loop support
  infrastructure/        Config, persistence, workspace support
  orchestration/         Orchestrator planner and coordinator
  policies/              Tool/run/agent policies
  runtime/               Prompt/context/result helpers
  skills/                Skill loader and models
  tools/                 Built-in tools and registry

skills/
  orchestrator.md
  code_agent.md
  ui_builder.md
  code_review.md
  vision_agent.md
  file_analyst.md

agent-workspace/
  runtime/               conversations, messages, artifacts, versions, custom agents
  uploads/               uploaded files/images
  previews/              generated preview HTML
  deployments/           local static deployment output
  generated/
  logs/
```

## Environment

Use the `agenthub` Conda environment on D drive.

```powershell
conda activate agenthub
```

Python dependencies are managed by `uv`:

```powershell
uv sync --group dev
```

Frontend dependencies are installed under `app/web/node_modules`:

```powershell
cd app\web
npm install --cache D:\code\agenthub\AgentHub\.npm-cache
```

## Model Configuration

Create or update `.env` in the project root. API keys should stay in `.env`; do not commit them.

```env
ENABLE_REAL_LLM=true
ENABLE_LLM_PLANNER=false
LLM_TIMEOUT_SECONDS=180

DEFAULT_MODEL_PROVIDER=stepfun

OPENAI_API_KEY=
OPENAI_BASE_URL=
MODEL_NAME=

STEPFUN_API_KEY=
STEPFUN_BASE_URL=https://api.stepfun.com/step_plan/v1
STEPFUN_MODEL_NAME=step-3.7-flash

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL_NAME=

DOUBAO_API_KEY=
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL_NAME=

CODEX_MODE=llm
CODEX_MODEL=
```

Model options shown in the frontend are configured in:

```text
app/configs/models.yaml
```

Agent definitions are configured in:

```text
app/configs/agents.yaml
```

## Run

Backend:

```powershell
conda activate agenthub
python -m uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd .\AgentHub\app\web
npm run dev -- --host 0.0.0.0 --port 5173
```

Open:

```text
http://127.0.0.1:5173
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Evaluation Cases

- Create a custom Agent in the Agents panel, assign a System Prompt and selected tools, then create a single-agent conversation with that Agent.
- Send `@ui_builder @code_reviewer build a React settings page` and confirm group routing, generated artifacts, preview, and review output.
- Upload a text file and ask File Analyst to summarize it; confirm file extraction artifact appears.
- Upload an image and ask Vision Agent to analyze it; use Doubao or another vision-capable model for semantic image understanding.
- Ask `Build a landing page and deploy it`; confirm deployment artifact and local preview URL under `/deployments/.../index.html`.
- Generate or load a diff artifact, click structured diff view, then apply the diff and verify workspace-safe patching.
- Edit a code artifact in the full-screen editor, save it, then restore a previous artifact version.
- Select part of an Agent answer, use partial quote, and send a follow-up.
- Use regenerate and confirm answer version metadata is retained.
- Switch between multiple conversations and confirm conversation tabs keep recently opened sessions available.

## Test

Backend tests:

```powershell
D:\Miniconda3\envs\agenthub\python.exe -m pytest -q -p no:cacheprovider --basetemp D:\code\agenthub\AgentHub\.pytest-tmp-run
```

Frontend build:

```powershell
cd app\web
npm run build -- --emptyOutDir
```

## Important Notes

- `agent-workspace/runtime` stores runtime conversation/artifact/custom-agent data and is ignored by git.
- `agent-workspace/uploads` stores uploaded files/images and is ignored by git except `.gitkeep`.
- `agent-workspace/previews` and `agent-workspace/deployments` store generated runtime output.
- `.env` is ignored by git and should contain all private API keys.
- Image understanding depends on the selected model supporting vision input. Doubao vision-capable models should be used for image tasks.
- The current `CodexAdapter` is an AgentHub adapter abstraction with mock/LLM modes. It is not yet a full official Codex CLI or Claude Code integration.
