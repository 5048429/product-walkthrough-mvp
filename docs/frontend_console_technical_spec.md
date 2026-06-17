# Prodwalk 前端控制台技术规格

## 项目目标

为当前 Python multi-agent 产品走查系统增加一个本地 Web 控制台，让用户可以通过浏览器完成原本依赖命令行的操作，并实时观察 run、agent、event、evidence、artifact、report 的状态。

第一版目标是本地单机控制台，不是多人协作 SaaS。它应该满足：

- 使用 React + Vite + TypeScript 构建前端，目录规划为 `apps/web`。
- 使用 FastAPI 构建后端，目录规划为 `src/prodwalk/server`。
- 保留现有 CLI 行为和命令参数。
- 复用现有 `ResearchDirector`、walker、report、evaluation、credential/auth-session 能力。
- 支持启动 run、查看 agent 状态、实时事件流、查看 evidence 和 Markdown report。
- 使用当前 artifact 文件作为事实来源，避免第一版引入数据库复杂度。

## 当前项目结构理解

当前项目是一个 Python 包，入口和核心链路如下：

- `src/prodwalk/cli.py`
  - 提供 `run`、`auth-session`、`credentials` 子命令。
  - `run` 命令负责加载 config、选择 walker、处理 verification preflight、创建 `run-YYYYMMDD-HHMMSS` 输出目录。
  - 支持 `mock`、`browser-use`、`browser-use-local` 模式。

- `src/prodwalk/agents/director.py`
  - `ResearchDirector.run(plan, run_dir)` 是核心编排入口。
  - 当前 pipeline 是批处理式，执行完成后一次性写出 `evidence.json`、`report.md`、`evaluation.json`。
  - 当前没有内建事件总线，也没有 agent 状态持久化。

- `src/prodwalk/models.py`
  - 已有领域模型：`ProductTarget`、`Scenario`、`ResearchPlan`、`WalkStep`、`EvidenceItem`、`WalkthroughResult`、`Finding`、`ProductAnalysis`、`CompetitiveInsight`、`ReviewNote`、`EvaluationResult`。
  - Web 控制台应在这些模型之上增加 run、agent、event、artifact 运行时模型，而不是替换这些模型。

- `src/prodwalk/agents/walker.py`
  - `MockBrowserWalker` 用于无浏览器验证编排。
  - `BrowserUseLocalWalker` 控制本地 browser-use 和 Chrome/Edge。
  - browser-use 的 step 细节目前主要在运行完成后从 history 文件提取，因此第一版实时 step 粒度可能有限。

- `src/prodwalk/auth_session.py`
  - 提供 human-assisted login、profile、storage state 能力。
  - Web 控制台第一版不应重写 auth 流程，只应暴露 verification 状态和继续操作入口。

- 当前 artifact 形态
  - `runs*/run-*/evidence.json`
  - `runs*/run-*/report.md`
  - `runs*/run-*/evaluation.json`
  - `runs*/run-*/screenshots/`
  - 项目根目录下存在若干 `browser_use_history_*.json`。

当前约束：

- pipeline 是一次性返回完整结果，不是逐 agent callback 架构。
- 截图 archive 已经存在，但真实历史 run 中仍可能残留临时路径引用，Web 后端必须做 artifact path 归一化和访问控制。
- credential store 使用本地 DPAPI，前端不应展示或传输明文 secret。

## 推荐目录结构

本规格仅设计目录，不在当前阶段创建实现目录。

```text
apps/
  web/
    package.json
    vite.config.ts
    tsconfig.json
    index.html
    src/
      main.tsx
      app/
        App.tsx
        router.tsx
        providers.tsx
      api/
        client.ts
        contracts.ts
        sse.ts
      features/
        runs/
          RunListPage.tsx
          RunDetailPage.tsx
          RunLauncher.tsx
          runQueries.ts
          runTypes.ts
        agents/
          AgentStatusPanel.tsx
          AgentTimeline.tsx
        events/
          EventStreamPanel.tsx
          EventFilters.tsx
        artifacts/
          ArtifactList.tsx
          ArtifactPreview.tsx
          EvidenceExplorer.tsx
        reports/
          ReportViewer.tsx
          EvaluationSummary.tsx
      components/
        layout/
        ui/
      styles/
        globals.css
```

