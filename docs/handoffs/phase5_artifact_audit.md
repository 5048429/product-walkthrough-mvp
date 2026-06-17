# Phase 5 Evidence Artifact Audit

## Scope

本审计在进入体验增强前核对了当前文档、真实 run 产物、后端 FastAPI 实现和前端 Evidence / Report 支持情况。

已阅读材料：

- `docs/frontend_console_mvp_spec.md`
- `docs/api_event_contract.md`
- `docs/handoffs/phase4_final_handoff.md`
- `docs/handoffs/phase4_frontend_integration_handoff.md`
- `docs/handoffs/phase4_backend_integration_handoff.md`
- `src/prodwalk/agents/evidence.py`
- `src/prodwalk/agents/report.py`
- `apps/web/src/types/*`
- `apps/web/src/api/*`
- `src/prodwalk/server/*`

同时抽查了 `runs/`、`runs-*` 下的历史 `evidence.json`、`report.md`、`artifacts.json` 样本。

## evidence.json 字段说明

当前磁盘上的 `evidence.json` 是 raw pipeline artifact，不等同于 Web API 的 normalized evidence response。

当前 `ResearchDirector` 写入的 raw `evidence.json` 顶层字段：

- `created_at`: artifact 生成时间，ISO 字符串。
- `report_language`: 当前代码会写入报告语言；部分历史 run 缺失该字段。
- `plan`: 序列化后的 `ResearchPlan`，包含 `research_goal`、`products`、`scenarios`、`evaluation`、`report_language`。
- `scenarios`: `ScenarioPlanner` 输出的 scenario 列表。
- `results`: `WalkthroughResult[]`，每个 result 包含 `product`、`product_kind`、`scenario_id`、`scenario_title`、`status`、`started_at`、`completed_at`、`steps`、`evidence`、`metrics`、`errors`。
- `evidence`: 去重后的全局 `EvidenceItem[]`。
- `analyses`: `ProductAnalysis[]`，包含产品 summary、findings、metrics。
- `competitive_insights`: `CompetitiveInsight[]`。
- `review_notes`: `ReviewNote[]`。

`results[].steps[]` 真实字段：

- `index`
- `action`
- `status`
- `observation`
- `url`
- `screenshot`
- `elapsed_ms`
- `evidence_ids`

`evidence[]` 真实字段：

- `id`
- `product`
- `scenario_id`
- `kind`
- `title`
- `summary`
- `url`
- `screenshot`
- `data`
- `confidence`
- `created_at`

`data` 的内容依 walker 而变：

- mock evidence 常见字段：`action`、`status`、`observation_points`、`mock`。
- browser-use run evidence 常见字段：`task`、`mode`、`final_output`、`model`、`provider`、`base_url`、`wire_api`、`config_source`、`executable_path`、`headless`、`run_timeout_sec`、`user_data_dir`、`storage_state`、`timed_out`、`history_file`、`screenshot_paths`、`urls`、`action_names`、`errors`、`status_reason`。
- browser-use step evidence 常见字段：`step_number`、`action_names`、`summary`、`url`、`title`、`screenshot_path`、`errors`。

Web API 的 `GET /api/runs/{run_id}/evidence` 会重新 normalize：

- 返回 `run_id`、`artifact_id`、`created_at`、`report_language`、`results`、`evidence`、`plan`、`scenarios`。
- 不返回 raw 顶层的 `analyses`、`competitive_insights`、`review_notes`。
- 会把 `screenshot` / `screenshot_path` / `screenshot_paths` 映射为 `screenshot_artifact_id`。
- 会通过 `_sanitize_evidence_data()` 移除或脱敏 `history_file`、`screenshot_path`、`screenshot_paths`、`storage_state`、`user_data_dir`、`executable_path`、secret/token/credential/password/api_key 等字段。

注意：前端 `apps/web/src/api/client.ts` 当前会丢弃 normalized API 返回的 `data` 字段，`apps/web/src/types/contracts.ts` 的 `EvidenceItem` 也没有声明 `data`。

## report.md 展示限制

当前 `MarkdownReportWriter` 生成的是 Markdown 文本 artifact。报告主体包括：

- 标题和 research goal。
- Scope。
- Scenario Coverage 表格。
- Product Findings。
- Competitive Insights。
- Reviewer Notes。
- Evidence Appendix。
- Scenario Definitions。

截图相关行为：

