# Phase 6 UI Simplification Audit

## Scope

本审计面向 `apps/web` 当前前端界面，目标是把 Phase 5 已完成的本地 Web 控制台，从“工程调试台”收敛成“产品经理工作台”。

本轮只做审计和方案，不修改前端代码，不接入 browser-use。

已阅读依据：

- `docs/frontend_console_zh.md`
- `docs/frontend_console_mvp_spec.md`
- `docs/frontend_console_ux_spec.md`
- `docs/handoffs/phase5_final_handoff.md`
- `apps/web/src/pages/ConsolePage.tsx`
- `apps/web/src/components/**`

## 当前 UI 问题

当前界面功能闭环完整，但默认暴露的信息过多。`ConsolePage` 把 Run Start、Run History、Evaluation、Agent Status、Live Event Log、Report Preview、Evidence 全部同时铺开，首屏更像排障驾驶舱，而不是 PM 做研究复核的工作台。

主要问题：

- 默认可见区域太多：左侧启动、历史、评分，中间 agent，右侧事件，底部报告和证据全部展开，用户需要先理解系统结构才能开始工作。
- 技术状态占据核心位置：`Source`、`SSE open/closed`、`Retry API`、`Mock fallback`、`Run dir`、artifact id、`evaluation.json`、`report.md` 等默认出现，偏向工程诊断。
- 启动区过度暴露 API 参数：`RunStartPanel` 默认展示 `API request / Mock request` 全量 payload，包括 `browser_timeout_sec`、`browser_storage_state`、`verification_success_url_contains` 等 PM 不需要日常看到的字段。
- Mock fallback 调试控件默认可见：`idle/running/done/blocked/failed` 状态切换器只适合开发预览，不应出现在产品经理默认工作台。
- browser-use 入口过于前置：Phase 5 已确认 Web browser-use run creation 仍 gated，但当前顶部和启动面板都有 `Start Browser`，容易让用户以为已可用。
- Agent 面板默认太细：`AgentStatusCard` 展示 current step、step count、started、heartbeat、completion 等细节，适合作为运行详情，不适合作为默认主视图。
- Event Log 默认太工程化：事件类型、seq、agent id/type、payload 摘要、artifact tokens、SSE 状态和多组筛选默认占据右栏。PM 需要的是“发生了什么”和“是否需要处理”，不是原始事件流。
- Report 与 Evidence 都在底部半高区域，弱化了完成后最重要的 PM 产物：报告阅读、证据核对和评估判断。
- History 面板显示 artifact availability 和 screenshot count 是有价值的，但默认展示 `Report yes / Evidence yes / Evaluation yes` 等工程标签，缺少“打开报告 / 查看证据 / 复用此 run”的任务导向。
- Evaluation 重复出现：左侧独立 `EvaluationSummary` 和 `ReportPreview` 内部 Evaluation 区域都可见，信息重复。
- 缺少清晰主路径：PM 的默认路径应是选择 plan -> 启动 mock run -> 看进度 -> 读报告 -> 查证据 -> 回看历史；当前页面没有把这条路径排成视觉优先级。

## 必须保留的功能

这些能力属于 MVP 和 Phase 5 已验收闭环，简化时必须保留：

- 选择本地 plan，并展示 plan 的 PM 可理解摘要：research goal、产品数、场景数、报告语言。
- 启动 mock run，这是第一条必须稳定的端到端路径。
- 显示 active run 的核心状态：run id、plan/research goal、mode、status、elapsed、进度。
- 恢复或选择历史 run，并能查看历史 report、evidence、evaluation。
- 显示当前 run 的阶段进度，至少能回答：运行到哪一步、是否 blocked/failed、下一步是否需要用户操作。
- 保留 SSE 实时更新能力，但默认呈现为简化活动流或状态更新。
- 保留完整 Live Event Log，作为“详情/调试信息”中的可展开视图。
- 保留 Agent Status，但默认展示阶段摘要，细节放入详情。
- 保留 Report Preview，且完成后应成为默认最重要内容。
- 保留 Evidence Viewer，包括搜索、筛选、截图缺失状态、详情查看、artifact 安全链接。
- 保留 Evaluation，但默认展示 overall score 和关键指标摘要，详细 notes/score list 可折叠。
- 保留 partial artifacts 策略：blocked/failed 时不能隐藏已经可读的 report/evidence/evaluation。
- 保留 artifact API 访问路径，不允许前端直接读取本地路径。
- 保留空状态和错误状态说明，并继续区分 idle/running/done/blocked/failed。

