# AgentHub

AgentHub is a Web-based multi-agent collaboration workspace. It uses an IM-style chat experience to coordinate agents, tools, files, images, previews, and generated artifacts in one product interface.

The current implementation is no longer a Day 1 mock demo. It includes a FastAPI backend, a React/Vite frontend, configurable agents, OpenAI-compatible model providers, file/image attachments, artifact persistence, preview cards, pinned context, progress events, and a four-column Web app layout.

## Current Capabilities

- IM-style conversation list with create, search, pin, archive, restore, and active sorting.
- Single-agent and multi-agent chat modes.
- Orchestrator-based task routing with rule dispatch and optional LLM JSON planner.
- Built-in agents:
  - Orchestrator
  - Code Agent
  - UI Builder
  - Code Reviewer
  - Vision Agent
  - File Analyst
- Built-in tools:
  - `file_reader_tool`
  - `image_reader_tool`
  - `preview_tool`
  - `code_review_tool`
  - `ui_builder_tool`
- Model selector with Auto, StepFun, DeepSeek, and Doubao.
- Skill files under `skills/*.md` used as formal agent instructions.
- Image and file upload.
- Image-aware prompt flow for vision-capable OpenAI-compatible models.
- File text extraction for text-like attachments.
- Chat history and pinned messages passed into agent context.
- Artifact persistence under `agent-workspace/runtime`.
- Preview HTML persistence under `agent-workspace/previews`.
- Diff artifact apply API with workspace path checks and backup records.
- Four-column Web UI:
  - left rail navigation
  - conversation list
  - main chat workspace
  - collapsible right panel for Artifacts / Agents / Tools / Context
- Execution progress display based on backend run events.

## Project Structure

```text
app/
  api/
    main.py
    routers/              FastAPI routes
    services/             conversation, artifact, attachment, diff, chat services
  configs/
    agent.yaml            built-in agent definitions
    models.yaml           built-in model provider definitions
    tools.yaml            tool metadata
  web/
    src/                  React app

src/agenthub_harness/
  adapters/               mock, OpenAI-compatible, Codex-style adapters
  core/                   RunContext, HarnessRunner, run result/events
  runtime/                Orchestrator planner and rule dispatch
  tools/                  preview, file, image, review, UI tools
  skills/                 skill loader
  llm/                    OpenAI-compatible chat provider

skills/
  orchestrator.md
  code_agent.md
  ui_builder.md
  code_review.md
  vision_agent.md
  file_analyst.md

agent-workspace/
  generated/
  previews/
  uploads/
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
app/configs/agent.yaml
```

## Run

Backend:

```powershell
conda activate agenthub
python -m uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd D:\code\agenthub\AgentHub\app\web
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

- `agent-workspace/runtime` stores runtime conversation/artifact data and is ignored by git.
- `agent-workspace/uploads` stores uploaded files/images and is ignored by git except `.gitkeep`.
- `.env` is ignored by git and should contain all private API keys.
- Image understanding depends on the selected model supporting vision input. Doubao vision-capable models should be used for image tasks.
- The current `CodexAdapter` is an AgentHub adapter abstraction with mock/LLM modes. It is not yet a full official Codex CLI or Claude Code integration.

## Known Gaps

- User-created custom agents are not implemented yet.
- Claude Code / OpenCode / official Codex CLI integration is not complete.
- Deployment cards and deployment pipelines are not implemented yet.
- Long-context automatic summarization is not implemented yet.
- Diff apply exists, but the frontend does not yet have a professional split/unified diff viewer.
- Source-level merge conflict resolution is still basic.
- Desktop and mobile clients are not implemented yet.

