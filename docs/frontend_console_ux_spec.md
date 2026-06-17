# prodwalk Web 控制台 UX 规格

## 目标用户

第一版 Web 控制台服务单机本地使用的产品经理。用户希望把 prodwalk 从命令行工具变成可观察、可回放、可复核的内部工作台，用于自家产品走查、竞品分析、证据收集、报告生成和 PRD 输入。

目标用户的典型特征：

- 熟悉产品目标、用户路径、竞品对象和评审材料需求。
- 不希望记忆 CLI 参数或翻找 run 目录。
- 需要在运行过程中判断 agent 是否卡住、是否需要人工登录验证、是否已经收集到足够证据。
- 需要把 evidence、截图和 report 互相串起来，判断结论是否可信。

## 核心使用场景

- 选择已有 research plan，启动一次 mock run 或 browser-use run。
- 在 run 运行中查看当前阶段、agent 状态、实时事件和已采集 evidence。
- 当 run blocked 或 failed 时，快速定位原因、保留已产生的证据，并判断是否重试。
- 在 run 完成后查看 report、evaluation、findings 和 evidence appendix。
- 回看历史 run，对比不同计划、不同模式、不同时间的结果。

第一版重点是本地 Web 控制台，不做营销页。整体观感应像内部工作台：信息密度适中、状态清楚、操作克制、默认进入可用的 run 管理界面。

## 页面结构

控制台采用左侧主导航 + 顶部 run context bar + 主内容区。

左侧主导航：

- Run Dashboard
- Agent Status
- Live Event Log
- Evidence Viewer
- Report Preview
- Run History

顶部 run context bar：

- 当前选中的 run 名称或 run id。
- plan 名称、mode、目标产品数量、scenario 数量。
- run 状态：idle、running、done、blocked、failed。
- 开始时间、已运行时长、输出目录。
- 主操作：Start Mock Run、Start Browser Run、Stop、Retry、Open Report。

主内容区根据导航切换。第一版不需要多层应用壳，不需要工作区、组织、权限或云端环境。

## 导航结构

默认首页是 Run Dashboard。没有选中 run 时，Agent Status、Live Event Log、Evidence Viewer、Report Preview 显示对应空状态，并引导用户先选择或启动 run。

导航之间共享同一个 active run：

- 从 Run Dashboard 点击 run 后，所有页面进入该 run 的上下文。
- 从 Live Event Log 点击 evidence 事件，跳转到 Evidence Viewer 并选中对应 evidence。
- 从 Report Preview 点击 evidence id，跳转到 Evidence Viewer。
- 从 Agent Status 点击失败步骤，跳转到 Live Event Log 并定位相关事件。

## Run Dashboard 规格

### 页面目的

Run Dashboard 是 PM 的起点，用于选择 plan、启动 run、查看当前 run 和最近历史 run 的整体状态。

### 展示内容

- Plan Selector：列出本地可用 plan，例如 examples 下的 smoke、research、Clink UAT plan。
- Run Launcher：选择 mode、report language、concurrency、browser max steps 等第一版允许配置的最小参数。
- Active Run Summary：当前运行中的 run、当前阶段、完成度、已采集 evidence 数、finding 数、错误数。
- Recent Runs：最近 run 列表，展示 run id、plan、mode、status、created_at、duration、output artifacts。
- Evaluation Summary：完成后展示 overall score、task completion rate、evidence coverage rate、finding grounding rate、recommendation actionability rate。

### 用户能做什么

- 选择 plan 并查看 plan 摘要。
- 启动 mock run。
- 启动 browser-use run，若需要人工验证，进入 blocked/manual verification 提示。
- 打开运行中的 run。
- 打开历史 run 的 report、evidence、event log。
- Retry failed 或 blocked run。

### 主要组件

- Plan Selector
- Plan Detail Summary
- Run Launch Panel
- Active Run Card
- Run Metric Cards
- Recent Runs Table
- Artifact Links
- Status Badge
- Error Banner

### 数据字段

来自现有 plan 和 artifacts 的字段：

