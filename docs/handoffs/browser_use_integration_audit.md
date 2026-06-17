# Browser-use Integration Audit

日期：2026-06-17

范围：只读审计当前项目的 Web 控制台接入 browser-use 真实页面测试现状。未运行 Clink UAT，未修改 credentials，未修改业务代码。本文件是本次审计唯一新增产物。

## 已阅读文件

- `README.md`
- `docs/frontend_console_zh.md`
- `docs/handoffs/phase6_final_handoff.md`
- `src/prodwalk/cli.py`
- `src/prodwalk/agents/walker.py`
- `src/prodwalk/auth_session.py`
- `src/prodwalk/server/runtime.py`
- `src/prodwalk/server/models.py`
- `apps/web/src/hooks/useProdwalkConsole.ts`
- `apps/web/src/components/runs/`
- 额外核对：`src/prodwalk/server/app.py`、`apps/web/src/types/contracts.ts`、`apps/web/src/api/client.ts`、`apps/web/src/pages/ConsolePage.tsx`、相关 tests 和 examples。

## 总体结论

Web 控制台已经具备“启动本地 browser-use 真实页面 run”的基本链路：`POST /api/runs` 支持 `browser-use` 和 `browser-use-local`，前端能提交 max steps、timeout、verification、profile、storage_state 等参数，后端能调用 `BrowserUseLocalWalker` 并归档 report/evidence/evaluation/screenshots/browser history。

但 Web 侧对 authenticated UAT 和人工验证仍不完整。CLI 已经有完整得多的 auth-session preflight 和 retry wrapper；Web API 目前只是接收 verification 参数、根据 evidence 文本把最终状态折算成 `awaiting_verification`，`POST /verification/confirm` 也只是记录确认，不会重新打开可见浏览器、不会 refresh storage state、不会恢复或重试 browser-use 任务。

因此当前最可靠路径仍是：

- 公开 smoke：Web 可以跑，默认应使用 `verification_mode=off`。
- Clink-style authenticated UAT：继续优先使用 CLI human-assisted profile 流程；若从 Web 发起，必须先准备好 profile/storage_state，且不能期待 Web confirm 真正续跑。

## 1. 后端 POST /api/runs 对 browser-use 的支持是否完整

结论：基础 browser-use run 支持基本完整；verification/authenticated continuation 不完整。

已经支持：

- `RunStartRequest` 包含 `mode`、`browser_model`、`browser_max_steps`、`browser_timeout_sec`、`browser_user_data_dir`、`browser_storage_state`、`verification_mode`、`verification_timeout_sec`、`verification_success_url_contains`、`verification_login_url_contains`。
- runtime 接受 `browser-use` 和 `browser-use-local`，强制本地 browser-use `concurrency=1`，校验 max steps、timeout、verification timeout 和 profile/storage_state 路径。
- backend readiness 会检查 `browser_use`、`playwright.async_api` 和 LLM key/provider 配置。
- `_walker_for_options` 会把 model、max_steps、timeout、user_data_dir、storage_state 传给 `BrowserUseLocalWalker`。
- browser screenshots 和 browser history 会被 postprocess 到 run directory，artifact API 可读。
- `_final_status_from_evidence` 能把 browser-use run 折算成 `succeeded`、`blocked`、`timeout`、`failed`、`awaiting_verification`。

缺口：

- Web runtime 没有调用 CLI 里的 `_prepare_verification_checkpoints` / `ensure_auth_session`，所以 `verification_mode=auto` 不会预先验证或刷新登录态。
- Web runtime 没有包 `HumanVerificationRetryWalker`，所以 browser-use 遇到 Altcha/CAPTCHA/login 后不会自动打开可见浏览器让人处理并重试。
- `verification_timeout_sec`、`verification_success_url_contains`、`verification_login_url_contains` 在 Web runtime 里基本只被校验和持久化，没有参与 auth preflight 或 continuation。
- `POST /api/runs/{run_id}/verification/confirm` 只是 append 一个 `agent.status_changed` 事件；如果任务已经结束，状态会变成 `blocked`，没有实际续跑能力。
- `_request_params` 出于安全只记录 `browser_user_data_dir_configured` 和 `browser_storage_state_configured`，不记录真实路径；这对安全是好事，但 UI 无法从历史 run 直接确认使用了哪个 profile。

## 2. 前端是否能提交 browser-use 参数

结论：能提交。

证据：

- `RunModeSelector` 提供真实浏览器模式，并暴露 max steps、timeout、verification mode、profile 目录、storage state 文件、verification timeout、success URL contains、login URL contains。
- `RunStartPanel` 默认 `verificationMode` 是 `off`，切换到 browser-use 时设置 concurrency 为 1，并把高级参数拼入 launch payload。
- `useProdwalkConsole.startRun` 会把这些字段放入 `RunCreateRequest` 后 POST `/api/runs`。
- `apps/web/src/types/contracts.ts` 和 `apps/web/src/api/client.ts` 的 request/response 类型已包含这些字段。

