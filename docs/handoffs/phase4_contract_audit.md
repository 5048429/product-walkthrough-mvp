# Phase 4 Contract Audit Handoff

## Scope

本审计在真实前后端联调前完成，覆盖：

- Phase 1/2 API 与事件契约文档：`docs/frontend_console_mvp_spec.md`、`docs/api_event_contract.md`
- Phase 2 后端交接：`docs/handoffs/phase2_final_handoff.md`
- Phase 3 前端交接：`docs/handoffs/phase3_final_handoff.md`
- 前端类型与 mock：`apps/web/src/types/contracts.ts`、`apps/web/src/api/*`、`apps/web/src/mock/*`
- 后端 FastAPI 实现：`src/prodwalk/server/app.py`、`src/prodwalk/server/models.py`、`src/prodwalk/server/runtime.py`

本次只做审计和文档，没有修改 `apps/web` 或 `src/prodwalk/server`。

## Executive Summary

Phase 4 可以先接通 mock-mode 的核心闭环：plans、create run、run detail、agents、events/SSE、artifacts、report、evidence、evaluation。后端真实 SSE 字段形状与 RunEvent schema 基本一致，且前后端都使用最终 `/api/runs/{run_id}/events/stream` URL。

主要联调风险集中在三类：

1. 契约列出的部分路由后端尚未实现：`POST /cancel`、`POST /verification/confirm`、`GET /evidence/{evidence_id}`。
2. evidence 仍是原始 `EvidenceItem` 形状，尚未归一化为前端 mock/最终契约里的 `screenshot_artifact_id`、`errors`、`final_output` 等字段，并可能暴露本地 screenshot/storage 路径。
3. 前端把 run/agent `error` 定义成 `string | null`，后端真实返回是对象或 null，失败态直接渲染会有运行时风险。

## API 对齐表

| API | 最终契约 | 后端实际 | 前端当前 | 对齐结论 |
| --- | --- | --- | --- | --- |
| `GET /api/health` | 返回 `ok/service/version/time` | 已实现，匹配 | client 未正式接入页面 | OK |
| `GET /api/plans` | `{ items: PlanSummary[] }` | 已实现；额外返回 `name` | `PlanSummary` 没有 `name`，mock 也没有 | OK，额外字段兼容；前端可选加 `name?: string` |
| `GET /api/plans/{plan_id}` | `{ id,path,plan }` | 已实现；额外返回 `name`；path 参数名为 `name` | `getPlan(encodeURIComponent(planId))` | OK；`examples/foo.json` 经过编码后可被 path route 解析 |
| `POST /api/runs` | request 使用 `config_path`/`plan` 二选一；response 至少含 `run` | 已实现；只接受 `mode="mock"`；response 额外有 `run_id/status/created_at/*_url` | `RunCreateResponse` 只声明 `{ run }` | mock path OK；browser-use 直接发会 400 |
| `GET /api/runs` | `{ items,next_cursor }` RunSummary 列表 | 已实现；历史 run 可推断 `mode: "unknown"` | `RunMode` 只允许 `"mock" | "browser-use"` | 需处理 `unknown`，否则历史 run 类型不真实 |
| `GET /api/runs/{run_id}` | `{ run: RunDetail }` | 已实现 | 类型基本匹配 | `error` 类型不一致：后端对象，前端 string |
| `POST /api/runs/{run_id}/cancel` | 返回 `{ run_id,status,accepted }` | 未实现 | `client.cancelRun()` 已写好 | 阻塞 Stop 接入 |
| `POST /api/runs/{run_id}/verification/confirm` | 返回 `{ run_id,status,accepted }` | 未实现 | `client.confirmVerification()` 已写好 | 阻塞 manual verification 接入 |
| `GET /api/runs/{run_id}/agents` | `{ items: AgentExecution[] }` | 已实现 | 类型基本匹配 | `error` 类型不一致：后端对象，前端 string |
| `GET /api/runs/{run_id}/events` | `{ items,last_seq }`，支持 `after_seq/limit` | 已实现；Accept 含 `text/event-stream` 时也会走 SSE | `getEvents()` 已写好 | OK |
| `GET /api/runs/{run_id}/events/stream` | SSE `run.event` + `ping` | 已实现 | `openRunEventStream()` 使用最终 URL | OK |
| `GET /api/runs/{run_id}/artifacts` | `{ items: Artifact[] }` | 已实现；当前仅构建 8 个核心 artifact | `getArtifacts()` 已写好 | OK；截图 artifact 尚未归档 |
| `GET /api/runs/{run_id}/artifacts/{artifact_id}` | `{ artifact }` | 已实现 | `getArtifact()` 已写好 | OK |
| `GET /api/runs/{run_id}/artifacts/{artifact_id}/content` | JSON/text/image 按媒体类型返回 | 已实现 | `ArtifactLink` 使用该 URL | OK |
| `GET /api/runs/{run_id}/report` | markdown + evaluation 摘要 | 已实现；不返回 `artifacts` | `ReportResponse.artifacts?` 可选 | OK |
| `GET /api/runs/{run_id}/evidence` | normalized evidence list | 已实现但返回原始 evidence 形状，并额外返回 `plan/scenarios` | `EvidenceResponse` 假设 normalized/mock 形状 | 需后端归一化或前端兼容转换 |
| `GET /api/runs/{run_id}/evidence/{evidence_id}` | 单条 evidence detail | 未实现 | client 也未实现 | 阻塞 evidence 深链/detail endpoint |
| `GET /api/runs/{run_id}/evaluation` | `{ run_id,artifact_id,scores,overall_score,notes }` | 已实现 | `EvaluationResponse` 匹配 | OK |

