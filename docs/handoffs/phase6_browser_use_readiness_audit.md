# Phase 6 Browser-Use Readiness Audit

## Scope

本审计面向“从 Web 控制台启动真实 `browser-use` 本地走查”的准备情况。按要求已阅读：

- `README.md`
- `docs/frontend_console_zh.md`
- `docs/api_event_contract.md`
- `docs/handoffs/phase5_final_handoff.md`
- `src/prodwalk/cli.py`
- `src/prodwalk/agents/walker.py`
- `src/prodwalk/auth_session.py`
- `src/prodwalk/server/`

本次只审计和写文档，不修改运行代码，不运行真实 UAT，不读取或变更 credential。

## 总体结论

CLI 侧的 local `browser-use` 路径已经比较完整：能创建 `BrowserUseLocalWalker`，支持本地浏览器 profile、storage state、LLM 配置继承、超时控制、敏感 credential placeholder、人机验证 preflight，以及走查中二次人工验证重试。

Web/FastAPI 侧当前仍是 mock-first 实现。`POST /api/runs` 的 `RunStartRequest` 已经有部分 browser-use 字段，但 `RunRuntime.start_run()` 明确拒绝非 `mock` mode，并且执行路径固定为 `_execute_mock_run()` + `MockBrowserWalker()`。因此现在不能从 Web 正式启动 browser-use。

前端也处于“有入口但被 gate”的状态：UI 有 `browser-use` mode、`Start Browser Run`、`Browser max steps`、verification selector 等控件，但 hook 会在 `options.mode !== "mock"` 时直接拦截，并提示后端尚未开放 browser-use API path。需要补齐参数表单、人机验证状态闭环和后端可继续机制。

## browser-use 所需参数

### CLI `run` 参数

`src/prodwalk/cli.py` 中 `run` 子命令当前支持：

- `--config`: research plan JSON，必填。
- `--out`: 输出根目录，默认 `runs`。
- `--mode`: `mock`、`browser-use`、`browser-use-local`，默认 `mock`。
- `--concurrency`: 并发 walkthrough 数；browser-use 默认 `1`，mock 默认 `3`。
- `--browser-model`: 传给 `BrowserUseLocalWalker(model=...)`。
- `--report-language`: `en` 或 `zh`。
- `--browser-max-steps`: browser-use `agent.run(max_steps=...)`，默认 `25`。
- `--browser-timeout-sec`: 单个 browser-use scenario 最大耗时，默认 `600`，`0` 表示禁用超时。
- `--browser-user-data-dir`: 本地浏览器 profile 目录。
- `--browser-storage-state`: Playwright/browser-use storage state JSON。
- `--verification-mode`: `auto` 或 `off`，默认 `auto`。
- `--verification-timeout-sec`: 人工登录等待上限，默认 `300`。
- `--verification-success-url-contains`: 可重复传入，用于判断登录成功 URL。
- `--verification-login-url-contains`: 默认 `/auth/login`。

### `auth-session` 参数

`src/prodwalk/auth_session.py` 中单独的 `auth-session` 子命令支持：

- `--url`: 登录页或目标产品页，必填。
- `--credentials-ref`: 用于自动填充的 credential ref。
- `--user-data-dir`: 持久化 profile 目录；缺省为 `.prodwalk/browser-profiles/<ref-or-host>`。
- `--storage-state`: 可选 storage state JSON 输出路径。
- `--success-url-contains`: 可重复传入。
- `--login-url-contains`: 默认 `/auth/login`。
- `--timeout-sec`: 默认 `300`。
- `--browser-path`: Chrome/Edge 路径覆盖。
- `--manual-confirm`: 等用户按 Enter 确认。

### 环境变量和运行时配置

`BrowserUseLocalWalker` 还依赖以下运行时输入：

