# Prodwalk Web 控制台 MVP 最终规格

本文是 Phase 1 规格整合后的唯一开发依据。后续 agent 如果发现本文与早期技术规格、UX 规格、用户路径或 handoff 存在冲突，必须以本文为准。

## MVP 范围

第一版是本地单机 Web 控制台，目标是把现有 prodwalk CLI 能力包装成可观察、可回放、可复核的内部工作台。它不是 SaaS，也不是新的 pipeline 实现。

MVP 必须交付：

- 前端使用 React + Vite + TypeScript，目录为 `apps/web`。
- 后端使用 FastAPI，目录为 `src/prodwalk/server`。
- 保留现有 CLI 行为，Web 后端复用现有 `ResearchDirector`、walker、report、evaluation、credential/auth-session 能力。
- 以 run directory 和 artifact 文件作为事实来源，第一版不引入数据库。
- 支持从 Web 选择本地 plan、启动 mock run、查看 run 状态、查看 agent/stage 状态、订阅实时事件、查看 evidence、查看 Markdown report、查看 evaluation、回看历史 run。
- mock mode 是第一条必须打通的端到端验收路径：不启动浏览器、不依赖外部网络、不读写 credential 明文，但必须生成 `evidence.json`、`report.md`、`evaluation.json`。
- browser-use mode 在 MVP 中保留 API 和 UI 参数入口，支持 local-only 状态展示和 manual verification 状态；细粒度 browser step telemetry 可以在后续 instrumentation 中增强。
- artifact 访问只能通过后端 API，前端不得直接拼接或读取本地路径。

## 明确不做范围

MVP 不做以下能力：

- 登录、多用户、权限、团队空间、云端部署、远程队列、定时任务。
- 数据库、跨机器同步、复杂审计日志或长期任务调度。
- plan 在线编辑器；第一版只选择和预览本地已有 plan。
- credential 管理 UI、secret 明文展示、storage state 下载、browser profile 浏览。
- 富文本 report 编辑器、PDF/PPT/PRD 自动导出。
- evidence 人工编辑、标注、Useful/Not useful、截图裁剪、批量 evidence 管理。
- 跨 run diff、批量删除、本地文件浏览器。
- agent prompt 编辑、agent 单步控制、人工接管浏览器。
- WebSocket；第一版实时更新只使用 SSE。
- 任意绝对路径 artifact 读取；run directory 外路径默认不可访问。
- 多个 browser-use run 并发执行；第一版最多允许一个 active browser-use run。

## 最终目录结构

本节定义后续实现目标目录。Phase 1 只创建文档，不创建实现目录。

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
          RunDashboardPage.tsx
          RunHistoryPage.tsx
          RunLauncher.tsx
          ActiveRunCard.tsx
          runQueries.ts
          runTypes.ts
        agents/
          AgentStatusPage.tsx
          AgentStatusTimeline.tsx
          AgentStatusCard.tsx
        events/
          LiveEventLogPage.tsx
          EventStream.tsx
          EventFilters.tsx
          EventDetailDrawer.tsx
        evidence/
          EvidenceViewerPage.tsx
          EvidenceList.tsx
          EvidenceDetailPanel.tsx
          ScreenshotPreview.tsx
        artifacts/
          ArtifactList.tsx
          ArtifactLink.tsx
          ArtifactPreview.tsx
        reports/
          ReportPreviewPage.tsx
          ReportOutline.tsx
          ReportViewer.tsx
          EvaluationSummary.tsx
      components/
        layout/
          AppShell.tsx
          SideNavigation.tsx
          TopRunContextBar.tsx
        ui/
          StatusBadge.tsx
          ErrorBanner.tsx
          EmptyState.tsx
          LoadingSkeleton.tsx
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

每个新 Web run 建议写入：

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
  browser-history/