- `MarkdownReportWriter._screenshot_note()` 会从 `EvidenceItem.screenshot`、`data.screenshot_path`、`data.screenshot_paths` 收集最多 5 个截图引用。
- 如果引用存在，会生成 Markdown 链接：`[filename](ref)`。
- 当截图已由 `EvidenceExtractor.archive_screenshots()` 成功归档时，`ref` 通常是 run 内相对路径，例如 `screenshots/ev-example-scenario-step-1.png`。
- 如果截图源文件不存在，归档逻辑会保留原始值；理论上 report 可能出现绝对本地路径或不可访问路径。

当前抽查结果：

- 最新 Phase 4 mock run 的 `report.md` 不含截图链接，因为 mock mode 不生成截图。
- 当前 workspace 下抽查的历史 browser-use report 也没有找到 Markdown 链接形式的截图路径。
- 历史 browser-use `evidence.json` 中存在大量绝对临时截图路径，但对应图片文件不在 run directory 中，也没有 `artifacts.json`。

展示限制：

- `GET /api/runs/{run_id}/report` 返回 raw Markdown，不改写 `screenshots/...` 相对链接。
- `GET /api/runs/{run_id}/artifacts/art_report_md/content` 也直接返回 raw Markdown。
- 前端 `ReportPreview` 使用 `<pre>{markdown}</pre>` 显示原文，不渲染 Markdown，不渲染图片，不改写相对链接。
- 当前 report 中的 evidence id 只是文本/code，不会跳转到 Evidence Viewer。

## screenshots/artifacts 路径规则

截图归档规则位于 `EvidenceExtractor.archive_screenshots()`：

- 处理 `EvidenceItem.screenshot`。
- 处理 `EvidenceItem.data.screenshot_path`。
- 处理 `WalkStep.screenshot`。
- 处理 `EvidenceItem.data.screenshot_paths[]`。
- `http://`、`https://`、`data:` 引用不会归档。
- 相对路径会尝试按 `run_dir / value` 和 `Path.cwd() / value` 查找。
- 已在 run directory 内的文件会保留为 run 内相对路径。
- run directory 外的已存在文件会复制到 `run_dir/screenshots/`。
- 归档文件名使用 evidence id 或 step hint slug，保留后缀，重复文件会追加序号。
- 同一源文件会去重，同源多处引用会指向同一个 run 内相对路径。
- 源文件不存在时不会报错，也不会复制，原始路径会保留在 raw evidence 中。

后端 artifact registry 规则位于 `RunRuntime._build_artifacts()`：

- 固定 artifact：
  - `art_run_manifest` -> `run.json`
  - `art_plan_json` -> `plan.json`
  - `art_events_jsonl` -> `events.jsonl`
  - `art_agents_json` -> `agents.json`
  - `art_artifacts_json` -> `artifacts.json`
  - `art_evidence_json` -> `evidence.json`
  - `art_report_md` -> `report.md`
  - `art_evaluation_json` -> `evaluation.json`
- 截图 artifact：
  - 扫描 `run_dir/screenshots/**/*`。
  - 只接受 `.png`、`.jpg`、`.jpeg`、`.webp`、`.gif`。
  - artifact id 格式是 `art_screenshot_<slug>_<sha1-8>`。
  - `path` 始终是 run 内 POSIX 相对路径。

当前不支持：

- `browser-history/` artifact 自动注册。
- 根目录 `browser_use_history_*.json` 自动归档到 run directory。
- 视频或其他非图片媒体 artifact。
- 多截图数组的完整 API 字段；后端 normalized evidence 当前只返回第一个匹配到的 `screenshot_artifact_id`。

## 当前 API 缺口

当前 FastAPI 对已注册 artifact 的文件路径有基本安全保护：

- `run_id` 必须匹配 `run-[A-Za-z0-9_.-]+`。
- run directory 只从 workspace 下的 `runs*` 目录扫描。
- `artifact_path()` 使用 `run_dir / artifact.path` resolve 后检查必须仍在 `run_dir` 内。
- 文件不存在返回 `ARTIFACT_NOT_FOUND`。
- 越界路径返回 `ARTIFACT_FORBIDDEN`。
- 图片 artifact 通过 `FileResponse` 返回对应 media type。

但仍有以下缺口：

