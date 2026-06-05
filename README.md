# AgentHub Demo

这是 AgentHub Demo 的 Day 1 最小可运行版本：React 前端 + FastAPI 后端，跑通“用户输入消息 -> 调用 `/chat` -> 返回 mock Agent 回复和 artifacts -> 前端展示”的闭环。

## 当前已实现

- FastAPI 后端接口：`GET /health`、`POST /chat`、`GET /agents`、artifact 查询和预览接口。
- React + Vite + TypeScript 单页前端。
- 聊天页面可以输入消息并调用后端 mock `/chat`。
- 前端可以展示 Agent 回复，以及 code / review / preview 三类 artifact 卡片。
- 预留 Harness 目录结构，方便 Day 2 接入 `HarnessRunner`。

## 环境准备

本项目 Python 依赖使用 `uv` 管理。首次进入项目后运行：

```bash
uv sync --group dev
```

前端依赖使用 npm：

```bash
cd app/web
npm install
```

如果 npm 下载慢，可以先设置镜像源：

```bash
npm config set registry https://registry.npmmirror.com
```

## 启动项目

在项目根目录运行：

```bash
./scripts/dev_all.sh
```

启动后访问：

- 前端：<http://localhost:5173>
- 后端：<http://localhost:8000>

## 分开启动

后端：

```bash
uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd app/web
npm run dev
```

## 测试

```bash
uv run pytest
```

也可以直接跑一次 mock demo：

```bash
uv run python scripts/run_demo.py
```

## Day 1 边界

当前版本故意只做 mock 闭环，不实现 AgentScope、真实 Harness、多 Agent 调度、Tool 调用、真实 LLM、数据库、沙箱、部署和流式输出。

后续 Day 2 建议从这条链路开始扩展：

```text
FastAPI /chat -> HarnessRunner -> mock agents -> artifacts
```