```

`browser-history/` 可以后续补强；MVP 不要求所有历史 browser-use 文件都已迁移。

## 最终 API 契约

### 枚举

后端规范状态使用以下枚举。前端可以把 `succeeded` 展示为 `done`，把 `awaiting_verification` 和 `blocked` 展示为 `blocked`，但 API 不返回 `done`。

```json
{
  "RunStatus": [
    "queued",
    "starting",
    "running",
    "awaiting_verification",
    "blocked",
    "finalizing",
    "succeeded",
    "failed",
    "canceling",
    "canceled"
  ],
  "AgentStatus": [
    "pending",
    "running",
    "waiting",
    "succeeded",
    "failed",
    "skipped",
    "canceled"
  ],
  "AgentType": [
    "director",
    "planner",
    "walker",
    "evidence_extractor",
    "product_analyst",
    "competitive_analyst",
    "reviewer",
    "report_writer",
    "evaluator",
    "auth_session"
  ],
  "ArtifactType": [
    "run_manifest",
    "plan_json",
    "events_jsonl",
    "agents_json",
    "artifacts_json",
    "evidence_json",
    "report_markdown",
    "evaluation_json",
    "screenshot",
    "browser_history",
    "log_text"
  ]
}
```

### 基础对象

所有时间字段使用 ISO 8601 UTC 字符串。所有可选字段允许为 `null`。

```json
{
  "RunSummary": {
    "id": "run-20260616-101500",
    "status": "running",
    "mode": "mock",
    "research_goal": "Compare onboarding flows.",
    "run_dir": "runs/run-20260616-101500",
    "created_at": "2026-06-16T02:15:00Z",
    "started_at": "2026-06-16T02:15:01Z",
    "completed_at": null,
    "progress": {
      "total_scenarios": 6,
      "completed_scenarios": 2,
      "failed_scenarios": 0
    }
  }
}
```

```json
{
  "RunDetail": {
    "id": "run-20260616-101500",
    "status": "succeeded",
    "mode": "mock",
    "research_goal": "Compare onboarding flows.",
    "run_dir": "runs/run-20260616-101500",
    "created_at": "2026-06-16T02:15:00Z",
    "started_at": "2026-06-16T02:15:01Z",
    "completed_at": "2026-06-16T02:15:08Z",
    "progress": {
      "total_scenarios": 6,
      "completed_scenarios": 6,
      "failed_scenarios": 0
    },
    "params": {
      "mode": "mock",
      "concurrency": 3,
      "report_language": "zh"
    },
    "artifact_ids": ["art_evidence_json", "art_report_md", "art_evaluation_json"],
    "error": null
  }
}
```

```json
{
  "AgentExecution": {
    "id": "agent_walker_our-product_onboarding",
    "run_id": "run-20260616-101500",
    "type": "walker",
    "status": "running",
    "label": "BrowserWalker: Our Product / onboarding",
    "product": "Our Product",
    "scenario_id": "onboarding",
    "current_step": 2,
    "started_at": "2026-06-16T02:15:05Z",
    "updated_at": "2026-06-16T02:15:06Z",
    "completed_at": null,
    "metrics": {
      "step_count": 5,
      "completion_score": null
    },
    "error": null
  }
}
```

```json
{
  "Artifact": {
    "id": "art_report_md",
    "run_id": "run-20260616-101500",
    "type": "report_markdown",
    "title": "report.md",
    "path": "report.md",
    "media_type": "text/markdown; charset=utf-8",
    "size_bytes": 12070,
    "created_at": "2026-06-16T02:20:00Z",
    "metadata": {
      "language": "zh"
    }
  }
}
```

### 请求与响应

`POST /api/runs` 的 request body：

```json
{
  "config_path": "examples/research_plan.json",
  "plan": null,
  "mode": "mock",
  "out": "runs",
  "concurrency": 3,
  "report_language": "zh",
  "browser_model": null,
  "browser_max_steps": 25,
  "browser_timeout_sec": 600,
  "browser_user_data_dir": null,
  "browser_storage_state": null,
  "verification_mode": "off",
  "verification_timeout_sec": 300,
  "verification_success_url_contains": [],
  "verification_login_url_contains": "/auth/login"
}
```

规则：

- `config_path` 和 `plan` 二选一。
- `config_path` 第一版优先支持 `examples/` 下 plan；若支持任意路径，必须限制在 workspace 或显式允许目录内。
- `mode` 首批至少支持 `mock`；browser-use 支持不得破坏 mock path。
- `out` 默认 `runs`，必须做路径校验，不允许写到 workspace 外的任意位置。
- credential、storage state、browser profile 参数只作为后端运行参数，永不作为 artifact 暴露。

统一错误响应：

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run not found: run-unknown",
    "details": {
      "run_id": "run-unknown"
    },
    "request_id": "req_01HX..."
  }
}
```

