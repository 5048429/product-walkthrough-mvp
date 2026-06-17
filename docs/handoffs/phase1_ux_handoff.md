# Phase 1 UX Handoff

## 本 agent 产出的文件

- `docs/frontend_console_ux_spec.md`
- `docs/frontend_console_mvp_user_flows.md`
- `docs/handoffs/phase1_ux_handoff.md`

这些文件基于当前仓库的 README、VERSION_HISTORY、examples plan、prodwalk 数据模型、CLI 入口、pipeline agent 和 run artifact 结构编写。没有创建 `apps/web`，没有修改 `src/prodwalk`。

## 推荐优先级

P0：

- Run Dashboard
- Plan Selector
- Start Mock Run
- Active Run Summary
- Live Event Log
- Evidence Viewer 基础列表与详情
- Report Preview 读取 Markdown

P1：

- Agent Status Panel
- Run History
- Evaluation Summary
- Screenshot Gallery
- Blocked state detail

P2：

- Browser-use run 启动参数 UI
- Retry flow
- Artifact availability diagnostics
- Report outline 与 evidence citation 深链

第一阶段建议先跑通 mock run 的完整闭环：选择 plan、启动 run、看到事件、看到 evidence、看到 report、看到历史记录。

## 前端 Agent 下一步应该实现哪些组件

全局组件：

- App Shell
- Side Navigation
- Top Run Context Bar
- Status Badge
- Error Banner
- Empty State
- Loading Skeleton
- Artifact Link

Run Dashboard：

- Plan Selector
- Plan Detail Summary
- Run Launch Panel
- Active Run Card
- Run Metric Cards
- Recent Runs Table

Agent Status：

- Agent Status Timeline
- Agent Status Card
- Current Step Row
- Blocked Reason Panel

Live Event Log：

- Event Stream
- Event Row
- Event Filter Bar
- Severity Badge
- Event Detail Drawer

Evidence Viewer：

- Evidence List
- Evidence Filter Bar
- Evidence Detail Panel
- Screenshot Preview
- Screenshot Gallery Strip
- Raw Data Collapsible
- Linked Findings List

Report Preview：

- Report Outline
- Markdown Preview
- Finding Card
- Evidence Citation Link
- Reviewer Notes Panel
- Evaluation Score Panel

Run History：

- Run History Table
- Status Filter Tabs
- Artifact Availability Badge
- Run Detail Drawer

## 后端 Agent 需要支持哪些数据

### Plan 数据

- 列出可用 plan。
- 读取 plan 详情。
- 返回 plan parse error，字段要能定位到 research_goal、products、scenarios 等缺失项。

### Run 数据

- 创建并启动 mock run。
- 返回 run_id、status、mode、plan_id、created_at、started_at、completed_at、output_dir。
- 返回 active run 和历史 run 列表。
- 支持状态：idle、running、done、blocked、failed。
- 能从 artifact 推断历史 run 的 status 和 artifact availability。

### Agent/Stage 数据

- 返回当前 pipeline 阶段。
- 返回每个阶段型 agent 的 status、current_task、product、scenario_id、step_index、url、started_at、updated_at、elapsed_ms。
- blocked/failed 时返回 reason、error_message、related_event_id。

### Event 数据

- 提供历史事件列表。
- 提供实时事件流，建议 SSE。
- 事件需要包含 timestamp、stage、agent、severity、type、message、product、scenario_id、step_index、url、evidence_id、screenshot_path。
- 对现有 CLI pipeline，需要新增事件发射层；历史 run 可先用 artifacts 生成 derived events。

### Evidence 数据

- 读取 `evidence.json` 并返回 normalized evidence list。
- 支持 evidence detail。
- 支持 browser_run 和 browser_step。
- 返回关联 finding、events、steps。
- 对 invalid 或旧格式 artifact，返回可解释的 artifact read error。

### Screenshot 数据

- 优先服务 run-local `screenshots/` 目录。
- 对 evidence 中的 temp path，若文件存在则可读，若不存在则返回 missing。
- 截图 API 不应暴露 secret，也不应要求前端直接读取任意本地路径。

### Report 数据

- 读取 `report.md`。
- 返回 Markdown 原文、章节 outline、artifact path。
- 返回 report generated 状态。
- blocked/failed 时支持 partial report 状态。

### Evaluation 数据

- 读取 `evaluation.json`。
- 返回 overall_score、scores、notes。
- 缺失时不阻塞 Report Preview。

## 还需要产品确认的问题

- V1 是否只允许 mock run，还是同时开放 browser-use run？
- Plan 来源是否固定为 `examples/`，还是允许用户选择任意本地 JSON plan？
- Run 输出目录是否固定为 `runs/`，还是允许用户选择 `runs-*`？
- Browser-use 触发人工验证时，Web 控制台只提示用户回到后端/终端，还是需要提供更明确的 checkpoint UI？
- Report 第一版是否只支持 Markdown 预览和复制？
- Evidence Viewer 是否需要 PM 备注、Useful/Not useful 标记？当前建议 V1 不做。
- 历史 run 的 event log 是否必须完整持久化，还是第一版接受 artifact-derived events？
- Status 命名是否使用 done，还是沿用 artifact 中的 completed？当前 UX 对用户展示 done，后端可继续使用 completed。
- 中文 report 当前存在历史编码显示问题，V1 是否需要前端做编码异常提示？
- 是否需要在 UI 中暴露 LLM provider/model、browser headless、max steps 等运行参数，还是只放在详情抽屉？