- LLM：`BROWSER_USE_LLM_PROVIDER`、`BROWSER_USE_MODEL`、`BROWSER_USE_LLM_API_KEY`，或继承 Codex `~/.codex/config.toml` / `~/.codex/auth.json`。
- OpenAI 兼容配置：`BROWSER_USE_OPENAI_BASE_URL`、`BROWSER_USE_OPENAI_WIRE_API`、`BROWSER_USE_REASONING_EFFORT`。
- 浏览器：`BROWSER_USE_CHROME_PATH`、`BROWSER_USE_HEADLESS`。
- 会话：`BROWSER_USE_USER_DATA_DIR`、`BROWSER_USE_STORAGE_STATE` / `BROWSER_USE_STORAGE_STATE_PATH`。
- 运行控制：`BROWSER_USE_RUN_TIMEOUT_SEC`、`BROWSER_USE_RECORD_VIDEO_DIR`、`BROWSER_USE_ALLOWED_DOMAINS`。
- credential：`<REF>_USERNAME` / `<REF>_EMAIL` / `<REF>_USER` 和 `<REF>_PASSWORD`，或本地 `CredentialStore`。

### Web API 已有字段与缺口

`RunStartRequest` 已有字段：`mode`、`concurrency`、`report_language`、`browser_model`、`browser_max_steps`、`browser_timeout_sec`、`browser_user_data_dir`、`browser_storage_state`、`verification_mode`、`verification_timeout_sec`、`verification_success_url_contains`、`verification_login_url_contains`。

缺口：

- 后端模型 `verification_mode` 是自由字符串且默认 `off`，CLI 是 `auto/off`，前端类型是 `off/manual`，三处契约不一致。
- Web 没有传 `browser_headless`、`browser_chrome_path`、`record_video_dir`、`allowed_domains`、LLM provider/base_url/wire_api/reasoning effort 等显式字段；可以先继续走环境变量，但 UI 要说明哪些由服务端环境决定。
- `browser_user_data_dir` 和 `browser_storage_state` 是敏感本地路径，应允许选择/输入已知工作区内或 `.prodwalk` 下路径，但不能作为 artifact 暴露。

## BrowserUseLocalWalker 创建和调用方式

CLI `_run()` 当前流程：

1. `load_research_plan(args.config)`。
2. 判断 `args.mode in {"browser-use", "browser-use-local"}`。
3. browser-use 默认 `concurrency=1`。
4. `_prepare_verification_checkpoints()` 根据 plan credentials 和 verification mode 预处理 profile/storage state。
5. 创建 `BrowserUseLocalWalker(model, max_steps, run_timeout_sec, user_data_dir, storage_state)`。
6. 如果 `verification_mode == "auto"`，再包一层 `HumanVerificationRetryWalker`。
7. 创建 `ResearchDirector(walker=walker, concurrency=..., report_language=...)`。
8. `await director.run(plan, run_dir)`。

`BrowserUseLocalWalker.walk()` 的核心行为：

- 构建 browser-use task，包含产品 URL、persona、goal、steps、success criteria、observation points、安全 credential placeholder、禁止破坏性操作和外部域跳转的 guardrail。
- 调 `browser_use.Agent(...).run(max_steps=self.max_steps)`。
- 用 `BrowserProfile(headless, executable_path, allowed_domains, user_data_dir, storage_state, record_video_dir)` 控制本地 Chrome/Edge。
- 保存 browser-use history 到 `browser_use_history_<slug>_<hash>.json`，并尝试脱敏。
- 从 history 中抽取 observations、action names、urls、screenshot_paths、errors。
- 返回 `WalkthroughResult`，其中 evidence 包含 `browser_run` 和 `browser_step`，step/evidence 可带 screenshot path。
- 超时或异常会返回 `blocked`，让整体 report/evaluation 仍可生成。

`ResearchDirector` 会在 walker 返回后执行：

- `EvidenceExtractor.archive_screenshots(results, run_dir)`，把存在的截图复制或规范化到 `run_dir/screenshots/`。
- 写 `evidence.json`、`report.md`、`evaluation.json`。
- 通过 event sink 发出 stage、agent、artifact、run completed/failed 事件。