错误码至少包含：

```text
BAD_REQUEST
PLAN_NOT_FOUND
PLAN_INVALID
RUN_NOT_FOUND
RUN_NOT_CANCELABLE
ARTIFACT_NOT_FOUND
ARTIFACT_FORBIDDEN
RUN_ALREADY_ACTIVE
SERVER_ERROR
```

### Endpoint 列表

最终 endpoint 以本列表为准。

```text
GET  /api/health
GET  /api/plans
GET  /api/plans/{plan_id}
POST /api/runs
GET  /api/runs
GET  /api/runs/{run_id}
POST /api/runs/{run_id}/cancel
POST /api/runs/{run_id}/verification/confirm
GET  /api/runs/{run_id}/agents
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/events/stream
GET  /api/runs/{run_id}/artifacts
GET  /api/runs/{run_id}/artifacts/{artifact_id}
GET  /api/runs/{run_id}/artifacts/{artifact_id}/content
GET  /api/runs/{run_id}/report
GET  /api/runs/{run_id}/evidence
GET  /api/runs/{run_id}/evidence/{evidence_id}
GET  /api/runs/{run_id}/evaluation
```

废弃早期草案中的 `GET /api/runs/{run_id}/stream` 和 `GET /api/runs/{run_id}/screenshots/{screenshot_id}`。实时事件统一走 `/events/stream`，截图统一作为 `screenshot` artifact 通过 `/artifacts/{artifact_id}/content` 读取。

Endpoint 职责：

- `GET /api/health`：返回服务健康状态、版本和当前时间。
- `GET /api/plans`：扫描可选本地 plan，首版优先扫描 `examples/*.json`。
- `GET /api/plans/{plan_id}`：读取 plan 原文和摘要；plan parse error 必须定位到字段。
- `POST /api/runs`：创建 run、写入 `run.json` 初始状态、启动后台任务、返回 `RunSummary`。
- `GET /api/runs`：扫描 Web run 和历史 run，返回分页 `RunSummary` 列表。
- `GET /api/runs/{run_id}`：返回 `RunDetail`。
- `POST /api/runs/{run_id}/cancel`：best-effort cooperative cancel。
- `POST /api/runs/{run_id}/verification/confirm`：记录用户已完成 visible browser 登录或验证；第一版可先与现有 terminal/manual confirm 并存。
- `GET /api/runs/{run_id}/agents`：返回 agent/stage 状态。
- `GET /api/runs/{run_id}/events`：按 `after_seq` 和 `limit` 返回持久化事件。
- `GET /api/runs/{run_id}/events/stream`：SSE 实时事件流，支持 `after_seq` 回放。
- `GET /api/runs/{run_id}/artifacts`：返回 artifact registry。
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`：返回单个 artifact 元数据。
- `GET /api/runs/{run_id}/artifacts/{artifact_id}/content`：返回 artifact 内容；JSON 返回 JSON，Markdown 返回文本，图片返回对应 image media type。
- `GET /api/runs/{run_id}/report`：返回 report markdown、evaluation 摘要、artifact id 和生成时间。
- `GET /api/runs/{run_id}/evidence`：返回 normalized evidence list、walkthrough results 和 artifact id。
- `GET /api/runs/{run_id}/evidence/{evidence_id}`：从 normalized evidence 中返回单条详情、关联 artifact、关联 event 和 finding。
- `GET /api/runs/{run_id}/evaluation`：返回 evaluation scores、overall_score 和 notes；缺失时不得阻塞 report markdown 展示。

## 最终事件 schema

事件是 append-only JSONL，同时用于 SSE 推送。`seq` 在单个 run 内严格单调递增，前端用 `seq` 去重和重连补齐。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://prodwalk.local/schemas/run-event.schema.json",
  "title": "RunEvent",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "run_id", "seq", "ts", "type", "level", "message"],
  "properties": {
    "id": {
      "type": "string"
    },
    "run_id": {
      "type": "string"
    },
    "seq": {
      "type": "integer",
      "minimum": 1
    },
    "ts": {
      "type": "string",
      "format": "date-time"
    },
    "type": {
      "type": "string"
    },
    "level": {
      "type": "string",
      "enum": ["debug", "info", "warn", "error"]
    },
    "message": {
      "type": "string"
    },
    "agent_id": {
      "type": ["string", "null"]
    },
    "agent_type": {
      "type": ["string", "null"],
      "enum": [
        "director",
        "planner",
        "walker",
        "evidence_extractor",
        "product_analyst",
        "competitive_analyst",
        "reviewer",
        "report_writer",
        "evaluator",
        "auth_session",
        null
      ]
    },
    "product": {
      "type": ["string", "null"]
    },
    "scenario_id": {
      "type": ["string", "null"]
    },
    "step_index": {
      "type": ["integer", "null"],
      "minimum": 1
    },
    "status": {
      "type": ["string", "null"]
    },
    "payload": {
      "type": "object",
      "additionalProperties": true
    },
    "artifact_ids": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  }
}
```