## 默认隐藏的功能

以下内容不应在默认工作台首屏直接出现，应折叠到“详情”或“调试信息”：

- API health/version/source banner 的详细文本。
- `Source`、`SSE connecting/open/closed/error` 的原始连接状态；默认只保留小型连接提示或异常提示。
- `Retry API`，除非 API 不可用或用户打开调试信息。
- `Mock fallback` 说明和 mock 状态切换器。
- `API request / Mock request` payload 全量字段。
- `browser_model`、`browser_max_steps`、`browser_timeout_sec`、`browser_user_data_dir`、`browser_storage_state`、verification URL 参数等高级启动参数。
- `Run dir`，默认隐藏到 run details。
- artifact id、artifact path、media type、size、`events.jsonl`、`agents.json`、`artifacts.json`、`evaluation.json` 原始链接。
- Event Log 原始字段：seq、agent id、payload key/value、artifact tokens、status filter、agent filter。
- Agent heartbeat、started timestamp、step count、raw metrics、agent id。
- Evidence 的 `Sanitized Data`、raw final_output、artifact ids、history_file/raw path。
- Report 中的下载 `report.md` 可以保留为次级操作；`evaluation.json` 链接默认隐藏。
- 历史 run 的 screenshot count 和 artifact availability 原始 yes/no 标签，默认改为更任务化的可用状态。

## 建议的新布局

建议从固定五区调试台改为“单主线 + 可切换工作区”的 PM 工作台。

### 页面骨架

- 顶部：Run Context Bar，保留品牌、当前 plan/run、状态、进度、主操作。
- 左侧或顶部次导航：Dashboard、Report、Evidence、History、Details。
- 主区：默认显示 Dashboard；run 完成后可自动突出 Report。
- 详情抽屉或折叠区：Agent details、Event log、API/debug、Artifacts。

### 默认 Dashboard

Dashboard 只回答 PM 首屏最关心的四件事：

- 要跑什么：Plan selector + plan 摘要。
- 现在怎样：Active run summary + status + progress + blocker/failure 摘要。
- 结果在哪：Report / Evidence / Evaluation 快捷入口。
- 最近跑过什么：Recent runs 简化列表。

建议结构：

```text
Top Context Bar
  - Prodwalk
  - selected plan / active run
  - status, elapsed, progress
  - Start Mock Run, Stop/Retry when applicable, Open Report when ready

Main Dashboard
  - Start a run
    - plan selector
    - primary Start Mock Run
    - advanced options collapsed
  - Active run
    - research goal
    - progress
    - current phase
    - evidence/report/evaluation availability
  - Results
    - Report card
    - Evidence card
    - Evaluation score card
  - Recent runs
    - compact list with Open Report / Evidence actions
```

### Report 页面

Report 应是完成后的主产物页面：

- 默认展示 Markdown 渲染内容。
- 右侧保留 Outline 和 Evaluation 摘要。
- Copy Markdown 保留。
- Download report.md 作为次级操作。
- evaluation.json 原始 artifact 链接折叠到 Details。

### Evidence 页面

Evidence 保留强检索能力，但默认减少字段：

- 顶部：evidence count、产品/场景筛选、搜索。
- 左侧：evidence list，默认显示 title、product、scenario、confidence、screenshot 状态。
- 右侧：selected evidence detail，默认显示 summary、URL、screenshot、关联 finding。
- Raw data、artifact ids、final_output 放入折叠详情。

### History 页面

History 应替代手动翻 run 目录：