## Phase 4 前端要接的接口

P0 mock E2E 先接：

- `GET /api/plans`
- `GET /api/plans/{plan_id}`
- `POST /api/runs`，只发送 `mode: "mock"`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/agents`
- `GET /api/runs/{run_id}/events?after_seq=N&limit=100`
- `GET /api/runs/{run_id}/events/stream?after_seq=N`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}/content`
- `GET /api/runs/{run_id}/report`
- `GET /api/runs/{run_id}/evidence`
- `GET /api/runs/{run_id}/evaluation`

暂缓或 gated 接入：

- `POST /api/runs/{run_id}/cancel`：后端未实现，Stop 按钮不能直接接。
- `POST /api/runs/{run_id}/verification/confirm`：后端未实现，manual verification 不能直接接。
- `GET /api/runs/{run_id}/evidence/{evidence_id}`：后端和前端 client 都未实现，可先用 `/evidence` 列表中的 item 做本地 detail。
- `POST /api/runs` with `mode: "browser-use"`：后端当前返回 400。Start Browser Run 需要禁用、标为 local-only placeholder，或等待后端实现。

## RunEvent 字段对齐表

| 字段 | 契约要求 | 前端类型 | 后端 SSE/JSONL 实际 | 对齐结论 |
| --- | --- | --- | --- | --- |
| `id` | required string | required string | `evt_000001` 递增格式 | OK |
| `run_id` | required string | required string | 当前 run id | OK |
| `seq` | required integer, >= 1 | required number | 单 run 内单调递增 | OK |
| `ts` | required date-time | required string | `utc_now()` ISO 字符串，可能是 `+00:00` 而非 `Z` | OK，前端用 Date parse 即可 |
| `type` | required string；最终事件集合见契约 | `RunEventType | string` | dot-style，如 `run.created`、`agent.started` | OK |
| `level` | `debug/info/warn/error` | 同契约 | 默认 `info`，blocked/error 用 warn/error | OK |
| `message` | required string | required string | 已填充 | OK |
| `agent_id` | optional/null string | optional/null | 后端总是输出字段，可能为 null | OK |
| `agent_type` | optional/null AgentType | optional/null | 后端总是输出字段，可能为 null | OK |
| `product` | optional/null string | optional/null | 后端总是输出字段，可能为 null | OK |
| `scenario_id` | optional/null string | optional/null | 后端总是输出字段，可能为 null | OK |
| `step_index` | optional/null integer | optional/null | 后端总是输出字段，当前 mock 通常为 null | OK |
| `status` | optional/null string | optional/null string | 后端总是输出字段，生命周期状态或 agent 状态 | OK |
| `payload` | object | optional object | 后端总是输出对象，默认 `{}` | OK |
| `artifact_ids` | string array | optional array | 后端总是输出数组，默认 `[]` | OK |