- plan.research_goal
- plan.products.name/url/kind/credentials_ref/notes/tags
- plan.scenarios.id/title/persona/goal/steps/success_criteria/observation_points/risk_level
- run.status
- run.mode
- run.output_dir
- evidence.created_at
- evaluation.scores
- evaluation.overall_score

### 状态呈现

- idle：显示 plan selector 和启动按钮，Active Run 区域为空。
- running：显示进度、当前阶段、最近事件、Stop 操作。
- done：显示 report、evidence、evaluation 快捷入口。
- blocked：显示阻塞原因、阻塞阶段、是否需要人工验证、Retry 操作。
- failed：显示失败摘要、最近 error event、保留 partial artifacts 的入口。

## Agent Status Panel 规格

### 页面目的

Agent Status Panel 用于让 PM 理解 prodwalk pipeline 当前跑到哪里，以及哪个 agent 在做什么。它不是工程调试台，而是运行可解释性面板。

### Agent 与阶段映射

现有 pipeline：

- ResearchDirector：编排 run。
- ScenarioPlanner：规划 scenario。
- BrowserWalker：执行 mock 或 browser-use walkthrough。
- EvidenceExtractor：归档截图并汇总 evidence。
- ProductAnalyst：生成产品 findings。
- CompetitiveAnalyst：生成竞品洞察。
- Reviewer：检查 evidence grounding。
- ReportWriter：生成 Markdown report。
- Evaluator：生成 evaluation。

前端展示时可简化为阶段型 agent：

- Director
- Planner
- Walker
- Evidence
- Analyst
- Reviewer
- Reporter
- Evaluator

### 展示内容

- 当前阶段。
- 每个 agent 的状态、当前任务、开始时间、耗时、最近心跳。
- Walker 的当前 product、scenario、step、url、action。
- Evidence 的已采集数量和截图归档状态。
- Reporter 的 report 生成状态。
- Blocked 或 failed agent 的原因。

### 用户能做什么

- 查看每个 agent 的实时状态。
- 展开 agent 详情，查看当前 product/scenario/step。
- 从 agent 详情跳转到相关 events。
- 从 Walker step 跳转到 evidence 或截图。
- 对 blocked/failed run 发起 Retry。

第一版不提供单独控制某个 agent 的复杂操作，不做 agent prompt 编辑，不做逐步人工接管。

### 主要组件

- Agent Status Timeline
- Agent Status Card
- Current Step Row
- Heartbeat Indicator
- Stage Progress Bar
- Blocked Reason Panel
- Related Events Link

### 状态呈现

- idle：所有 agent 灰态，文案为 No active run。
- running：当前 agent 高亮，已完成 agent 显示 done check，未开始 agent 灰态。
- done：所有完成阶段显示 done，若某阶段无输出则显示 skipped。
- blocked：阻塞 agent 使用 amber 状态，展示 blocker reason 和 next action。
- failed：失败 agent 使用 red 状态，展示 error message 和 failed event。

## Live Event Log 规格

### 页面目的

Live Event Log 是 PM 的实时运行记录。它应解释系统做了什么、什么时候做、产出了什么证据，而不是暴露原始工程日志噪音。

### 展示内容

事件列表默认按时间正序，运行中自动滚动到底部。

事件字段：

- event_id
- timestamp
- run_id
- stage
- agent
- severity：info、warning、error
- type
- title
- message
- product
- scenario_id
- step_index
- url
- evidence_id
- screenshot_path

推荐事件类型：

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

### 用户能做什么

- 暂停或恢复自动滚动。
- 按 severity、agent、stage、product、scenario 筛选。
- 只看 warnings/errors。
- 点击 evidence 或 screenshot 跳转到 Evidence Viewer。
- 点击 report.generated 跳转到 Report Preview。

### 主要组件

- Event Stream
- Event Filter Bar
- Severity Badge
- Stage Badge
- Auto-scroll Toggle
- Event Detail Drawer
- Related Artifact Link

### 状态呈现

- idle：显示 No events yet。
- running：显示 Live 标记，新事件短暂高亮。
- done：自动滚动关闭，顶部显示 run completed 摘要。
- blocked：顶部固定 blocked summary，并突出相关 warning/error。
- failed：顶部固定 failure summary，保留已产生事件。