最终事件类型集合：

```text
run.created
plan.loaded
run.started
stage.started
stage.completed
agent.started
agent.status_changed
agent.completed
agent.failed
scenario.started
scenario.step.started
scenario.step.completed
scenario.completed
evidence.created
screenshot.archived
finding.created
artifact.created
report.generated
evaluation.generated
run.awaiting_verification
run.blocked
run.finalizing
run.completed
run.failed
run.canceled
```

P0 mock mode 可以只发送 stage 级和 artifact 级事件；step 事件允许在 scenario 完成后从 `WalkthroughResult.steps` 批量补发。

SSE 格式：

```text
id: 12
event: run.event
data: {"id":"evt_000012","run_id":"run-20260616-101500","seq":12,"ts":"2026-06-16T02:15:06Z","type":"artifact.created","level":"info","message":"Report artifact created","agent_id":"agent_report_writer","agent_type":"report_writer","product":null,"scenario_id":null,"step_index":null,"status":"finalizing","payload":{"artifact_type":"report_markdown"},"artifact_ids":["art_report_md"]}

```

Heartbeat：

```text
event: ping
data: {"time":"2026-06-16T02:15:07Z"}

```

事件安全规则：

- 事件不得包含 secret、token、credential 明文、storage state 内容。
- URL 可以出现，但不得把认证 token query 参数原样暴露；必要时由后端脱敏。
- `payload` 可以扩展，但稳定筛选字段必须保留在顶层。
- 写事件顺序必须是：append `events.jsonl`，更新内存状态，广播 SSE。

## 最终页面结构

控制台采用左侧导航、顶部 run context bar、主内容区。

最终 route 建议：

```text
/                         -> Run Dashboard
/dashboard                -> Run Dashboard
/runs                     -> Run History
/runs/:run_id             -> Run Detail default view
/runs/:run_id/agents      -> Agent Status
/runs/:run_id/events      -> Live Event Log
/runs/:run_id/evidence    -> Evidence Viewer
/runs/:run_id/report      -> Report Preview
```

左侧主导航：

- Run Dashboard
- Agent Status
- Live Event Log
- Evidence Viewer
- Report Preview
- Run History

顶部 run context bar：

- 当前 active run id。
- plan 名称或 research goal 摘要。
- mode、目标产品数、scenario 数。
- 状态 badge：idle、running、done、blocked、failed。
- started_at、elapsed、run_dir。
- 主操作：Start Mock Run、Start Browser Run、Stop、Retry、Open Report。

页面职责：