SSE frame 与契约一致：

```text
id: <seq>
event: run.event
data: <RunEvent JSON>

event: ping
data: {"time":"..."}
```

## RunEvent 类型集合差异

前端 mock 包含较丰富的事件：`plan.loaded`、`scenario.step.started`、`scenario.completed`、`evidence.created`、`finding.created`、`run.awaiting_verification` 等。

后端当前 mock run 实测事件类型集合为：

```text
agent.completed
agent.started
artifact.created
evaluation.generated
report.generated
run.completed
run.created
run.finalizing
run.started
stage.completed
stage.started
```

失败路径可输出 `run.failed`；blocked walker 会输出 `agent.status_changed`。当前后端不会在 mock path 输出：

- `plan.loaded`
- `agent.failed`
- `scenario.started`
- `scenario.step.started`
- `scenario.step.completed`
- `scenario.completed`
- `evidence.created`
- `screenshot.archived`
- `finding.created`
- `run.awaiting_verification`
- `run.blocked`
- `run.canceled`

结论：字段 schema 对齐，事件类型是子集。前端事件日志不能依赖 mock 数据里那些细粒度事件一定存在；只能把它们当可选增强。

## 前端当前 mock 类型和后端真实类型差异

| 对象 | 前端 mock/TS 当前假设 | 后端真实返回 | 风险 |
| --- | --- | --- | --- |
| `RunDetail.error` | `string | null` | `dict/object | null` | 失败态渲染 object 会出错 |
| `AgentExecution.error` | `string | null` | `dict/object | null` | `AgentStatusCard` 直接渲染 object 会出错 |
| `RunSummary.mode` | `"mock" | "browser-use"` | 新 run 是 `"mock"`；历史推断 run 可为 `"unknown"` | 历史列表运行时值超出 TS union |
| `PlanSummary` | 无 `name` | 有 `name` | 兼容；可选补充 |
| `RunCreateResponse` | 只声明 `{ run }` | 还有 `run_id/status/created_at/events_url/report_url/evidence_url/evaluation_url` | 兼容；前端可利用 top-level URL |
| `Artifact[]` | mock 有 screenshot artifact | 后端当前只自动注册 8 个核心 artifact | Screenshot UI 应保留 missing state |
| `EvidenceResponse` | mock 带 `artifacts?` | 后端不带 `artifacts`，但带 `plan/scenarios` | 兼容一部分；artifact 链接需另取 `/artifacts` |
| `EvidenceItem` | `product_kind/scenario_title/status/step_index/action/screenshot_artifact_id/errors/final_output/finding_ids` 等扁平字段 | 原始模型只有 `id/product/scenario_id/kind/title/summary/url/screenshot/data/confidence/created_at` | 需要归一化，否则 detail/screenshot/error 展示会缺字段 |
| `EvidenceItem.screenshot_artifact_id` | 前端以 artifact id 访问截图 | 后端 raw evidence 是 `screenshot` 本地路径，且 `data.screenshot_paths` 也可能含绝对路径 | 违反“artifact 只能经 API 访问”的边界，需要后端修 |
| `ReportResponse.artifacts` | mock 带 `artifacts` | 后端不带 | 前端类型可选，OK |
| `ReportResponse.language` | string | 新 run 有值；历史 run 可能为 null | 前端需防御 |
| `EvaluationResponse` | scores/overall_score/notes | 匹配 | OK |

## 状态枚举对齐

- `RunStatus`：前端、后端 `models.py`、`frontend_console_mvp_spec.md` 都包含 `blocked`。但 `docs/api_event_contract.md` 顶部旧枚举遗漏了 `blocked`。Phase 4 应以最终 MVP spec 和代码为准。
- `AgentStatus`：前后端一致。
- `AgentType`：前后端一致。
- `ArtifactType`：前后端一致。
- `RunMode`：前端定义 `"mock" | "browser-use"`；后端 request 接受 string 但实际只支持 `"mock"`，历史 run 可能返回 `"unknown"`。这是当前最明显的 mode 枚举不一致。
- `ConsoleStatus` 是前端展示态，不应作为后端 API 状态发送；前端 `done` 需要继续映射为 API `succeeded`。