- `GET /api/runs/{run_id}/artifacts/{artifact_id}/content` 对 JSON artifact 直接返回 raw JSON。对 `art_evidence_json` 来说，这会绕过 `GET /evidence` 的脱敏逻辑，暴露 raw `evidence.json` 中的绝对截图路径、`history_file`、`executable_path`、`user_data_dir`、`storage_state` 等字段。
- 历史 `runs-*` 会被 `RunRuntime._scan_run_dirs()` 纳入 Web 可见范围；这些旧 run 没有 Web metadata，却可以被推断为 run 并暴露 raw artifact content。
- `GET /api/runs/{run_id}/report` 返回 raw Markdown，不做相对截图链接重写，也不做内容脱敏。
- `read_report()` 和 `read_evidence()` 当前没有在响应中附带 `artifacts`，虽然前端类型允许该字段。
- `GET /api/runs/{run_id}/evidence/{evidence_id}` 已实现，但前端 API client 尚无 `getEvidenceDetail()`。
- evidence item 缺少 `artifact_ids`、`screenshot_artifact_ids`、`finding_ids` 的后端完整填充。
- 没有专门的 `EVIDENCE_NOT_FOUND` 错误码；单条 evidence 缺失当前返回 `ARTIFACT_NOT_FOUND`。
- `artifacts.json` 存在时 `list_artifacts()` 优先使用持久化文件；如果文件过期或被手动改动，列表可能与磁盘真实截图不一致。content endpoint 会拦截越界路径，但 metadata 仍可能暴露异常路径字符串。
- 没有 `screenshot.archived` 事件；截图只是作为 artifact registry 的一部分被发现。
- Web `POST /api/runs` 当前仍只支持 `mock`，无法通过 Web 创建真实 browser-use 截图 run。

## 当前前端缺口

Evidence Viewer 当前能力：

- 能显示 evidence list、group by `product` / `scenario` / `kind` / `status`。
- 能显示 selected evidence 的基础详情。
- 能显示 missing screenshot 状态。
- 能通过 `ArtifactLink` 打开 artifact content 新标签。

Evidence Viewer 缺口：

- 没有实际 `<img>` 截图预览或 gallery；有截图 artifact id 时仍显示占位和 artifact 链接。
- 没有图片加载中、加载失败、重试、尺寸适配状态。
- 没有调用 `GET /api/runs/{run_id}/evidence/{evidence_id}`，详情是本地 list item 展开。
- 前端 API client 没有 `getEvidenceDetail()`。
- `EvidenceItem` 类型没有 `data`，client 也丢弃 normalized API 的 sanitized `data`，因此没有 raw/sanitized data inspector。
- 没有 linked events、linked findings、step timeline。
- `screenshot_artifact_ids` 类型存在，但后端目前只填单个 `screenshot_artifact_id`。
- 当前仍是单页 console workbench，不是 MVP spec 中的 route-level Evidence Viewer。

Report Preview 当前能力：

- 能显示 raw Markdown。
- 能从 Markdown heading 提取 outline。
- 能显示 evaluation summary。
- 能复制 Markdown。
- 能链接 `report.md` 和 `evaluation.json` artifact content。

Report Preview 缺口：

- 不渲染 Markdown，只显示 `<pre>`。
- 不解析或改写 Markdown 链接。
- 不支持 report 内 `screenshots/...` 相对截图路径展示。
- 不支持 evidence id citation 跳转。
- 不显示 report 中关联的 screenshot/artifact 预览。
- 没有 Markdown 渲染安全策略；如果 Phase 5 引入 Markdown renderer，需要显式禁止或 sanitize raw HTML。

## Phase 5 后端任务建议

1. 定义 raw artifact 与 safe artifact 的边界：`GET /evidence` 保持 normalized/sanitized；`art_evidence_json/content` 是否继续允许 raw 下载需要明确开关或脱敏版本。
2. 为 `evidence_json`、`report_markdown`、`browser_history` 增加敏感字段审计测试，覆盖 storage state、user data dir、absolute temp screenshots、history file、token/secret/password。
3. 在 `read_report()` 中返回可选的 linked assets metadata，或新增 report asset resolver，将 `screenshots/foo.png` 映射为 screenshot artifact id / content URL。
4. 在 normalized evidence 中返回完整 `screenshot_artifact_ids`，并保留单个 `screenshot_artifact_id` 作为兼容字段。
5. 为 screenshot artifact 返回稳定 `content_url`，减少前端手拼 URL。
6. 归档 browser-use history 到 `run_dir/browser-history/` 前必须先脱敏，再注册为 `browser_history` artifact；不要暴露根目录历史文件。
7. 增加 `screenshot.archived` 或 `artifact.created` screenshot 事件，方便前端实时刷新截图。
8. 改进 `list_artifacts()`：对持久化 `artifacts.json` 做路径、media type 和存在性校验；必要时 rebuild 或标记 unavailable。
9. 为 `GET /api/runs/{run_id}/evidence/{evidence_id}` 增加前端所需详情字段：linked artifacts、linked events、related finding ids、sanitized raw data。
10. 为 artifact content 加 `X-Content-Type-Options: nosniff`，并明确图片、JSON、Markdown 的下载/inline 策略。
11. 增加测试覆盖：path traversal、缺失截图文件、过期 artifact registry、历史 CLI run、历史 browser-use absolute path、Markdown 相对链接重写。
12. 接入 Web browser-use run 前，先确认截图归档发生在 evidence 写入前，并保证 artifact registry 与 evidence screenshot ids 同步。

