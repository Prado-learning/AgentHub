# AgentHub 执行与维护说明

## 依赖方向

`app/api` 是组合根：HTTP 校验、后台任务触发、模型适配器组装和发布。`src/agenthub` 不反向导入 API 服务——这是硬约束，`harness` 与 `sandbox` 可以在没有 FastAPI 的情况下被导入和使用。`application/chat` 通过注入的用例入口访问持久化与运行；旧 API 服务模块保留兼容别名。

```
app/api                      传输层 + 组合根
  ↓
src/agenthub/
  domain/          纯数据模型：Plan / Run / RunContext / AuthorityTier / Trace
  application/     用例层（chat、tools 目录）
  ── 引擎层 ──
  orchestration/   请求 → Plan：任务分解、选 agent、依赖推断、附件路由
  agent/           agent 身份与能力：定义、profile、注册表
  harness/         执行引擎 + run 生命周期监督
  sandbox/         每次运行的受控执行环境
  runtime/         模型工具循环（协议层，经 ContextVar 绑定当前 sandbox）
  ── 能力层 ──
  adapters/        模型 provider 与外部 CLI（副作用全部经 sandbox 执行）
  tools/           内置工具
  skills/          skill 加载
  ── 横切 ──
  policies/        纯规则数据（tool / agent / run / sandbox）
  gateway/         出站调用门面（缓存、身份）
  infrastructure/  持久化与配置
  registry.py      四个扩展接缝：adapters / tools / planners / sandbox backends
```

### harness

- `harness/runner.py`：唯一 DAG 调度器，聊天与工作流均使用它；执行前审批、上下游数据、步骤限额、失败传播、检查点、每 run 绑定沙箱。
- `harness/supervisor.py`：run 生命周期监督——后台执行、审批恢复、取消、重启恢复、每 run 沙箱归属。通过 `RunStorePort` / `DecisionStorePort` / `ResultPublisher` 三个端口依赖持久化，本身不 import 应用层。
- `harness/control.py`：取消、运行时限、模型调用预算和事件上下文。
- `harness/authority_gate.py`：L1/L2/L3 分级授权门。审批是派发的前置条件，不是完成后的注解。
- `harness/fingerprint.py`：动作指纹。绑定步骤、上下文、Agent 配置、模型身份与凭据哈希；任一变化都必须重新审阅。
- `harness/tracing.py`：阶段级追踪，`AGENT_DEBUG` 关闭时近零开销。

### sandbox

一次运行一个沙箱实例。**所有跨出当前进程的副作用都必须经过它**：适配器起 CLI 走 `sandbox.exec()`，工具写文件走 `sandbox.write_path()`。

- `sandbox/spec.py`：声明式边界——可写根、只读挂载、网络策略、资源限额、凭据作用域、生命周期。
- `sandbox/base.py`：`Sandbox` Protocol（exec / read_path / write_path / stop）。边界即接口，backend 可替换。
- `sandbox/manager.py`：按 run 创建/销毁，并用 ContextVar 把实例绑定到当前执行域（与 `RunControl`、事件 sink 并列的第三个环境对象）。
- `sandbox/backends/local.py`：默认 backend。进程树纳管（Windows Job Object / POSIX 进程组）、资源限额、环境变量白名单、文件系统边界、审计。
- `sandbox/backends/windows_job.py`：Job Object 封装。除 `KILL_ON_JOB_CLOSE` 外，还会按 spec 设置 CPU 时间、内存与进程数上限。
- `sandbox/audit.py`：`SandboxReport`——本次运行实际起了哪些进程、写了哪些文件、拒绝了什么。
- `sandbox/profiles.py`：`run_spec()` 工厂 + 环境变量开关。
- `policies/sandbox_policy.py`：tier → 边界映射。审批卡会展示该步骤的边界说明；run 的 spec 取计划中所有 tier 的最严边界。