## URL 对齐

已对齐：

- 前端 SSE 使用 `/api/runs/{run_id}/events/stream`，后端已实现。
- 前端 artifact link 使用 `/api/runs/{run_id}/artifacts/{artifact_id}/content`，后端已实现。
- 前端没有使用废弃的 `/api/runs/{run_id}/stream`。

不对齐或缺失：

- 前端 client 已有 `/api/runs/{run_id}/cancel`，后端缺 route。
- 前端 client 已有 `/api/runs/{run_id}/verification/confirm`，后端缺 route。
- 最终契约要求 `/api/runs/{run_id}/evidence/{evidence_id}`，后端缺 route，前端 client 也缺 method。
- `POST /api/runs` 的 browser-use mode UI 入口与后端实际能力不一致，后端当前只支持 mock。

## 需要前端修改的文件

P0 接真实 mock backend：

- `apps/web/src/pages/ConsolePage.tsx`
  - 替换 `mockConsoleData` 为真实 API state orchestration。
  - 维护 active run id、last event seq、SSE connection state。
  - lifecycle/artifact event 后 refetch run/agents/artifacts/report/evidence/evaluation。
- `apps/web/src/api/client.ts`
  - 解析统一错误响应 `ApiErrorPayload`，不要只抛 generic HTTP error。
  - 在后端 route 未实现前 gate `cancelRun`、`confirmVerification`。
  - 后端实现后补 `getEvidenceDetail(runId, evidenceId)`。
- `apps/web/src/api/sse.ts`
  - 接入页面状态后按 `seq` 去重。
  - reconnect 时使用 `after_seq`。
  - 保留 `run.event` 监听；`ping` 不需要进入事件列表。
- `apps/web/src/types/contracts.ts`
  - `RunDetail.error`、`AgentExecution.error` 改为结构化类型或 `unknown/string` union。
  - `RunMode` 增加 `"unknown"` 或前端转换历史 run mode。
  - `PlanSummary.name?: string` 可选补齐。
  - `EvidenceItem` 要么匹配后端 raw shape，要么定义 normalized shape 并在 API layer 转换。
  - `ReportResponse.language`、`EvidenceResponse.report_language/created_at` 建议允许 null，兼容历史 run。
- `apps/web/src/components/runs/RunStartPanel.tsx`
  - `Start Mock Run` 调 `prodwalkApi.createRun()`。
  - Browser Run 按后端能力禁用或显示 local-only/manual placeholder。
- `apps/web/src/components/layout/TopRunContextBar.tsx`
  - Stop/Retry/Open actions 接真实状态；Stop 在后端 cancel route 未实现前禁用。
- `apps/web/src/components/agents/AgentStatusCard.tsx`
  - 不要直接渲染 `agent.error` object；统一格式化错误。
- `apps/web/src/components/events/EventLog.tsx`
  - 真实事件类型是子集，filter 不能假设 scenario/evidence/finding 事件一定存在。
- `apps/web/src/components/evidence/EvidenceList.tsx`
- `apps/web/src/components/evidence/EvidenceItemCard.tsx`
  - 兼容后端 raw `screenshot`/`data` 或等待后端 normalized evidence。
  - 截图只能通过 artifact content URL 打开；不要使用 raw local path。
- `apps/web/src/components/reports/ReportPreview.tsx`
- `apps/web/src/components/reports/ReportToolbar.tsx`
  - 兼容 report 有 markdown 但 evaluation 缺失的情况。
- `apps/web/src/components/common/ArtifactLink.tsx`
  - 路径是正确的；继续只用 backend content endpoint。
- `apps/web/src/api/mockConsoleData.ts`、`apps/web/src/mock/*`
  - 可保留作 fallback fixture，但不要再驱动默认页面状态。

## 需要后端修改的文件

P0/P1 后端联调修复建议：

