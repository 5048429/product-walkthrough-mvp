# prodwalk Web 控制台 MVP 用户路径

本文定义第一版本地 Web 控制台从选择 plan 到查看 report 的核心路径。API 名称是前端需要后端支持的本地接口契约，目的是承接现有 CLI 能力和 artifact 文件，不代表当前仓库已经存在 Web API。

## 通用 API 与事件约定

### 推荐 API

- `GET /api/plans`：列出本地可用 plan。
- `GET /api/plans/{planId}`：读取 plan 详情。
- `POST /api/runs`：创建并启动 run。
- `GET /api/runs`：列出历史 run。
- `GET /api/runs/{runId}`：读取 run 摘要。
- `GET /api/runs/{runId}/agents`：读取 agent/stage 状态。
- `GET /api/runs/{runId}/events`：读取事件列表。
- `GET /api/runs/{runId}/stream`：订阅实时事件。
- `GET /api/runs/{runId}/evidence`：读取 evidence 列表。
- `GET /api/runs/{runId}/evidence/{evidenceId}`：读取 evidence 详情。
- `GET /api/runs/{runId}/screenshots/{screenshotId}`：读取 run-local 截图。
- `GET /api/runs/{runId}/report`：读取 report markdown 和 report metadata。
- `GET /api/runs/{runId}/evaluation`：读取 evaluation。

### 推荐事件

- run.created
- run.started
- plan.loaded
- stage.started
- stage.completed
- agent.status_changed
- step.started
- step.completed
- evidence.created
- screenshot.archived
- finding.created
- report.generated
- evaluation.generated
- run.blocked
- run.failed
- run.completed

## Flow 1：选择 plan 并启动 mock run

### 用户动作

用户进入 Run Dashboard，打开 Plan Selector，选择一个本地 plan，例如 smoke plan。用户查看 plan 摘要，确认 research goal、products、scenarios 和 evaluation 配置，然后点击 Start Mock Run。

### 前端状态变化

- 初始状态为 idle。
- 选择 plan 后，Run Launch Panel 显示 plan detail summary。
- 点击启动后按钮进入 loading，Active Run Card 创建 pending 状态。
- 收到 run.started 后进入 running。
- 导航上下文设置 active run。

### 调用哪些 API

- `GET /api/plans`
- `GET /api/plans/{planId}`
- `POST /api/runs`，参数包括 planId、mode=mock、report_language。
- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/stream`

### 依赖哪些事件

- plan.loaded
- run.created
- run.started
- stage.started
- agent.status_changed
- run.failed
- run.blocked
- run.completed

### 成功结果

- Run Dashboard 显示 active run running。
- Agent Status 可以看到 Planner 或 Walker 阶段启动。
- Live Event Log 开始出现事件。
- 后续完成后生成 evidence、report 和 evaluation。

### 失败结果

- plan 读取失败：Run Launch Panel 显示 plan parse error。
- run 创建失败：Active Run Card 显示 failed，错误摘要固定在顶部。
- mock walker 执行失败：run 状态进入 failed，保留已产生事件。

## Flow 2：查看实时 agent 状态

### 用户动作

用户从 Run Dashboard 点击当前 running run，进入 Agent Status Panel，查看当前执行阶段和各 agent 的状态。用户展开 Walker，查看当前 product、scenario、step、url 和最近动作。

### 前端状态变化

- Agent Status 从 idle 空状态切换到 running 状态。
- 当前 agent card 高亮。
- 已完成阶段显示 done。
- 收到 agent.status_changed 后更新状态、心跳和当前任务。
- 如果 run blocked，阻塞 agent card 转为 amber。
- 如果 run failed，失败 agent card 转为 red。

### 调用哪些 API

- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/agents`
- `GET /api/runs/{runId}/stream`
- 必要时调用 `GET /api/runs/{runId}/events` 补齐历史事件。

### 依赖哪些事件

- stage.started
- stage.completed
- agent.status_changed
- step.started
- step.completed
- run.blocked
- run.failed
- run.completed

### 成功结果

- 用户能看到 prodwalk 当前位于 Planner、Walker、Evidence、Analyst、Reviewer、Reporter 或 Evaluator 的哪一阶段。
- Walker 运行时能看到当前 product/scenario/step。
- 用户可以从相关 step 跳到 Live Event Log 或 Evidence Viewer。

### 失败结果

- agent 状态 API 不可用：页面显示 Unable to load agent status，同时保留 run summary。
- 实时流断开：显示 reconnecting，并回退轮询 `GET /api/runs/{runId}/agents`。
- blocked：展示 blocker reason，例如 manual verification required、timeout、login challenge、external domain blocked。

## Flow 3：查看事件日志

### 用户动作

用户进入 Live Event Log，默认查看实时事件。用户暂停自动滚动，筛选 Warning/Error，点击 evidence.created 事件打开对应 evidence。

### 前端状态变化

- running 时显示 Live 标记，自动滚动到底部。
- 用户暂停自动滚动后，新事件计数显示在顶部。
- 筛选条件改变后，列表只显示匹配事件。
- 点击事件后打开 Event Detail Drawer。
- 若事件有关联 evidence_id，显示 Open Evidence 操作。

### 调用哪些 API

- `GET /api/runs/{runId}/events`
- `GET /api/runs/{runId}/stream`
- 点击 evidence 时调用 `GET /api/runs/{runId}/evidence/{evidenceId}`

