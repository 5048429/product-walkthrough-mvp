# Phase 1 Final Handoff

本文是 Phase 1 结束时给后续 agent 的最终交接。后续开发必须优先执行 `docs/frontend_console_mvp_spec.md`，早期技术/UX 文档只作为背景材料。

## 后续 agent 必须优先阅读的文件

按优先级阅读：

1. `docs/frontend_console_mvp_spec.md`
   - 唯一权威 MVP 规格。
   - 覆盖范围、不做范围、最终目录、最终 API、最终事件 schema、页面结构、数据流、开发顺序、文件边界、验收标准。

2. `docs/handoffs/phase1_final_handoff.md`
   - 当前文件。
   - 覆盖 Phase 2 任务拆分、不可偏离决策、仍未解决的问题。

3. `docs/api_event_contract.md`
   - 作为 API 和事件历史来源参考。
   - 若与 `frontend_console_mvp_spec.md` 不一致，以 `frontend_console_mvp_spec.md` 为准。

4. `docs/frontend_console_technical_spec.md`
   - 作为架构背景参考。

5. `docs/frontend_console_ux_spec.md`
   - 作为 UX 细节参考。

6. `docs/frontend_console_mvp_user_flows.md`
   - 作为用户路径参考。

7. `docs/handoffs/phase1_architecture_handoff.md` 和 `docs/handoffs/phase1_ux_handoff.md`
   - 作为 Phase 1 原始 handoff 背景。

## Phase 2 的任务拆分

Phase 2 的目标是打通本地 Web 控制台 mock mode 闭环，并为 browser-use 接入保留稳定边界。

### Task 2A：Backend Contract Skeleton

负责 agent：Backend API Agent。

交付：

- 创建 `src/prodwalk/server` 目录结构。
- FastAPI app、settings、CORS、route registry。
- `schemas.py` 中定义 final spec 的枚举、请求、响应和错误模型。
- 实现 `GET /api/health`。
- 建立统一错误响应格式。

验收：

- server 可启动。
- OpenAPI 中出现 final endpoint skeleton。
- 不修改现有 CLI 行为。

### Task 2B：Plan 和 Run Repository

负责 agent：Backend API Agent。

交付：

- `PlanService` 扫描 `examples/*.json`，读取 plan 详情，返回 parse error。
- `RunRepository` 读写 `run.json`、`agents.json`、`artifacts.json`。
- 扫描 `runs*` 历史目录，对缺少 `run.json` 的 run 做只读 summary 推断。
- 实现 `GET /api/plans`、`GET /api/plans/{plan_id}`、`GET /api/runs`、`GET /api/runs/{run_id}`。

验收：

- 能列出 example plans。
- 能列出历史 run。
- artifact 缺失时返回可解释状态，而不是崩溃。

### Task 2C：Event Store、SSE 和 Mock Run

负责 agent：Backend API Agent 或 Pipeline Adapter Agent。

交付：

- `EventStore` append/read `events.jsonl`。
- `EventBus` 支持内存 subscriber。
- `GET /api/runs/{run_id}/events` 支持 `after_seq`。
- `GET /api/runs/{run_id}/events/stream` 支持 SSE 和 heartbeat。
- `RunService` + `PipelineAdapter` 打通 `POST /api/runs` mock mode。
- 写入 run lifecycle events 和 stage/artifact events。

验收：

- 从 Web API 启动 mock run 后能看到事件持续写入。
- SSE 断线后可用 `after_seq` 补齐。
- mock run 完成后状态为 `succeeded`，失败时状态为 `failed` 且保留 events。

### Task 2D：Artifact、Evidence、Report、Evaluation API

负责 agent：Artifact / Evidence / Report Agent。

交付：

- `ArtifactService` 建立 artifact registry。
- path resolved 校验和敏感文件拒绝。
- 实现 artifacts、report、evidence、evaluation endpoints。
- normalized evidence list/detail。
- screenshot 只通过 artifact content 读取。

验收：

- `report.md` 可读，evaluation 缺失不阻塞 report。
- evidence detail 可从 `evidence.json` 得到。
- run directory 外绝对路径不可读。
- credential store、storage state、browser profile 不出现在 artifact list 中。

### Task 2E：Frontend App Shell 和 Dashboard

负责 agent：Frontend Shell Agent。

交付：

- 创建 `apps/web` Vite + React + TypeScript 项目。
- Router、providers、API client、contracts、SSE wrapper。
- App Shell、Side Navigation、Top Run Context Bar。
- Run Dashboard：Plan Selector、Run Launch Panel、Active Run Card、Recent Runs。
- Run History 基础表格。

验收：

- 默认打开是控制台工作台。
- 能选择 plan、启动 mock run、进入 active run context。
- 空状态和错误状态可读。

