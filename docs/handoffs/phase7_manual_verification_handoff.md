# Phase 7 Manual Verification Handoff

日期：2026-06-22

## 范围

本阶段实现 Web 人工验证接管闭环：当 browser-use run 进入 `awaiting_verification` 后，前端可以请求后端打开可见浏览器，用户手动完成登录/Altcha/CAPTCHA/MFA/SSO 后，后端保存 profile/storage state，并创建一个新的 retry run 使用新登录态继续走查。

## 后端变更

- 复用并扩展 `src/prodwalk/auth_session.py`：
  - 新增 `ManualAuthSession` 句柄。
  - 新增 `open_manual_auth_session`、`complete_manual_auth_session`、`close_manual_auth_session`，供 FastAPI 持有可见浏览器会话。
- 新增 API：
  - `POST /api/auth-sessions`
  - `GET /api/auth-sessions/{session_id}`
  - `POST /api/auth-sessions/{session_id}/confirm`
  - `POST /api/runs/{run_id}/retry-after-verification`
- `POST /api/runs/{run_id}/verification/confirm` 现在只记录确认，并明确说明不会恢复已经结束的 browser-use task。
- auth-session 状态包括 `created/running/awaiting_user/succeeded/failed/timeout/canceled`。
- 新增事件：
  - `auth_session.started`
  - `auth_session.awaiting_user`
  - `auth_session.completed`
  - `auth_session.failed`
  - `run.retry_started`
- 原 run metadata 记录 `verification_session_id`、`verification_status`、`retry_run_id`。
- retry run metadata 记录 `parent_run_id`、`retry_of_run_id`、`verification_session_id`。
- profile/storage state 路径限制在 workspace 下；未传时默认使用 `.prodwalk/browser-profiles/<ref-or-host>/prodwalk_storage_state.json`。
- auth-session artifact 会写入原 run 的 `auth-sessions/{session_id}.json`，仅保存脱敏会话状态，不写账号密码或本地 profile/storage state 真实路径。

## 前端变更

- `awaiting_verification` 面板改为中文人工接管流程：
  - “开始人工验证”创建 auth-session 并打开可见浏览器。
  - “我已完成，使用新登录态重新运行”确认会话、保存 storage state、创建 retry run。
  - 文案明确当前版本是 retry run，不是假装恢复原 browser-use task。
- API client 新增 `createAuthSession`、`getAuthSession`、`confirmAuthSession`、`retryRunAfterVerification`。
- Hook 保存 `authSession`、`verificationSourceRunId`、`retryRunId`。
- History 面板显示 `Retry of`、`Retry started`、`Auth <session_id>` 关系标签。
- retry run 启动后，当前 active run 自动切到新 retry run；原 run 仍可从 History 打开报告、证据、评分和截图。

## 仍然不能做什么

- 不能恢复同一个已经结束的 browser-use task；当前实现是保存登录态后创建新的 retry run。
- 不会自动绕过或破解 CAPTCHA/Altcha/MFA；必须由用户在可见浏览器中手动完成。
- 不会执行真实破坏性操作、支付、导出或设置保存；browser-use task 仍应遵守 plan 中的安全约束。
- 登录页截图仍可能包含邮箱、租户名或页面内敏感信息。代码会隐藏常见 secret/token 和本地 profile/storage path，但截图分享前仍需人工检查。

## 测试结果

已运行：

```powershell
python -m pytest
cd apps/web
npm run build
```

结果：

```text
python -m pytest: 56 passed, 1 warning
apps/web build: passed
```

## 手动验收步骤

1. 启动后端：`python -m uvicorn prodwalk.server.app:app --host 127.0.0.1 --port 8000`。
2. 启动前端：`cd apps/web; $env:VITE_API_BASE_URL="http://127.0.0.1:8000"; npm run dev -- --host 127.0.0.1 --port 5173`。
3. 使用 fresh profile 启动 Clink UAT browser-use run，并设置 `verification_mode=auto`。
4. run 进入 `awaiting_verification` 后，确认前端显示“需要你手动完成登录/验证”。
5. 点击“开始人工验证”，确认后端打开可见浏览器窗口。
6. 在浏览器中手动完成 Altcha/login/MFA/SSO。
7. 回到前端点击“我已完成，使用新登录态重新运行”。
8. 确认后端保存 storage state，并启动新的 retry run。
9. 确认 retry run 使用登录态进入 dashboard 或目标成功页。
10. 在 History 中确认原 run、auth-session、retry run 的关系可追溯，并能打开 retry run 的 report/evidence/screenshots。