## 人工验证/checkpoint 当前如何工作

当前是 CLI/terminal 驱动，不是 Web 驱动。

预检阶段：

- `_prepare_verification_checkpoints()` 只在 browser-use 且 `verification_mode != off` 时运行。
- 只对带 `credentials_ref` 的产品做验证。
- 如果未传 `--browser-user-data-dir`，且只有一个 credential ref，会自动推导 `.prodwalk/browser-profiles/<normalized_ref>`。
- storage state 默认写到 profile 下的 `prodwalk_storage_state.json`。
- `ensure_auth_session()` 用 headless persistent context 打开目标 URL，判断 session 是否有效。
- 若无效，`run_manual_auth_session()` 打开 visible browser，自动填充 username/password，用户完成 Altcha/CAPTCHA/SSO/MFA 后回终端按 Enter。

正式走查中的二次兜底：

- `HumanVerificationRetryWalker` 先调用 inner walker。
- 如果结果文本、步骤、evidence 中出现 `manual_verification_required`、`/auth/login`、`altcha`、`captcha`、`login failed` 等标记，且该 credential ref 尚未重试过，则打开 visible browser 让用户验证。
- 用户在终端按 Enter 后，重新执行同一个 walkthrough 一次。

Web 现状：

- API 有 `POST /api/runs/{run_id}/verification/confirm`。
- 但当前实现只在 run 状态为 `awaiting_verification` 时改回 `running` 并追加一条 `agent.status_changed` 事件。
- 没有后端等待对象、future/condition、browser window 管理、auth-session task，也没有把 Web confirm 连接到 `run_manual_auth_session()`。
- 因此它目前是“记录确认”的 API，不是“继续执行”的控制面。

## 后端 API 缺口

### 运行入口

- `RunRuntime.start_run()` 当前直接拒绝 `request.mode != "mock"`。
- 执行任务固定创建 `_execute_mock_run()`。
- `runtime.py` 只 import `MockBrowserWalker`，没有 import/create `BrowserUseLocalWalker`、`HumanVerificationRetryWalker` 或 auth-session helper。
- `_request_params()` 没有保存 `browser_user_data_dir`、`browser_storage_state` 等路径字段；这是合理的安全默认，但需要保存脱敏摘要，例如 `profile_configured: true`、`storage_state_configured: true`。
- 没有 single active browser-use guard。真实本地 Chrome/CDP 不宜并发多个 browser-use run。

### 验证状态和继续机制

- 需要 `run.awaiting_verification` 事件和 run status `awaiting_verification` 的真实触发点。
- 需要后端持有“等待 Web confirm”的异步控制对象，而不是 `input()`。
- 需要一个 Web 版 auth-session/preflight API 或 runtime service，用 visible browser 打开登录页、填充 credential、写回 storage state/profile。
- `confirm_verification()` 需要能够唤醒等待中的 preflight 或 retry，而不是只写事件。
- 需要失败/超时/取消路径：verification timeout、user cancel、browser launch failed、profile locked、credential missing。

### browser-use 参数校验

- `mode` 应约束为 `mock | browser-use | browser-use-local` 或 Web 只暴露 `mock | browser-use`。
- `verification_mode` 应统一：建议后端/前端/API 使用 `auto | off`，UI copy 可显示为自动 checkpoint。
- browser-use 默认 concurrency 应为 `1`，并限制本地 browser-use run 并发。
- `browser_max_steps`、`browser_timeout_sec`、`verification_timeout_sec` 需要合理 min/max。
- `browser_user_data_dir`、`browser_storage_state` 应限制在 workspace 或 `.prodwalk` 允许目录内，避免任意本地路径写入。
- 需要检测可用依赖：`browser-use`、`playwright`、Chrome/Edge executable，并以 API 错误返回。