前端缺口：

- `useProdwalkConsole.startRun` 对 browser-use 的 fallback 默认是 `options.verificationMode ?? "auto"`；正常 UI 会传 `off`，但其他入口若漏传会变成 auto，不适合公开 smoke。
- `awaiting_verification` 被 `toConsoleStatus` 映射成 `blocked`，顶部 badge 仍容易显示为受阻，而不是专门的等待验证状态。
- `terminalRunStatuses` 和 `terminalEventTypes` 没有包含 `awaiting_verification` / `run.awaiting_verification`，SSE 和 artifact refresh 的终态判断会含糊。
- “我已完成验证，继续”按钮文案暗示可以恢复 run，但当前后端 confirm 不会续跑。
- UI 没有 browser-use readiness panel，也没有在按钮层明确阻止第二个 browser-use run；目前主要靠后端 409 guard。

## 3. 公开 smoke plan 是否应该默认 verification_mode=off

结论：应该默认 `verification_mode=off`，并且建议所有 public smoke 文档、UI 快捷入口和测试都显式使用 off。

原因：

- `examples/smoke_plan.json` 是公开 Wikipedia 页面，没有 credentials_ref，也不应该触发 auth preflight。
- Web backend 的 `awaiting_verification` 是 evidence 文本启发式折算：只要 `verification_mode != off` 且 evidence/final output/errors/urls 中出现 `manual_verification_required`、`/auth/login`、`authentication is required`、`login failed` 等 marker，就会进入 `awaiting_verification`。
- 对公开页面，auto 没有实际 preflight 价值，却会放大 LLM 摘要、页面文字或 browser-use 中间错误里的 auth marker，造成误判。
- Phase 6 handoff 已记录公开 smoke 曾经产出 artifacts/evaluation，但最终状态被折算成 `awaiting_verification`。

当前代码状态：

- API model 默认 `verification_mode="off"`。
- `RunStartPanel` 默认 `verificationMode` 为 `off`，且 UI 文案写明公开页面推荐关闭。
- 仍需修正 hook 默认和文档/测试，避免非 UI 入口或未来快捷入口漏传时退回 auto。

## 4. Authenticated UAT 是否需要 verification_mode=auto、profile、storage_state

结论：需要，但当前 Web 只能消费这些参数，不能完整管理它们。

推荐 UAT 配置：

- `verification_mode=auto`
- `browser_user_data_dir=.prodwalk/browser-profiles/clink_uat_account`
- `browser_storage_state=.prodwalk/browser-profiles/clink_uat_account/prodwalk_storage_state.json`
- `verification_login_url_contains=/auth/login`
- `verification_success_url_contains=/analytics` 或其他明确的 authenticated landing path
- plan 中保留 `credentials_ref=CLINK_UAT_ACCOUNT`，不要写真实账号密码。

原因：

- Clink UAT 有 login/Altcha/CAPTCHA/MFA 风险，纯 browser-use headless run 容易被重定向或卡住。
- 持久 profile 是 CLI README 中推荐路径，storage state 是辅助复用和刷新登录态的产物。
- `verification_mode=auto` 应用于 UAT 时应该表示：run 前检查 profile 是否已登录；未登录则打开可见浏览器让人完成；browser-use 途中遇到验证再打开可见浏览器并重试一次。

当前 Web 差距：

- Web 不会自动 derive profile path。
- Web 不会调用 `ensure_auth_session` 检查或刷新 storage state。
- Web 不会用 `HumanVerificationRetryWalker` 在 browser-use 途中 retry。
- 如果 profile/storage_state 事先没有通过 CLI 准备好，Web 发起 UAT run 很可能仍停在登录/验证处或被折算成 `awaiting_verification`。

## 5. 真实页面测试失败或误判 awaiting_verification 的原因

主要原因是状态折算和真实 continuation 脱节。

后端层面：

- `BrowserUseLocalWalker._classify_run` 把大多数非空 final output 当成 `completed`，不会把 `manual_verification_required` 本身作为 blocked marker。
- Web runtime 之后再用 `_final_status_from_evidence` 扫描整份 evidence 文本；只要 `verification_mode != off` 且出现 auth marker，就把最终 run 置为 `awaiting_verification`。
- 这个判断不要求 plan 有 `credentials_ref`，不要求实际当前 URL 是 login page，也不验证 profile/storage_state 是否可用，因此对 public smoke 可能误判。
- `awaiting_verification` 是 run 结束后的状态折算，不是一个真正挂起的 browser task。`_execute_run` finally 会清空 active browser run；confirm 时通常没有可继续的 task。

前端层面：

- UI 有 awaiting verification panel，但按钮调用的后端 confirm 不能续跑。
- `awaiting_verification` 同时被展示为 blocked 风格，容易让操作者误以为真实页面测试失败，而不是“artifacts 已生成但状态启发式误判/等待人工验证”。
- SSE 终态集合缺少 `run.awaiting_verification`，可能导致连接/刷新状态与真实 run 完成状态不一致。