- 默认列表显示 run id、创建时间、research goal、status、mode、score、report/evidence 可用状态。
- 提供搜索和状态筛选。
- 每条 run 的主动作是 Open Report，其次是 Evidence 和 Details。
- artifact availability 原始信息折叠到 run details。

### Details / Debug 页面

把工程视图集中放在一个明确位置：

- Agent Status full board。
- Live Event Log full stream。
- API request payload。
- Source/API health/SSE state。
- Artifact links and raw JSON files。
- Mock fallback controls，仅在 fallback 或开发预览模式出现。

## 需要删除/合并/折叠的组件

### `ConsolePage.tsx`

- 需要重组：不要把 left/main/right/bottom 全部默认铺开。
- 建议改为 route/tab 驱动的主内容区：Dashboard、Report、Evidence、History、Details。
- Agent 和 Event 默认进入 Details，不作为首屏主栏。

### `AppShell`

- 需要从三列固定工作台改成产品工作台壳。
- 保留 top bar。
- 新增导航区或 tab 区。
- 主内容区一次只突出一个工作任务。

### `TopRunContextBar`

- 保留，但简化默认字段。
- 默认显示：plan/run、status、progress/elapsed、Start Mock、Stop/Retry/Open Report。
- 折叠：source、connection state、run dir。
- `Start Browser` 在 browser-use 未闭环前应放入 Advanced 或置为 disabled 并说明“待联调”。
- `Retry API` 默认只在 API 错误或 Debug 中显示。

### `RunStartPanel` / `RunLauncher`

- 保留启动 mock run 的能力。
- 合并 `PlanSelector`、核心 mode、report language 为简洁启动卡。
- 默认只显示 Start Mock Run。
- Advanced options 折叠：mode、concurrency、browser max steps、verification。
- 删除或折叠 `API request / Mock request` payload。
- Mock fallback 状态切换器只允许在 Debug/Fallback 模式显示。

### `RunModeSelector`

- 默认不应直接展示 browser-use 和 verification 细节。
- 保留为 Advanced launch options。
- browser-use gated 状态需要明确，不应作为同等主操作。

### `RunHistoryPanel` / `RecentRunsList`

- 两者功能重叠，建议合并成一个 `RunHistory` 组件。
- Dashboard 中显示 compact recent runs。
- History 页面显示完整列表和筛选。
- artifact yes/no pills 和 screenshot count 默认折叠到详情。

### `EvaluationSummary`

- 与 `ReportPreview` 内部 Evaluation 合并。
- Dashboard 只显示一个 score card。
- Report 页面显示完整 score list。
- Evaluation 原始 artifact 链接折叠。

### `AgentStatusPanel` / `AgentTimeline` / `AgentStatusCard`

- `AgentTimeline` 可保留为 Dashboard 的简化阶段条。
- `AgentStatusCard` 默认折叠到 Details。
- Dashboard 只显示 current phase、blocked/failed reason、最近可读事件。
- heartbeat、raw metrics、started time 默认隐藏。

### `EventLog`

- 默认不作为右栏展示。
- Dashboard 可保留“Activity”简版，只展示最近 3-5 条 PM 可读事件。
- 完整 `EventLog` 移到 Details。
- Payload summary、artifact tokens、seq、SSE 状态默认隐藏。
- Filters 保留在 Details，默认简化为 All / Warnings & Errors。

### `EvidenceList` / `EvidenceItemCard` / `ScreenshotPreview`

- 保留。
- 默认筛选行可以简化为 Search、Product、Scenario，Kind/Status/Group 放到 More filters。
- `Sanitized Data`、artifact ids、final_output 默认折叠。
- Missing screenshot 状态必须保留。

### `ReportPreview` / `ReportToolbar`

- 保留为主页面。
- Toolbar 默认保留 Copy Markdown。
- Download report.md 次级。
- report.md/evaluation.json artifact links 折叠到 Details。

### `ArtifactLink`

- 保留为底层组件。
- 默认 UI 不应大量直接暴露 artifact id。
- 在 PM 页面中使用人类可读 label，如 Open source artifact / Open screenshot。

## 前端实现任务清单