```text
src/prodwalk/server/
  __init__.py
  main.py
  schemas.py
  settings.py
  routes/
    __init__.py
    health.py
    plans.py
    runs.py
    agents.py
    events.py
    artifacts.py
    reports.py
  services/
    run_service.py
    pipeline_adapter.py
    event_bus.py
    event_store.py
    artifact_service.py
    run_repository.py
    plan_service.py
  storage/
    __init__.py
```

建议 run 目录增加运行时元数据：

```text
runs/run-YYYYMMDD-HHMMSS/
  run.json
  agents.json
  events.jsonl
  artifacts.json
  evidence.json
  report.md
  evaluation.json
  screenshots/
```

## 后端 FastAPI 模块设计

### `main.py`

职责：

- 创建 FastAPI app。
- 注册 CORS，仅允许本地开发域名。
- 注册 routes。
- 初始化 `RunService`、`RunRepository`、`EventBus`、`ArtifactService`。

### `schemas.py`

职责：

- 定义 Pydantic 请求和响应模型。
- 包含 `RunStatus`、`AgentStatus`、`RunEvent`、`Artifact`、`RunSummary`、`RunDetail`、`CreateRunRequest`、`ApiError`。
- API 契约以 `docs/api_event_contract.md` 为准。

### `RunService`

职责：

- 接收 `CreateRunRequest`。
- 解析 plan 来源，支持 `config_path` 或 inline `plan`。
- 创建 run id 和 run directory。
- 写入 `run.json` 初始状态。
- 在后台任务中启动 pipeline。
- 更新 run lifecycle 状态。
- 提供 cancel 标记。第一版 cancel 可以是 cooperative best-effort，不保证中断 browser-use 内部所有 await。

### `PipelineAdapter`

职责：

- 在不改 CLI 行为的前提下，封装现有运行逻辑。
- 复用 `load_research_plan`、`MockBrowserWalker`、`BrowserUseLocalWalker`、`HumanVerificationRetryWalker`、`ResearchDirector`。
- 将 Web 请求参数映射为当前 CLI 参数语义。
- 在关键阶段发出事件。

第一版建议先做轻量 instrumentation：

- run started
- planner started/completed
- scenario started/completed
- evidence extraction completed
- report generated
- evaluation generated
- run completed/failed

更细的 browser step 事件可以在 run 完成后从 `WalkthroughResult.steps` 批量生成。

### `EventBus` 和 `EventStore`

职责：

- `EventBus` 管理内存订阅者，为 SSE 推送提供队列。
- `EventStore` 将事件 append 到 `events.jsonl`。
- 每个事件有单调递增 `seq`。
- SSE 断线重连时通过 `after_seq` 回放事件。

推荐事件写入顺序：

1. 写入 `events.jsonl`。
2. 更新内存 last event。
3. 广播给 SSE subscriber。

### `RunRepository`

职责：

- 读写 `run.json`、`agents.json`、`artifacts.json`。
- 扫描历史 `runs*` 目录，兼容旧 run。
- 对旧 run 缺少 `run.json` 的情况，使用目录名和 artifact 文件推导只读 `RunSummary`。

### `ArtifactService`

职责：

- 只允许访问 run directory 内的文件。
- 建立 artifact registry：`report.md`、`evaluation.json`、`evidence.json`、截图、browser history。
- 将 legacy evidence 中的路径归一化为 artifact URL。
- 对 storage state、credential store 等敏感文件默认不暴露。
- 对未知绝对路径默认拒绝，除非已被复制进 run directory。

## 前端 React 模块设计

### 应用框架

推荐：