## Phase 5 前端任务建议

1. 增加 `prodwalkApi.getEvidenceDetail(runId, evidenceId)`。
2. 在 Evidence detail panel 中显示 sanitized raw data，不显示被后端移除的本地路径或 secret。
3. 实现 Screenshot Preview：通过 artifact content URL 渲染 `<img>`，支持 loading、error、missing、retry、open original。
4. 支持多截图 gallery，优先消费 `screenshot_artifact_ids`。
5. 将 evidence card 的截图区域从 placeholder 升级为真实缩略图。
6. Report Preview 改用安全 Markdown renderer，禁用或 sanitize raw HTML。
7. 对 report Markdown 中的 evidence ids 做 citation link，跳转到 selected evidence。
8. 对 report Markdown 中的相对 `screenshots/...` 链接做后端映射或前端 artifact lookup，不能直接拼本地路径。
9. 给 artifact link 增加 unavailable 状态：文件缺失、403 forbidden、unsupported media、load failed。
10. 增加 route-level Evidence Viewer / Report Preview deep link，至少支持 `run_id` 和 `evidence_id`。
11. 把 artifact refresh 与 screenshot/artifact events 绑定，避免 screenshot 到达后仍显示 missing。
12. 为 mock、missing screenshot、real screenshot、stale artifact 四类状态补前端测试。

## 风险点

- 路径穿越：content endpoint 已有 run_dir containment check，但 raw `artifacts.json` metadata 仍可能展示异常 path 字符串。
- Raw artifact 泄露：`art_evidence_json/content` 当前会直接返回 raw evidence，可能暴露绝对路径、browser profile/storage state 路径、history 文件名和执行环境路径。
- 历史 run 兼容：旧 run 没有 `run.json` / `artifacts.json`，后端会推断 artifact；这有利于历史浏览，但也会暴露未按 Web 安全规则生成的 raw artifact。
- 文件不存在：历史 `evidence.json` 中的截图多为临时目录绝对路径，当前样本中对应图片不存在，API normalized 后只能得到 `screenshot_artifact_id: null`。
- 图片加载失败：前端目前没有真实图片加载逻辑；Phase 5 加 `<img>` 后必须处理 404、403、unsupported media、CORS/base URL、空图片。
- Markdown 相对路径：report.md 可能包含 `screenshots/...`，但 API 不重写，前端也不解析，直接渲染 Markdown 后会出现断图或错误请求。
- Markdown 安全：当前 `<pre>` 展示不会执行 HTML；若引入 Markdown renderer，必须 sanitize HTML 和链接协议。
- Artifact registry 过期：`artifacts.json` 优先级较高，后续手动添加或删除截图可能导致 registry 与磁盘不一致。
- Browser history：当前 browser-use history 文件留在 workspace 根目录，不是 run artifact；若 Phase 5 暴露 history，必须先归档、脱敏、限制路径。
- 本地服务暴露：这是 local console，但若 FastAPI 绑定到非 localhost，artifact content endpoint 会成为本机文件片段读取面，需要继续限制 workspace/run_dir 和敏感 artifact。

## Phase 5 实施清单

- [ ] 后端明确 raw artifact content 策略，优先保护 `art_evidence_json/content`。
- [ ] 后端为 evidence/report 增加 linked artifact metadata 或 content URL。
- [ ] 后端补齐多截图 `screenshot_artifact_ids`。
- [ ] 后端增加 screenshot/browser-history registry 与脱敏测试。
- [ ] 后端增加 report relative screenshot link resolver。
- [ ] 后端增加 stale/missing artifact 状态和 path traversal 回归测试。
- [ ] 前端新增 Evidence Detail API client 和 deep link。
- [ ] 前端实现真实 Screenshot Preview / Gallery。
- [ ] 前端实现 sanitized raw data inspector。
- [ ] 前端用安全 Markdown renderer 替换 `<pre>` report preview。
- [ ] 前端把 evidence citation 与 report preview 打通。
- [ ] 前端补齐 missing image、forbidden artifact、not found artifact 的可见错误状态。