- Run Dashboard：Plan Selector、Run Launcher、Active Run Summary、Recent Runs、Evaluation Summary。
- Agent Status：pipeline 阶段 timeline、agent card、current step、blocked/failed reason、related events。
- Live Event Log：SSE event stream、filters、auto-scroll toggle、event detail drawer、artifact links。
- Evidence Viewer：evidence list、filters、detail panel、screenshot preview/gallery、raw data、linked findings/events。
- Report Preview：Markdown preview、outline、reviewer notes、evaluation panel、copy markdown、evidence citation links。
- Run History：history table、search/filter、artifact availability、run detail drawer。

空状态必须说明原因和下一步动作；错误状态必须保留 partial evidence/report 入口。

## 前后端数据流

### 启动 run

```text
User
  -> Run Dashboard / RunLauncher
  -> GET /api/plans
  -> GET /api/plans/{plan_id}
  -> POST /api/runs
  -> RunService.create_run
  -> write run.json, events.jsonl
  -> background PipelineAdapter
  -> frontend navigates to /runs/:run_id
```

### 实时状态

```text
Run page
  -> GET /api/runs/{run_id}
  -> GET /api/runs/{run_id}/agents
  -> EventSource /api/runs/{run_id}/events/stream?after_seq=N
  -> receive RunEvent
  -> append/dedupe local event list by seq
  -> refetch run/agents/artifacts on lifecycle and artifact events
```

### 产物读取

```text
Report Preview
  -> GET /api/runs/{run_id}/report
  -> GET /api/runs/{run_id}/evaluation

Evidence Viewer
  -> GET /api/runs/{run_id}/evidence
  -> GET /api/runs/{run_id}/evidence/{evidence_id}

Screenshot Preview
  -> GET /api/runs/{run_id}/artifacts/{artifact_id}/content
```

### 历史 run

```text
Run History
  -> GET /api/runs
  -> RunRepository scans runs* directories
  -> if run.json exists, use Web metadata
  -> if missing, infer read-only RunSummary from evidence/report/evaluation artifacts
```

### cancel 和 verification

```text
Stop
  -> POST /api/runs/{run_id}/cancel
  -> status canceling
  -> best-effort background task exit
  -> status canceled or failed

Manual verification
  -> run status awaiting_verification
  -> user completes visible browser login/challenge
  -> POST /api/runs/{run_id}/verification/confirm
  -> status running if backend can resume, otherwise record confirmation and show terminal/manual next step
```

## 开发顺序

后续实现必须按能够形成闭环的顺序推进：

1. 后端 contract skeleton：创建 FastAPI app、settings、routes、Pydantic schemas、统一错误响应。
2. RunRepository 与 PlanService：读取 plan、扫描历史 run、从 artifacts 推断只读 summary。
3. EventStore 与 EventBus：写入 `events.jsonl`，支持 `after_seq` 查询和 SSE。
4. RunService 与 PipelineAdapter：先打通 mock mode `POST /api/runs`，保留 CLI 行为。
5. ArtifactService：建立 registry，校验 resolved path，提供 report/evidence/evaluation/artifact content。
6. 后端测试：覆盖 RunService、EventStore、ArtifactService、history run 兼容和 path traversal。
7. 前端 app shell：Vite/React/TS、router、providers、API client、contracts、SSE wrapper。
8. Run Dashboard 与 Run History：plan selector、run launcher、active run、recent/history list。
9. Run Detail 实时面板：agent status、live event log、SSE reconnect、error/empty states。
10. Evidence Viewer 与 Report Preview：normalized evidence、screenshot artifact、Markdown report、evaluation。
11. Browser-use 参数入口与 verification 状态：local-only 提示、single active browser-use guard、manual verification UI。
12. 端到端验收：从 Web 启动 mock run，看到 events、agents、evidence、report、evaluation、history。

## 每个后续 agent 的文件边界

后续 agent 必须遵守文件边界，除非用户明确重新分配任务。

- Backend API Agent
  - 可修改：`src/prodwalk/server/**`、后端测试文件。
  - 可读取：`src/prodwalk/**`、`examples/**`、`runs*/**`。
  - 不修改：`apps/web/**`。
  - 不改变现有 CLI 参数和行为。