- React + Vite + TypeScript。
- React Router 管理页面。
- TanStack Query 管理 REST 请求和缓存。
- 原生 `EventSource` 或轻量封装管理 SSE。
- 前端类型从 `api/contracts.ts` 维护，后续可由 OpenAPI 生成。

### 页面

- `RunListPage`
  - 展示历史 runs。
  - 展示状态、开始时间、耗时、模式、report 入口。

- `RunLauncher`
  - 选择 example plan 或输入 config path。
  - 选择 mode：`mock`、`browser-use`。
  - 配置 concurrency、report language、browser max steps、timeout、profile dir、verification mode。
  - 第一版不在 UI 中编辑 credentials 明文。

- `RunDetailPage`
  - 顶部展示 run 状态、进度、耗时、错误。
  - 中间展示 agent 状态和事件流。
  - 下方或侧边展示 artifacts、evidence、report。

- `AgentStatusPanel`
  - 按 pipeline 顺序显示 agent 状态。
  - walker agent 需要按 product + scenario 展开。

- `EventStreamPanel`
  - 通过 SSE 接收实时事件。
  - 支持 level、agent、scenario 简单过滤。
  - 支持断线重连后从 `after_seq` 补事件。

- `EvidenceExplorer`
  - 从 `evidence.json` 展示 evidence list。
  - 支持按 product、scenario、kind、confidence 过滤。
  - 如果 evidence 引用截图 artifact，展示缩略图或链接。

- `ReportViewer`
  - 渲染 Markdown report。
  - 展示 evaluation summary。
  - 提供下载 artifact。

## 数据流

### 启动 run

```text
User
  -> apps/web RunLauncher
  -> POST /api/runs
  -> RunService.create_run
  -> 写 run.json, events.jsonl
  -> 后台任务运行 PipelineAdapter
  -> 前端跳转 /runs/:runId
```

### 实时状态

```text
RunDetailPage
  -> GET /api/runs/{run_id}
  -> GET /api/runs/{run_id}/agents
  -> EventSource /api/runs/{run_id}/events/stream
  -> 收到 RunEvent 后更新本地事件列表
  -> 定期或事件触发 refetch run/agents/artifacts
```

### 产物读取

```text
ReportViewer
  -> GET /api/runs/{run_id}/report
  -> 后端读取 report.md + evaluation.json

EvidenceExplorer
  -> GET /api/runs/{run_id}/evidence
  -> 后端读取 evidence.json

ArtifactPreview
  -> GET /api/runs/{run_id}/artifacts/{artifact_id}/content
```

## 实时事件流

第一版使用 SSE，不使用 WebSocket。理由：

- 控制台主要是后端到前端的单向实时消息。
- SSE 支持浏览器原生重连。
- 实现简单，便于用 `events.jsonl` 回放。

事件原则：

- 所有事件都是 append-only。
- `seq` 在一个 run 内严格递增。
- 前端用 `seq` 去重。
- `payload` 可扩展，但稳定字段必须在顶层。
- 不在事件中写入 secret、token、完整 credential、storage state 内容。

建议事件阶段：

```text
run.created
run.started
agent.started
agent.completed
scenario.started
scenario.step.completed
scenario.completed
artifact.created
report.generated
evaluation.generated
run.awaiting_verification
run.completed
run.failed
run.canceled
```

## Run 生命周期

```text
queued
  -> starting
  -> running
  -> awaiting_verification
  -> running
  -> finalizing
  -> succeeded

queued/running/finalizing
  -> failed

queued/running/awaiting_verification
  -> canceling
  -> canceled
```

状态说明：

- `queued`：run 已创建，后台任务尚未启动。
- `starting`：正在解析 plan、准备 run directory 和 walker。
- `running`：pipeline 正在运行。
- `awaiting_verification`：需要用户完成 Altcha、CAPTCHA、SSO、MFA 或登录确认。
- `finalizing`：正在归档截图、写 report/evaluation/artifact registry。
- `succeeded`：所有必需 artifact 已生成。
- `failed`：run 失败，错误写入 `run.json` 和事件。
- `canceling`：收到取消请求，等待后台任务协作退出。
- `canceled`：已取消。