### 事件与进度

- 现有 `PipelineEventAdapter` 可以消费 `ResearchDirector` 事件，但事件文案还是 “Mock research pipeline started/completed”。
- 当前 pipeline 没有逐步发出 `scenario.step.started/completed`，browser-use step telemetry 只能在 scenario 完成后从 `WalkthroughResult.steps` 推断。
- 需要在 blocked/manual verification 时将 walker agent 标记为 `waiting`，auth_session agent 标记为 `running/waiting/succeeded/failed`。
- `cancel_run()` 当前取消 asyncio task，但 browser-use cancel 需要确保 browser-use agent/browser context 被关闭；`BrowserUseLocalWalker` 已有 `CancelledError` 后调用 `agent.stop/close` 的尝试，但 Web runtime 要把取消传到正确 task。

### artifact 和安全

- `RunRuntime._build_artifacts()` 会注册固定 artifact 和 `run_dir/screenshots/**/*` 图片，但不注册 browser-use history、video、log。
- `BrowserUseLocalWalker` 的 history 文件默认保存在当前工作目录，不在 run_dir；Web 接入前应移动到 `run_dir/browser-history/`，脱敏后注册为 `browser_history` artifact。
- `GET /artifacts/{artifact_id}/content` 对 JSON 直接返回 raw JSON。对 browser-use `evidence.json`，raw data 可能包含 `history_file`、`executable_path`、`user_data_dir`、`storage_state`、绝对截图路径。`GET /evidence` 已做 sanitized normalize，但 raw artifact content 仍是风险。
- `read_evidence()` 当前只返回第一个匹配的 `screenshot_artifact_id`，前端类型支持多截图；browser-use step 多截图场景需要补 `screenshot_artifact_ids`。
- 需要 `screenshot.archived` 或 screenshot `artifact.created` 事件，便于前端在截图到达后刷新。

## 前端 UI 缺口

当前已有：

- `RunModeSelector` 支持 `mock` / `browser-use`。
- `Browser max steps` 控件。
- Verification selector，但值为 `off` / `manual`。
- 顶部 `Start Browser` 按钮。
- Evidence detail、ScreenshotPreview、artifact link、ReportMarkdown 资产映射能力。
- `confirmVerification()` API client。

当前缺口：

- `useProdwalkConsole.startRun()` 明确 gate：非 mock 直接报错，且发送请求时强制 `mode: "mock"`。
- browser-use 参数表单不足：缺少 browser model、timeout、profile dir、storage state、success URL contains、login URL contains、headless/debug visible、LLM/provider 环境状态提示。
- 前端默认 browser-use `concurrency: 3`，与 CLI 推荐默认 `1` 冲突。
- verification mode 前端类型是 `off | manual`，后端/CLI 是 `off | auto`。
- “Start Browser Run” 没有预检提示：本地浏览器会被打开、可能使用 profile、可能需要人工验证、credential 不会显示。
- 没有 `awaiting_verification` 专用 UI：当前 blocked 状态只泛化展示，缺少“visible browser 已打开/等待你完成验证/确认继续/取消/超时倒计时”。
- 没有 profile/storage state 选择或最近使用 profile 记忆。
- 没有明确的 browser-use active run guard UI：当一个真实 browser-use run 运行时应禁用再次启动。
- 没有环境 readiness panel：依赖是否安装、Chrome/Edge 是否找到、LLM key/config 是否可用、server 是否允许 browser-use。
- `confirmVerification()` 虽有 client，但当前 UI 没有按钮/流程调用它。

## 人工验证流程设计

建议分两阶段接入，先做“Web 控制，后端仍打开本机 visible browser”，不做浏览器嵌入。

### 状态机

建议 run 状态：

- `queued`
- `starting`
- `running`
- `awaiting_verification`
- `finalizing`
- `succeeded`
- `failed`
- `canceled`

建议 auth_session agent 状态：