测试和文档层面：

- 现有测试覆盖了 browser-use 参数传递、路径校验、artifact 暴露、以及 marker 导致 `awaiting_verification`。
- 但缺少 Web auth preflight/retry 的测试，因为 Web 当前没有实现这条链。
- 缺少 public smoke 默认 off 的前端回归测试。

## 6. 建议修改

### 后端

1. 把 CLI auth 能力抽到可复用模块，供 CLI 和 server runtime 共用：
   - derive/resolve profile path
   - ensure auth session
   - refresh storage state
   - manual retry wrapper

2. Web `verification_mode=auto` 应具备真实语义：
   - 对带 `credentials_ref` 的产品，run 前调用 auth preflight。
   - 如未传 `browser_user_data_dir`，按 credentials_ref 或 host 自动推导 `.prodwalk/browser-profiles/<ref-or-host>`。
   - 自动设置或刷新 `prodwalk_storage_state.json`。
   - browser-use 途中遇到 manual verification marker 时，打开可见浏览器、等待用户完成、然后 retry 一次。

3. 调整 `awaiting_verification` 判定：
   - public/no-credentials run 默认不进入 awaiting verification。
   - `verification_mode=off` 时不要因 auth marker 折算 awaiting。
   - `verification_mode=auto` 时优先要求结构化 final output 的 `manual_verification_required: true`，并结合 credentials_ref、login URL、step status，而不是宽泛全文匹配。
   - 把 `manual_verification_required` 纳入 walker 层结构化状态，减少 runtime 二次猜测。

4. 改造 `POST /verification/confirm`：
   - 要么实现真正 continuation/retry。
   - 要么改成只读 acknowledge，并返回明确状态/错误，避免“继续”错觉。

5. 补充 readiness：
   - 检查 browser executable 是否可用。
   - 检查传入 profile/storage_state 是否存在或可创建。
   - 对 Web 返回更清晰的 browser-use readiness details。

### 前端

1. 公开 smoke 和普通 browser-use 默认保持 `verificationMode="off"`；hook 的 browser-use fallback 也改成 off，避免漏传时 auto。

2. 将 `awaiting_verification` 作为独立显示状态：
   - StatusBadge 不要只归一成 blocked。
   - Current Run Status 展示“等待人工验证/或需人工验证确认”，不要混同普通 blocker。

3. 更新 SSE 终态判断：
   - `terminalRunStatuses` 加入 `awaiting_verification`，或引入单独的 waiting-terminal 概念。
   - `terminalEventTypes` 加入 `run.awaiting_verification`，并触发 artifacts/history refresh。

4. 调整 confirm 文案：
   - 在后端未实现 continuation 前，把按钮文案改成“记录已完成验证”或隐藏按钮。
   - 若后端实现 retry，再恢复“继续”语义，并显示 retry 状态。

5. 增加 browser-use readiness/guard UI：
   - 依赖、LLM key、browser path、headless/env、active browser-use run。
   - 前端禁用第二个 browser-use start，后端 409 仍保留。

### 测试

后端测试：

- 保留现有 fake walker 测试，不跑真实 Clink UAT。
- 增加 `verification_mode=off` 下 public smoke 不会折算 `awaiting_verification` 的回归测试。
- 增加 server runtime auto verification 测试：mock `ensure_auth_session`，断言 profile/storage_state 被 derive 和传给 walker。
- 增加 retry wrapper 测试迁移到 server path：第一次返回 manual verification，mock manual auth 后第二次成功。
- 增加 `POST /verification/confirm` 的语义测试：若没有 continuation，应明确返回 blocked/ack；若实现 continuation，应断言会恢复 running/retry。

前端测试：

- `RunStartPanel` browser-use 默认 payload 中 `verification_mode` 为 `off`。
- 填写 profile/storage_state/success URL/login URL 后请求体完整传到 `createRun`。
- `run.awaiting_verification` 触发 artifact refresh 和 SSE closure。
- `awaiting_verification` 显示独立 copy/badge，不再只显示 blocked。
- confirm 按钮文案与后端真实语义一致。

手工 smoke：

- public smoke：`examples/smoke_plan.json`，browser-use，`verification_mode=off`，期望 artifacts 生成且 final status 不为 `awaiting_verification`。
- authenticated UAT：不在普通自动测试中跑；只在人工授权窗口中用 CLI 或已实现的 Web auth continuation 跑，且必须使用 profile/storage_state，不改 credentials。

## 建议优先级

P0：把 public smoke 默认和测试固定为 `verification_mode=off`，并让 `awaiting_verification` 成为清晰独立状态，减少误判噪音。

P1：把 CLI auth-session preflight/retry 抽成 server 可用能力，补齐 Web `verification_mode=auto` 的真实语义。

P2：完善 readiness panel、single-active UX guard、历史 run 中 profile/storage_state 的安全可解释展示。