### Task 2F：Frontend Realtime、Evidence、Report

负责 agent：Frontend Realtime/Data Agent 和 Artifact / Evidence / Report Agent。

交付：

- Agent Status 页面。
- Live Event Log 页面和 filters。
- Evidence Viewer list/detail/screenshot preview。
- Report Preview Markdown/evaluation/copy。
- Run History 打开历史 run。

验收：

- SSE 新事件实时显示，断线显示 reconnecting。
- Evidence 与 Report 可以互相跳转。
- Missing screenshot 不影响 evidence 文本展示。
- Report not ready、partial report、artifact read failed 状态清晰。

### Task 2G：Browser-use 和 Manual Verification 最小接入

负责 agent：Pipeline Adapter Agent，必要时 Frontend Shell Agent 配合。

交付：

- API 和 UI 暴露 browser-use local-only 参数。
- 最多一个 active browser-use run。
- `awaiting_verification` 和 `run.awaiting_verification` 事件。
- `POST /api/runs/{run_id}/verification/confirm` 记录确认。

验收：

- browser-use 接入不影响 mock mode 验收。
- 前端清楚提示 local-only、manual verification 和可能需要回到终端的限制。

### Task 2H：QA 和 Regression

负责 agent：QA / Acceptance Agent。

交付：

- 后端单元测试：RunService、RunRepository、EventStore、ArtifactService。
- 前端基础渲染和 API 状态测试。
- mock run 端到端脚本或手工验收记录。
- CLI 兼容检查。

验收：

- mock run Web 闭环通过。
- CLI run 仍能按原方式使用。
- artifact 安全测试通过。

## 不允许偏离的关键决策

- `docs/frontend_console_mvp_spec.md` 是唯一权威规格。
- 第一版是本地单机控制台，不做 SaaS、多用户、权限或云端部署。
- 前端目录固定为 `apps/web`，技术栈为 React + Vite + TypeScript。
- 后端目录固定为 `src/prodwalk/server`，技术栈为 FastAPI。
- 必须保留现有 CLI 行为；不要让 CLI 依赖 Web server。
- Web 后端复用现有 prodwalk pipeline，不重写 `ResearchDirector`。
- 第一版使用文件存储，以 run directory 和 artifact 文件为事实来源，不引入 SQLite/Postgres。
- 新 Web run 元数据文件为 `run.json`、`agents.json`、`events.jsonl`、`artifacts.json`。
- 实时事件只使用 SSE，最终路径为 `/api/runs/{run_id}/events/stream`。
- 早期 `/api/runs/{run_id}/stream` 不再使用。
- 截图不走独立 screenshots endpoint，统一作为 artifact content 读取。
- 后端 canonical run status 使用 `queued`、`starting`、`running`、`awaiting_verification`、`blocked`、`finalizing`、`succeeded`、`failed`、`canceling`、`canceled`。
- 前端可以把 `succeeded` 展示为 `done`，但 API 不返回 `done`。
- mock mode 是 P0 端到端验收路径，browser-use 不得阻塞 mock mode 发布。
- browser-use 第一版最多一个 active run，细粒度 step telemetry 可以后置。
- artifact API 必须拒绝 run directory 外路径、credential store、storage state、browser profile。
- 前端不得直接拼接本地文件路径。
- 第一版不做 plan 编辑器、credential UI、report 富文本编辑、PDF/PPT/PRD 导出、evidence 标注、agent prompt 编辑。
- 后续 agent 必须遵守 `frontend_console_mvp_spec.md` 中的文件边界。

## 当前仍未解决的问题

- Web verification confirm 与当前 terminal `input()` / manual confirm 流程如何完全协同。MVP 可先记录 Web 确认并提示用户回到终端，后续再做 Web 驱动恢复。
- Pipeline callback 的最终深度尚未确定。MVP 先用 wrapper 发 stage 级事件；后续是否深入 `ResearchDirector`、walker、analyst 等内部 callback 需要实现阶段评估。
- 历史 run 中引用 run directory 外临时截图路径时是否迁移。当前决策是不读取任意外部路径，只显示 missing/unavailable；是否提供一次性迁移工具留待后续。
- browser-use history 文件何时强制归档到 `browser-history/`。MVP 建议归档新 run，旧 run 可只显示 artifact 不完整。
- 前端 UI 组件库未最终选择。实现可以先用轻量 CSS 和本地基础组件，避免组件库选择阻塞 MVP。
- 中文 report 的历史编码异常是否需要专门 UI 提示。MVP 可以先在 artifact read error 或 markdown unreadable 中暴露可解释错误，后续再做自动编码诊断。
- LLM provider/model、browser headless、max steps 等运行参数在 UI 中展示到什么深度。当前建议放在详情抽屉，不放在主流程。