- Pipeline Adapter / Instrumentation Agent
  - 可修改：`src/prodwalk/server/services/pipeline_adapter.py`、`event_bus.py`、`event_store.py`、必要的 server tests。
  - 谨慎修改：`src/prodwalk/agents/**` 或 `src/prodwalk/cli.py`，只在明确需要抽共享逻辑时进行，并必须保留 CLI 兼容测试。
  - 不修改：前端页面和 UX 组件。

- Artifact / Evidence / Report Agent
  - 可修改：`src/prodwalk/server/services/artifact_service.py`、`run_repository.py`、`routes/artifacts.py`、`routes/reports.py`、相关测试。
  - 可修改对应前端功能时必须限定在 `apps/web/src/features/evidence/**`、`apps/web/src/features/artifacts/**`、`apps/web/src/features/reports/**`。
  - 不读取 run directory 外任意绝对路径。

- Frontend Shell Agent
  - 可修改：`apps/web/**`。
  - 不修改：`src/prodwalk/server/**`，除非只是同步由后端已确定的 generated/static contract 文件且任务明确要求。

- Frontend Realtime/Data Agent
  - 可修改：`apps/web/src/api/**`、`apps/web/src/features/agents/**`、`apps/web/src/features/events/**`、相关前端测试。
  - 必须使用 `/api/runs/{run_id}/events/stream`，不得使用废弃 `/stream` 路径。

- QA / Acceptance Agent
  - 可修改：测试、fixtures、文档中明确的验收记录。
  - 不做产品范围扩张，不引入数据库或新 UI 系统作为验收前置。

## 验收标准

### 后端验收

- `GET /api/health` 返回 ok。
- `GET /api/plans` 能列出至少一个 `examples/*.json` plan。
- `POST /api/runs` 使用 `mode=mock` 能创建 run directory，写入 `run.json` 和 `events.jsonl`。
- mock run 完成后生成或保留 `evidence.json`、`report.md`、`evaluation.json`。
- `GET /api/runs` 能列出新 run 和可推断的历史 run。
- `GET /api/runs/{run_id}/events` 支持 `after_seq`。
- `GET /api/runs/{run_id}/events/stream` 返回 `text/event-stream`，支持断线后用 `after_seq` 补齐。
- `GET /api/runs/{run_id}/artifacts` 返回 registry，content endpoint 能读取允许的 artifact。
- path traversal、run directory 外绝对路径、credential store、storage state、browser profile 均被拒绝。
- 现有 `python -m prodwalk.cli run ...` 和 `prodwalk run ...` 行为未被破坏。

### 前端验收

- 默认打开就是可用工作台，不是营销页。
- Run Dashboard 能选择 plan、查看摘要、启动 mock run。
- 启动后能进入 active run context，顶部 bar 显示 run id、mode、status、elapsed。
- Live Event Log 能展示历史事件和 SSE 新事件，支持 reconnect 状态和 filters。
- Agent Status 能展示阶段型 agent 状态，blocked/failed 有明确原因入口。
- Evidence Viewer 能展示 evidence list/detail；截图缺失时展示 Missing screenshot 而不隐藏 evidence。
- Report Preview 能渲染 Markdown、展示 evaluation、复制 Markdown，并能从 evidence id 跳转到 Evidence Viewer。
- Run History 能打开历史 run 的 report/evidence/evaluation，artifact 缺失时显示 unavailable。
- 空状态和错误状态符合 UX 规格，不吞掉 partial artifacts。

### 端到端验收

- 在无外部网络、无浏览器、无 credential 的环境中，mock mode 能从 Web 启动并完成。
- 用户能从一次 mock run 看到：run created、run started、stage/agent events、artifact/report/evaluation events、run completed。
- 用户能在同一个 active run 上从 Dashboard 跳到 Event Log、Evidence Viewer、Report Preview，并保持上下文。
- 刷新页面后仍能从后端恢复 run summary、events、artifacts。
- 所有新增能力只依赖 `docs/frontend_console_mvp_spec.md` 和 `docs/handoffs/phase1_final_handoff.md` 的决策。