- `pending`
- `running`: 正在检查或打开 visible browser。
- `waiting`: 等用户完成 Altcha/CAPTCHA/SSO/MFA。
- `succeeded`: profile/storage state 已刷新。
- `failed`: 超时、用户取消、浏览器启动失败、仍检测到 login form。

### API 设计建议

最小可行：

- `POST /api/runs` 接收 `mode=browser-use` 和 browser-use 参数。
- 后端 preflight 需要验证时，发出 `run.awaiting_verification` 事件，payload 包含 `verification_id`、`product`、`url`、`profile_label`、`timeout_sec`、`instructions`，不含 credential/path secret。
- `POST /api/runs/{run_id}/verification/confirm` 唤醒后端等待对象。
- `POST /api/runs/{run_id}/verification/cancel` 或复用 cancel run。

更完整：

- `GET /api/browser-use/readiness`: 返回依赖、浏览器路径、LLM provider/model 来源、是否有 API key、browser-use 是否可 import。
- `GET /api/browser-use/profiles`: 只列 `.prodwalk/browser-profiles` 下可用 profile 摘要。
- `POST /api/auth-sessions`: 单独创建/刷新 profile，不启动完整 research run。
- `GET /api/auth-sessions/{id}` 和 SSE 事件，用于 profile preflight。

### 前端交互

- Run Start 中选择 browser-use 后显示高级参数区，默认收起危险/路径项。
- 启动前显示本地运行提示：会打开本机 Chrome/Edge、可能访问真实环境、不要进行破坏性操作。
- `awaiting_verification` 时显示专门 banner/panel：目标产品、当前 URL 或登录域、倒计时、确认按钮、取消按钮、最近事件。
- 用户完成浏览器内验证后点击 “Confirm verified”，前端调用 `confirmVerification()`。
- 确认后状态回到 running，SSE 继续显示 walker 事件。
- 超时或用户取消时保留 partial evidence，并展示 blocked/failed 原因。

## 截图/artifact 处理方式

当前 pipeline 已有基础：

- browser-use history 产生 screenshot paths。
- `BrowserUseLocalWalker` 把 screenshot path 放入 `EvidenceItem.screenshot`、`WalkStep.screenshot` 或 `data.screenshot_paths`。
- `EvidenceExtractor.archive_screenshots()` 在写 `evidence.json` 前把存在的本地截图复制到 `run_dir/screenshots/`，并把引用改成 run 内相对路径。
- FastAPI 扫描 `run_dir/screenshots/**/*` 注册 `screenshot` artifact。
- `GET /api/runs/{run_id}/screenshots/{filename}` 和 artifact content/path API 能读取图片。
- 前端 `ScreenshotPreview` 能通过 artifact metadata 或 fallback URL 渲染图片。
- `ReportMarkdown` 能把 report 中安全的 `screenshots/...` 相对链接映射到后端 artifact/path URL。

Web browser-use 接入时建议：

- screenshot 只暴露归档到 run_dir 内的文件。
- `evidence.json` raw 下载要么禁用，要么提供脱敏版本；默认 UI 使用 `GET /evidence`。
- browser history 必须先脱敏，再移动到 `run_dir/browser-history/`，再注册 `browser_history` artifact。
- 不把 browser profile、storage state、credential store 注册为 artifact。
- normalized evidence 同时返回 `screenshot_artifact_id` 和 `screenshot_artifact_ids`。
- screenshot artifact metadata 保持 `content_url`，前端不拼本地路径。
- 对 report 中无法解析或越界的图片链接显示 unresolved，不直接访问本机绝对路径。

## 风险点