## Evidence Viewer 规格

### 页面目的

Evidence Viewer 用于让 PM 检查结论的证据基础，包括 browser_run、browser_step、截图、URL、action、summary、errors 和 confidence。

### 展示内容

左侧 evidence list：

- evidence id
- kind：observation、browser_run、browser_step
- product
- scenario_id
- title
- confidence
- created_at
- 是否有 screenshot
- 是否有关联 finding

右侧 evidence detail：

- 标题、类型、产品、scenario、URL。
- summary。
- screenshot preview。
- action_names、step_number、title。
- errors。
- final_output 或结构化摘要。
- history_file 引用。
- 关联 steps、events、findings。

截图展示：

- 若 screenshot 是 run-local `screenshots/` 路径，直接预览。
- 若是历史 temp path 且文件不存在，展示 Missing screenshot 状态，并保留路径文本。
- browser_run 可能包含 screenshot_paths 数组，展示为截图 strip。

### 用户能做什么

- 按 product、scenario、kind、有无 screenshot、有无 error 筛选。
- 在 evidence list 中切换详情。
- 打开截图大图。
- 从 evidence 跳转到对应 event。
- 从 evidence 跳转到 report 中引用它的 finding。

第一版不做 evidence 人工编辑、不做标注、不做重新裁剪截图。

### 主要组件

- Evidence List
- Evidence Filter Bar
- Evidence Detail Panel
- Screenshot Preview
- Screenshot Gallery Strip
- Raw Data Collapsible
- Linked Findings
- Missing Artifact Notice

### 状态呈现

- idle：未选择 run 时显示 Select a run to inspect evidence。
- running：新 evidence 进入列表顶部或按 step 顺序追加，并标记 New。
- done：展示完整 evidence 和截图。
- blocked：展示 partial evidence，并说明 run 被阻塞前已收集到哪些内容。
- failed：展示可恢复 evidence，缺失截图用错误状态表示。

## Report Preview 规格

### 页面目的

Report Preview 用于让 PM 阅读报告、检查 findings 是否有证据支撑，并把报告作为评审或 PRD 输入。

### 展示内容

基于现有 `report.md` 和 `evidence.json`：

- Research goal。
- Scope。
- Scenario Coverage 表。
- Product Findings。
- Competitive Insights。
- Reviewer Notes。
- Evidence Appendix。
- Scenario Definitions。
- Evaluation Summary。

Finding 展示字段：

- id
- product
- scenario_id
- severity
- theme
- claim
- recommendation
- confidence
- evidence_ids

### 用户能做什么

- 查看 Markdown 渲染预览。
- 切换 Outline 到不同章节。
- 点击 evidence id 打开 Evidence Viewer。
- 查看 reviewer notes 和 evaluation。
- 复制 report Markdown。
- 打开 report artifact 所在位置。

第一版不做富文本编辑、不做 PDF 导出、不做自动 PRD 生成，只保留可复制和可阅读预览。

### 主要组件

- Report Outline
- Markdown Preview
- Finding Card
- Evidence Citation Link
- Reviewer Notes Panel
- Evaluation Score Panel
- Copy Markdown Button

### 状态呈现

- idle：Report not ready。
- running：显示 report generation pending，并可展示已知 plan scope。
- done：展示完整 report。
- blocked：展示 Partial report available 或 Report not generated，取决于后端是否已经写出 artifact。
- failed：展示错误摘要和 partial artifact 入口。

## Run History 规格

### 页面目的

Run History 用于回看本地 run 目录中的历史执行结果，替代用户手动翻 `runs-*` 文件夹。

### 展示内容

- run id 或目录名。
- created_at。
- plan research goal。
- mode。
- status。
- products/scenarios 数量。
- evidence count。
- findings count。
- overall score。
- artifact 状态：evidence.json、report.md、evaluation.json、screenshots。

### 用户能做什么

- 搜索 run。
- 按 status、mode、plan、时间筛选。
- 打开 run 详情。
- 打开 report、evidence、evaluation。
- 对历史 run 发起 Retry。