**local backend 的边界是诚实的**：它做进程生命周期与资源管理，不做操作系统沙箱。没有 namespace、seccomp、网络封禁；沙箱内的 CLI 仍以 AgentHub 用户身份运行。更强的隔离是同一接口下的另一个 backend（`AGENTHUB_SANDBOX_BACKEND` 选择），不是重写。

### registry

`registry.py` 持有四个接缝：`ADAPTER_BUILDERS` / `TOOL_FACTORIES` / `PLANNER_FACTORIES` / `SANDBOX_BACKENDS`。各子系统的内置实现保留在自己模块里，启动时把注册表合并在上面——注册名与内置同名时覆盖内置。未知的 adapter 类型或 backend 名称会显式报错，不会静默降级。

## 关键约束

1. `run_id` 在排队时确定。前端取消通过该 ID 通知服务端，不能只终止 fetch。
2. 一个会话同时只有一个通过后台入口提交的活跃运行。后台线程池属于一个服务进程；启动入口强制单 worker。
3. 动作指纹绑定步骤、上下文、Agent 配置、模型身份、凭据哈希；变化后必须重新审阅。生成与部署拆成两个步骤，审批之前不执行部署。审批卡同时展示该步骤的沙箱边界。
4. 模型只能调用当前步骤中已授权的读取/提案工具；不能动态扩大到写入或部署。工作流声明的未知工具默认高权限，执行时仍受注册表与 Agent 工具权限限制。
5. 工具失败使所属步骤失败，其依赖步骤跳过。真实模型失败不会默默回退到 Mock；拼错的 adapter 类型同样显式报错。
6. 上游正文与精确产物沿全部依赖祖先传递。输入缓存包含这些内容，避免跨会话、模型或代码版本复用答案。
7. 文件修改位于会话工作区，路径拒绝穿越及受保护文件。沙箱的可写根是数据目录；越界读写抛 `SandboxError` 并记入审计。Diff 的审阅令牌还包含当前文件摘要；回滚只允许目标仍与应用结果一致。
8. 输出发布及其完成标记在 SQLite 同一事务提交；模型执行、HTTP 请求和文件写入不持有长数据库事务。
9. SQLite 使用命名空间 JSON payload，以兼容原数据格式；本地持久化可靠，但大规模分析/检索应迁移为行级表结构和专用索引。
10. 执行中断时保存的 inflight_steps 表示效果可能不确定，不能承诺外部 CLI 或网络操作的 exactly-once。
11. **沙箱生命周期**：runner 创建（只有它知道计划的 tier，从而知道策略要求的边界），supervisor 释放（保证跨 resume 存活、不越过 run 结束）。注入的沙箱由其创建者负责释放。
12. **沙箱子进程环境**：不再全量继承 AgentHub 进程环境，而是白名单 + 声明的凭据。需要额外变量时用 `AGENTHUB_SANDBOX_EXTRA_ENV` 显式放宽。

Windows CLI 通过隔离的 Python 启动器先加入 Job Object，再经 stdin 接收并启动命令，避免创建子进程后才纳管的竞态。结束或取消时关闭 Job 句柄，终止整棵受管进程树；POSIX 使用独立进程组。实现依据 [Microsoft Job Objects 文档](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。这属于进程生命周期与资源管理，不是权限沙箱。

## 验证入口

`tests/test_runtime_regressions.py` 覆盖模型工具循环、用量、预算、取消、上下游、缓存身份、Windows 路径、Diff、事务、多进程 SQLite 与后台 API。审批完整生命周期见 `tests/test_run_decisions_api.py` 和 `tests/test_authority_gate.py`。

新增：

- `tests/test_sandbox.py`：沙箱边界、环境白名单、审计、作用域绑定、策略与审批卡。
- `tests/test_supervisor.py`：run 生命周期（执行、恢复、取消、占位、重启恢复、沙箱归属），全程使用内存端口，不依赖应用层。
- `tests/test_registry.py`：四个扩展接缝的覆盖与显式失败。
