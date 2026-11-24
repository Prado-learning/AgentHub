# 本地验收记录

验收日期：2026-09-09（Asia/Shanghai）。

环境：Windows，Python 3.11.6，Node.js 24.12.0，项目 `.venv`，本机 Chrome headless。

## 已执行

- `python -m pytest -q`：**210 passed**，41.06 秒。测试使用临时数据目录并忽略真实 `.env`；存在一条 Starlette/httpx 测试客户端弃用提示，无失败用例。
- `ruff check --select E9,F63,F7,F82 src app/api tests`：通过。
- `npm run build`：TypeScript 检查与 Vite 生产构建通过。
- `git diff --check`：通过；Git 仅提示已有 CRLF 工作区的行尾转换。
- `scripts/start.ps1 -Demo -Build -Port 18765`：完成前端构建，启动单端口 Web/API，首页及 API 健康检查正常。
- Chrome 实际发送聊天，等待后台结果；发起部署，看到审批卡；点击确认，同一 run_id 继续完成；页面刷新后结果仍存在；部署页面 HTTP 200 并带 sandbox CSP。
- Chrome 实际打开 Diff 审阅，选择片段，提交应用成功；点击回滚成功；Escape 关闭原生对话框；两条界面操作链均无 pageerror。
- 截图检查后修复窄侧栏内状态标签、参数和工作区路径的溢出。
- 实际启动测试 CLI 及其子进程后取消：适配器在 5 秒内返回取消，等待后确认父、子进程均未继续写文件；普通 CLI 输出、错误返回与缺失命令检查通过。

浏览器验收运行：`run_d8a564578132`（聊天）、`run_f88c8588583c`（审批后部署），最终状态 `success`，决策 `applied`。

截图和浏览器脚本位于本机 Git 忽略目录 `agent-workspace/verification/`，测试数据与日常会话数据分开。临时验收服务在交付前停止；正式启动按 README 操作。

## 自动化覆盖重点

审批发生在动作执行前；动作/模型/上下文变更使审批失效；恢复不重复执行已完成步骤；拒绝和取消阻止后续动作；工作流工具节点使用统一 Harness；步骤与模型预算；模型 tool_calls 和用量；精确上游代码；跨会话及模型缓存隔离；零 TTL；Windows 路径穿越；新建/删除/选块 Diff 及冲突保护；跨进程 SQLite；发布事务回滚；中断后的恢复。

## 未作为通过项宣称

真实付费模型与各外部 CLI 的账号认证没有使用用户密钥实测。模型协议与工具循环使用受控响应验证，CLI 进程适配使用本机测试程序验证。GitHub Actions 已配置，但未推送触发云端 CI。此验收不覆盖多用户公网部署、OCR、GPU 或模型质量评估。