第一版不做跨 run diff，不做批量删除，不做云端同步。

### 主要组件

- Run History Table
- Run Search
- Status Filter Tabs
- Artifact Availability Badge
- Run Detail Drawer

## 状态设计：idle/running/done/blocked/failed

### idle

含义：没有 active run，或 run 尚未启动。

视觉：

- 中性色状态 badge。
- 主操作为选择 plan 和 Start Mock Run。
- Agent、Log、Evidence、Report 页面显示空状态。

### running

含义：run 正在执行，事件流和 agent 状态持续更新。

视觉：

- 蓝色或绿色 running badge。
- 显示 elapsed time、current stage、progress。
- Live Event Log 显示 Live 标记。
- Evidence Viewer 可显示 partial evidence。

### done

含义：run 完成，artifacts 已生成。

视觉：

- 绿色 done badge。
- Dashboard 显示 report/evidence/evaluation 快捷入口。
- Report Preview 展示完整 report。

### blocked

含义：run 没有崩溃，但由于产品流程、登录验证、Altcha/CAPTCHA、超时、外部域名限制或场景无法继续而停止或需要人工处理。

视觉：

- Amber blocked badge。
- 展示 blocker reason、blocked stage、blocked product/scenario。
- 显示 partial evidence 和 partial report 状态。
- 主操作为 Retry 或查看 blocked evidence。

blocked 与 failed 的区别：

- blocked 是可解释的业务/环境阻塞，通常已有 partial artifacts。
- failed 是系统错误或 artifact 写入失败，可能导致产物不完整或不可读。

### failed

含义：run 执行异常失败，例如后端进程异常、plan 解析失败、artifact 读取失败、浏览器启动失败、LLM 配置缺失。

视觉：

- Red failed badge。
- 顶部 Error Banner。
- 展示 error message、failed event、可用 artifact。
- 主操作为 Retry 或返回 Dashboard。

## 空状态设计

全局原则：

- 说明为什么为空。
- 给出下一步动作。
- 不用营销文案，不解释产品价值。

页面空状态：

- Run Dashboard：No runs yet。操作：Select a plan and start a mock run。
- Agent Status：No active agents。操作：Start or select a run。
- Live Event Log：No events yet。操作：Events will appear after the run starts。
- Evidence Viewer：No evidence collected。操作：Wait for evidence or inspect a completed run。
- Report Preview：Report not ready。操作：Run must complete before report preview is available。
- Run History：No historical runs found。操作：Start first run。

## 错误状态设计

错误状态分为用户可处理和系统需排查两类。

用户可处理：

- Plan parse error：展示缺失字段，例如 research_goal、products、scenarios。
- Credentials missing：展示 credentials_ref，但不展示 secret。
- Manual verification required：提示需要完成登录、Altcha、CAPTCHA 或 MFA。
- Screenshot missing：展示 evidence 仍可用，但截图文件不可预览。

系统需排查：

- Backend unavailable。
- Run process crashed。
- Artifact read failed。
- Report markdown unreadable。
- Browser executable not found。
- LLM API key or model config missing。

错误呈现：

- 页面顶部 Error Banner 放摘要。
- 详情放在 drawer 或 expandable panel。
- 保留 Retry、Back to Dashboard、Open Log。
- 不吞掉 partial evidence/report。

## 第一版不做的功能

- 不做登录、多用户、权限、团队空间。
- 不做云端部署、远程队列、定时任务。
- 不做复杂桌面壳或系统托盘。
- 不做 plan 在线编辑器，只选择和预览本地已有 plan。
- 不做富文本 report 编辑器。
- 不做 PDF、PPT、PRD 自动导出。
- 不做跨 run diff。
- 不做人工标注 evidence、截图裁剪、批量 evidence 管理。
- 不做 agent prompt 编辑、agent 单步控制、人工接管浏览器。
- 不做 credential 管理 UI；第一版只提示已有 credentials_ref 是否需要后端验证。
- 不做成本账单、token 明细或复杂性能分析。