1. 定义新的信息架构：Dashboard、Report、Evidence、History、Details 五个主视图，并确定默认视图规则。
2. 改造 `AppShell`：从固定 left/main/right/bottom 三区调试布局改为 top context bar + navigation/tabs + single main content。
3. 改造 `ConsolePage`：按当前选中视图渲染主内容，不再默认同时渲染 Agent、Event、Report、Evidence。
4. 新建或重组 Dashboard 组合组件：Plan/Start、Active Run、Results shortcuts、Recent Runs。
5. 简化 `TopRunContextBar`：移除默认 source/SSE/run_dir；只保留 PM 核心上下文和主操作。
6. 简化启动卡：默认仅保留 plan selector、plan summary、Start Mock Run；高级参数折叠。
7. 将 browser-use 入口降级为高级选项或 gated disabled 状态，直到后端路径完成。
8. 删除默认 `API request / Mock request` payload 展示，改为 Debug details。
9. 将 mock fallback 状态切换器移入 Debug details，并仅在 source 为 mock 时出现。
10. 合并 `RunHistoryPanel` 与 `RecentRunsList` 的职责：Dashboard compact，History full。
11. 将 `EvaluationSummary` 与 Report/Evaluation 展示合并，避免重复。
12. 把 Agent Status 变成两级展示：Dashboard 阶段摘要，Details 完整 agent board。
13. 把 Event Log 变成两级展示：Dashboard 最近活动摘要，Details 完整事件流。
14. 简化 Evidence 默认筛选：More filters 中放 kind/status/group。
15. 折叠 Evidence raw data、artifact ids、final_output。
16. 简化 Report toolbar：Copy Markdown 为主；download/artifact links 为次级详情。
17. 统一 PM 文案：把 `mock fallback`、`SSE`、`artifact`、`payload` 等词从默认视图移到 Debug。
18. 补齐空状态：每个主视图都说明为什么为空和下一步动作。
19. 补齐 blocked/failed 体验：默认展示原因、可用 partial artifacts、Retry/Open Details。
20. 更新前端验收用例或手工 QA 清单，覆盖 mock run、历史 run、report/evidence/evaluation、debug details。

## 验收标准

### 默认工作台体验

- 打开页面后，用户首先看到的是可执行的 PM 工作台，而不是多栏工程日志。
- 首屏能直接完成：选择 plan、查看摘要、启动 mock run。
- 默认首屏不显示 API payload、SSE 状态、raw artifact id、mock state toggles。
- Start Mock Run 是唯一主要启动动作；browser-use 未闭环前不作为同等主 CTA。
- 顶部 run context 能清楚显示当前 run 的状态、进度和下一步动作。

### 结果复核体验

- run 完成后，Report 是最突出的结果入口。
- Evidence 可从 Dashboard/Report 进入，并能继续查看截图缺失状态。
- Evaluation 不重复展示；至少有一个清晰 score summary，并能查看详细指标。
- 历史 run 可以打开 report/evidence/evaluation，且不会破坏 active run 上下文。

### 详情和调试体验

- Agent Status 和 Live Event Log 仍可完整访问，但位于 Details/Debug。
- Debug 中可以查看 source/API health、SSE connection state、API request payload、artifact links。
- Mock fallback 控件只在 mock fallback 或 Debug 中出现。
- blocked/failed 时，Details 能帮助定位原因，但默认页面仍优先展示 partial artifacts。

### 功能完整性

- Web mock run 端到端闭环不退化：start -> events -> agents -> report/evidence/evaluation -> history。
- SSE 实时更新能力保留。
- Artifact 安全访问约束不改变。
- 空状态和错误状态符合 UX 规格，不吞掉 partial evidence/report。
- `npm run build` 通过。

## Recommended Phase 6 Direction

Phase 6 不应继续堆功能。优先做信息架构收敛：把默认视图变成 PM 的任务流，把工程信息集中到 Details/Debug。这样既保留 Phase 5 的完整可观测能力，又能让新用户不用理解 run event schema、artifact registry 和 SSE 状态，也能完成一次产品走查复核。