### 依赖哪些事件

- run.started
- plan.loaded
- stage.started
- stage.completed
- agent.status_changed
- step.started
- step.completed
- evidence.created
- screenshot.archived
- finding.created
- report.generated
- evaluation.generated
- run.blocked
- run.failed
- run.completed

### 成功结果

- 用户能按时间理解 run 的执行过程。
- 用户可以从日志直接追溯 evidence、截图和 report。
- blocked/failed 时，顶部显示相关摘要并定位关键事件。

### 失败结果

- 事件加载失败：显示 Error Banner 和 Retry。
- 实时流断开：保留已有事件，显示 reconnecting。
- 事件缺少关联 artifact：显示 Missing linked artifact，但不隐藏事件本身。

## Flow 4：run 完成后查看 report

### 用户动作

用户看到 Run Dashboard 中 active run 变为 done，点击 Open Report，进入 Report Preview。用户浏览报告 outline，查看 Product Findings、Reviewer Notes 和 Evidence Appendix，点击 evidence id 核验证据。

### 前端状态变化

- run.completed 后，Report Preview 从 pending 变为 ready。
- Report Outline 显示章节。
- Markdown Preview 渲染 report.md。
- Evaluation Score Panel 展示 overall score 和关键指标。
- evidence citation 被渲染成可点击链接。

### 调用哪些 API

- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/report`
- `GET /api/runs/{runId}/evaluation`
- 点击 evidence 时调用 `GET /api/runs/{runId}/evidence/{evidenceId}`

### 依赖哪些事件

- report.generated
- evaluation.generated
- run.completed
- run.failed
- run.blocked

### 成功结果

- 用户看到完整 Markdown report。
- 用户可以从 finding 的 evidence_ids 打开 Evidence Viewer。
- 用户可以复制 report Markdown，作为评审或 PRD 输入。

### 失败结果

- report 未生成：显示 Report not ready，并提示 run 是否仍在 running、blocked 或 failed。
- report 读取失败：显示 Artifact read failed，提供 Open Log。
- evaluation 缺失：Report 仍可展示，Evaluation Panel 显示 unavailable。
- run blocked：若后端生成 partial report，则显示 Partial report available；否则显示 blocked reason 和 evidence 入口。

## Flow 5：查看 evidence 和截图

### 用户动作

用户从 Report Preview 点击 evidence id，或从 Live Event Log 点击 evidence.created 事件，进入 Evidence Viewer。用户查看 evidence summary、URL、action、errors、confidence 和截图。用户打开截图大图，检查 agent 当时看到的页面。

### 前端状态变化

- Evidence Viewer 选中目标 evidence。
- 左侧 evidence list 高亮对应项。
- 右侧 detail panel 加载 summary、metadata、raw data 和 screenshot。
- 如果 evidence 包含多个 screenshot_paths，显示 gallery strip。
- 若截图不存在，显示 Missing screenshot，不影响 evidence 文本展示。

### 调用哪些 API

- `GET /api/runs/{runId}/evidence`
- `GET /api/runs/{runId}/evidence/{evidenceId}`
- `GET /api/runs/{runId}/screenshots/{screenshotId}`
- 可选调用 `GET /api/runs/{runId}/events` 获取关联事件。

### 依赖哪些事件

- evidence.created
- screenshot.archived
- step.completed
- finding.created
- run.blocked
- run.failed
- run.completed

### 成功结果

- 用户能看到证据文本、截图、URL 和关联 finding。
- 用户能判断 report 中的 claim 是否有足够依据。
- 用户能区分 browser_run 总结证据和 browser_step 过程证据。

### 失败结果

- evidence 不存在：显示 Evidence not found，并返回 evidence list。
- 截图文件不存在：显示 Missing screenshot，但保留 path 和 summary。
- evidence.json 不可读：页面显示 Artifact read failed，引导查看 Live Event Log。
- run failed 但已有 evidence：显示 Partial evidence。

## Flow 6：查看历史 run

### 用户动作

用户进入 Run History，按时间查看历史 run，筛选 done 或 blocked，打开某一次 run。用户查看该 run 的 report、evidence、evaluation 和事件摘要。

### 前端状态变化

- Run History 初始加载历史列表。
- 选择历史 run 后，active run context 更新。
- 其他页面自动切换到该 run 的上下文。
- 若该 run 没有事件流归档，则 Live Event Log 显示 artifact-derived events 或事件不可用提示。

### 调用哪些 API

- `GET /api/runs`
- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/report`
- `GET /api/runs/{runId}/evidence`
- `GET /api/runs/{runId}/evaluation`
- 可选调用 `GET /api/runs/{runId}/events`

### 依赖哪些事件

历史 run 不依赖实时事件，但依赖后端从 artifacts 或 event store 中恢复：

- run.completed
- run.blocked
- run.failed
- report.generated
- evaluation.generated
- evidence.created

### 成功结果

- 用户能看到本地历史 run 列表。
- 用户能打开任何有 artifact 的 run。
- 用户能继续查看 report、evidence、evaluation。

### 失败结果

- run 目录为空或 artifact 缺失：列表显示 Incomplete artifacts。
- evidence/report/evaluation 读取失败：对应入口显示 unavailable。
- 历史 run 状态无法判断：显示 unknown，并用 artifacts 推断可查看内容。