- `src/prodwalk/server/app.py`
  - 增加 `POST /api/runs/{run_id}/cancel`。
  - 增加 `POST /api/runs/{run_id}/verification/confirm`。
  - 增加 `GET /api/runs/{run_id}/evidence/{evidence_id}`。
  - 给 list/create/report/evidence endpoints 补 response model 时要先处理当前真实 shape。
- `src/prodwalk/server/models.py`
  - 定义 `RunActionResponse`、`VerificationConfirmRequest`、`EvidenceResponse`、`EvidenceDetailResponse`、normalized `EvidenceItem`。
  - 明确 `RunDetail.error`、`AgentExecution.error` 是 object/null，或统一改成 string/null。
  - 明确 `RunMode` 是否包含 `unknown`；如果不包含，后端历史 run 要映射为 `mock` 或其他可展示值。
- `src/prodwalk/server/runtime.py`
  - 实现 cancel 状态流转：`canceling` -> `canceled`/`failed`，并发 `run.canceled`。
  - 实现 verification confirm 的记录和状态返回。
  - `read_evidence()` 做 normalized response，不直接透传 raw screenshot/storage/user_data_dir 路径。
  - 将 screenshot 文件注册为 `screenshot` artifact，并把 evidence 映射到 `screenshot_artifact_id`。
  - 对 browser-use local 路径、storage state、user data dir、history file 做脱敏或移除。
  - 如要满足完整事件 UX，可补 `plan.loaded`、scenario/step、`evidence.created`、`finding.created`、`agent.failed` 事件；mock P0 不强制。

## 阻塞问题

1. 后端缺 `POST /api/runs/{run_id}/cancel`，前端 Stop 无法真实接入。
2. 后端缺 `POST /api/runs/{run_id}/verification/confirm`，manual verification flow 无法真实接入。
3. 后端缺 `GET /api/runs/{run_id}/evidence/{evidence_id}`，最终契约的 evidence detail/deep link 不完整。
4. Evidence schema 未归一化：后端返回 raw `screenshot` 和 `data`，前端 mock/类型期待 `screenshot_artifact_id` 等 normalized 字段。
5. 后端 evidence 可能暴露本地绝对路径或 browser runtime 参数，不符合 artifact 访问安全边界。
6. `RunDetail.error` 和 `AgentExecution.error` 类型前后端不一致，失败态 UI 直接渲染 object 会报错。
7. Browser Run UI mode 与后端能力不一致；后端当前 `POST /api/runs` 只支持 `mode="mock"`。

## 非阻塞问题

1. `POST /api/runs` response 顶层多出 `run_id/status/created_at/*_url`，前端当前可忽略。
2. `PlanSummary` 后端多出 `name`，前端当前可忽略。
3. 后端实际 mock 事件类型是最终事件集合的子集，Live Event Log 可正常显示，但不要依赖 scenario/evidence/finding 事件。
4. `docs/api_event_contract.md` 旧 RunStatus 列表遗漏 `blocked`，与最终 spec 和代码冲突；按最终 spec 处理即可。
5. `ts` 字段可能是 `+00:00` 形式而不是 `Z`，仍是合法 ISO 8601 UTC。
6. `ReportResponse`/`EvidenceResponse` 后端不附带 `artifacts`，前端可另调 `/artifacts`。
7. `GET /api/runs/{run_id}/events` 在 Accept 为 `text/event-stream` 时也会返回 SSE，这是额外兼容行为，不影响 JSON client。
8. 前端 `requestJson()` 目前不解析统一错误 payload，会影响错误 UI 质量，但不阻塞 happy path。

## Recommended Phase 4 Order

1. 前端先接 plans + create mock run + poll run detail，保证从页面能启动 mock run。
2. 接 persisted events，再接 SSE；以 `seq` 去重并维护 `last_seq`。
3. 接 agents/artifacts/report/evaluation。
4. 接 evidence 前先决定：后端先 normalized，或前端做临时 adapter。建议后端先修，避免本地路径泄露。
5. 后端补 cancel/verification/evidence detail 后，再接 Stop、manual verification、evidence deep link。
6. Browser-use UI 保持 gated，直到后端明确支持真实 browser-use API path。