## Artifact 管理方式

Artifact 是 Web 控制台读取文件的唯一入口，前端不直接拼接本地文件路径。

第一版 artifact registry 来源：

- 固定产物：`evidence.json`、`report.md`、`evaluation.json`。
- run metadata：`run.json`、`agents.json`、`events.jsonl`、`artifacts.json`。
- 截图：`screenshots/*`。
- browser-use history：建议后续复制到 run directory 下，例如 `browser-history/`。

访问规则：

- 只允许访问 run directory 内文件。
- `ArtifactService` 使用 resolved path 校验，防止路径穿越。
- `storage_state`、credential store、browser profile 文件不作为可下载 artifact。
- Markdown report 中引用的截图路径由后端转成 artifact URL。
- 对 legacy absolute screenshot path，第一版只在文件位于 run directory 内时展示；其他路径显示为 unavailable，并提示需要重新归档。

## CLI 兼容策略

必须保持现有 CLI 兼容：

- 不删除、不重命名现有 CLI 参数。
- `python -m prodwalk.cli run ...` 和 `prodwalk run ...` 行为保持不变。
- Web 后端复用 CLI 当前使用的底层函数和类，而不是让 CLI 调用 Web API。
- CLI 继续输出当前三个核心 artifact：`evidence.json`、`report.md`、`evaluation.json`。
- 新增的 `run.json`、`events.jsonl`、`agents.json`、`artifacts.json` 是 Web 增强元数据，不应成为 CLI 成功运行的必需条件。

中期建议：

- 从 `cli.py` 抽出 `RunOptions` 和 `create_walker_from_options` 到共享模块，但这应由后端实现阶段谨慎完成。
- 若抽共享模块，CLI 仍是 public interface，测试必须覆盖 CLI 参数兼容。

## 风险与取舍

- 事件粒度风险：当前 pipeline 没有 callback，第一版实时事件只能覆盖 stage 级，step 级可能在 scenario 完成后补发。
- 取消运行风险：browser-use 内部运行可能无法立即中断，第一版 cancel 是 best-effort。
- 本地浏览器状态风险：profile、storage state、credential store 是敏感本地状态，不能被 artifact API 暴露。
- 并发风险：browser-use 当前推荐 concurrency 为 1，Web 控制台第一版应限制 browser-use 并发。
- 旧 run 兼容风险：历史 run 没有 `run.json` 和 `events.jsonl`，只能推导静态状态。
- 路径风险：历史 evidence 可能引用临时绝对截图路径，后端必须拒绝任意绝对路径读取。
- 范围风险：如果第一版加入 plan 编辑器、credential UI、报告编辑器，会拖慢核心闭环。

## Phase 2/3/4 的开发建议

### Phase 2：后端 MVP

- 创建 `src/prodwalk/server`。
- 实现 health、plans、runs、events、artifacts、reports API。
- 支持 mock mode 从 Web 启动 run。
- 写入 `run.json`、`events.jsonl`、`agents.json`、`artifacts.json`。
- 支持 SSE。
- 支持读取历史 artifact。
- 为 RunService、EventStore、ArtifactService 增加单元测试。

### Phase 3：前端 MVP

- 创建 `apps/web`。
- 实现 Run Launcher、Run Detail、Agent Status、Event Stream、Report Viewer。
- 支持 mock mode 端到端。
- 支持 browser-use 参数配置，但 UI 上明确 local-only 和 verification 限制。
- 对 report markdown、evaluation、evidence 做只读展示。

### Phase 4：Pipeline Instrumentation

- 给 `ResearchDirector` 或其包装层增加事件 callback。
- 在 planner、walker、evidence、analyst、reviewer、report、evaluator 阶段发事件。
- 将 browser-use history 文件复制进 run directory。
- 将 step screenshot 全部归档并注册为 artifact。
- 增加更准确的 agent progress 和 scenario progress。
- 引入 SQLite 或 Postgres 仅在文件存储无法满足查询需求时进行。