- 真实环境误操作：browser-use prompt 已要求不做 destructive actions，但 Web UI 仍需提醒，plan 也应避免付款、删除、提交等动作。
- 认证状态不稳定：Altcha/CAPTCHA/MFA/session 过期会导致 retry 和 partial evidence，需要可见状态和超时。
- profile 锁定：Chrome persistent profile 可能被另一个进程占用，后端要明确错误。
- 并发风险：多个本地 browser-use run 可能触发 Chrome/CDP 启动超时或互相污染 profile。
- 契约漂移：CLI `auto/off`、后端默认 `off`、前端 `manual/off` 当前不一致。
- raw artifact 泄露：`art_evidence_json/content` 和历史 run raw artifacts 可能暴露本地路径、history 文件、storage state 路径等环境信息。
- history 文件位置：当前 history 默认落在 cwd，Web 接入前要归档到 run_dir 并清理或忽略根目录残留。
- 依赖缺失：`browser-use-local` 是 optional dependency，server-only 安装不一定有 browser-use/playwright。
- LLM 配置不可见：Web 用户可能不知道后端继承了哪个 provider/model/key；readiness API 只能显示来源和是否存在，不能显示 secret。
- Cancel 清理：取消 browser-use run 必须关闭 agent/browser context，否则 visible/headless 浏览器可能残留。
- 历史 run 兼容：`runs*` 扫描会把旧 CLI run 纳入 Web，旧 raw browser-use artifact 可能未按新安全规则生成。

## 分阶段实现建议

### Phase 6A: 契约和 readiness，不启动真实 browser-use

1. 统一 API/前端/CLI verification mode：建议 `auto | off`。
2. 增加 backend readiness API，检查 optional dependency、Playwright、browser executable、LLM config 来源。
3. 前端新增 browser-use readiness panel 和参数表单，但继续 gate 启动。
4. 增加测试覆盖非 mock mode 仍被拒绝、readiness 缺依赖提示、参数校验。

### Phase 6B: Web 启动 browser-use smoke，不做人工验证闭环

1. 后端允许 `mode=browser-use` 且 `verification_mode=off`。
2. Runtime 创建 `BrowserUseLocalWalker`，browser-use 默认 concurrency `1`。
3. 复用 `PipelineEventAdapter`，修正文案中 mock-specific copy。
4. 限制 single active browser-use run。
5. 只跑 public smoke plan，不使用 credentials。
6. 确认 report/evidence/evaluation/screenshot artifact 能从 Web 查看。

### Phase 6C: 人工验证 preflight 闭环

1. 把 `ensure_auth_session()` 拆成可被 Web runtime 驱动的 service，去掉 terminal `input()` 依赖。
2. 需要人工时发 `run.awaiting_verification`，设置 run status。
3. Web 显示 verification panel，用户点击 confirm 后唤醒后端。
4. 支持 timeout、cancel、失败重试一次。
5. profile/storage state 路径限制在 `.prodwalk` 或 workspace 允许区。

### Phase 6D: 走查中二次验证和 artifact 安全

1. 将 `HumanVerificationRetryWalker` 的 terminal confirm 改为 Web confirm 机制。
2. browser history 脱敏后归档为 `browser_history` artifact。
3. 明确 raw artifact content 策略，保护 `evidence_json`、`browser_history`、历史 run。
4. 增加 screenshot/browser-history artifact 事件。
5. normalized evidence 补齐多截图、linked artifacts、linked events。

### Phase 6E: 真实 UAT 前验收

1. 先从 public `examples/smoke_plan.json` browser-use Web run 验收。
2. 再用非敏感 authenticated sandbox plan 验证 profile/verification。
3. 最后才跑 Clink UAT，且保持 `concurrency=1`、有明确 read-only plan、开启超时。
4. 验收项包括：SSE 状态、manual checkpoint、cancel cleanup、截图预览、report 链接、raw artifact 安全、历史 run 展示。

## 推荐下一步

不要直接从前端放开真实 UAT。先做 Phase 6A/6B：统一契约，增加 readiness API，并让 Web 能启动 `verification_mode=off` 的 public browser-use smoke run。这个步骤最小、风险最低，也能最快暴露 browser-use 依赖、LLM、Chrome/CDP 和 artifact 管线问题。
