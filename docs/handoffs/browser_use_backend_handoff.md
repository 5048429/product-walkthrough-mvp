# Browser-Use Backend Handoff

日期：2026-06-17

## 范围

本次只修复 FastAPI 后端的 browser-use 运行链路和回归测试，未修改 `apps/web/`，也未修改 `src/prodwalk/agents/walker.py`。后端继续复用现有 `BrowserUseLocalWalker`，不在 server 层重写 browser-use 逻辑。

涉及文件：
- `src/prodwalk/server/runtime.py`
- `tests/test_server.py`
- `docs/handoffs/browser_use_backend_handoff.md`

## 当前行为

`POST /api/runs` 支持：
- `mode=mock`
- `mode=browser-use`
- `mode=browser-use-local`

browser-use 两种 mode 都会走 `BrowserUseLocalWalker`，并强制本地并发为 `1`。以下参数会被接收、校验、持久化到 run params，并按需传给 walker：
- `browser_model`
- `browser_max_steps`
- `browser_timeout_sec`
- `browser_user_data_dir`
- `browser_storage_state`
- `verification_mode`
- `verification_timeout_sec`
- `verification_success_url_contains`
- `verification_login_url_contains`

`verification_mode=manual` 仍兼容归一为 `auto`。标准语义是 `off` 或 `auto`。

## Verification 判定

公开 smoke 默认仍是 `verification_mode=off`，因此不会因为页面中出现登录相关文案而被折叠成 `awaiting_verification`。

`verification_mode != off` 时，后端只在明确出现以下信号时返回 `awaiting_verification`：
- `manual_verification_required` 且不是显式 false
- CAPTCHA、hCaptcha、reCAPTCHA、Altcha
- MFA、2FA、two-factor、multi-factor、OTP
- 命中 `verification_login_url_contains` 的实际浏览 URL 或 browser-use 输出 URL
- 明确的登录阻塞语义，例如 `login required`、`redirected to login page`、`login failed`

普通公开页面上的 `Login`、`Sign in` 按钮文案不会触发 `awaiting_verification`。如果配置了 `verification_success_url_contains` 且 run 已观察到成功 URL，则登录 URL 或登录文案不会再覆盖为等待验证；但明确的 manual/CAPTCHA/MFA 信号仍会优先保留。

## Artifact 暴露

browser-use run 结束后仍会生成并可通过 artifact API 读取：
- `report.md`
- `evidence.json`
- `evaluation.json`
- `screenshots/**/*`
- `browser-history/*.json`

`history_file` 会归档到 run 目录下的 `browser-history/`，然后在 evidence 中替换为安全的 `browser_history_path` 和 `browser_history_artifact_id`。本地敏感路径如 profile、storage state、executable path、raw history path 不会出现在 Evidence API 的 `data` 中。

## 状态覆盖

后端测试已覆盖 browser-use 的：
- `succeeded`
- `blocked`
- `timeout`
- `failed`
- `awaiting_verification`

同时覆盖：
- browser-use readiness 失败时返回 `BROWSER_USE_UNAVAILABLE`
- 参数校验
- browser-use-local 参数传递到 `BrowserUseLocalWalker`
- screenshot、browser history、report、evidence、evaluation artifact 可读取
- mock mode 仍能生成 report/evidence/evaluation/events/agents/artifacts
- 默认 verification off 不误判为 awaiting verification
- auto verification 不会因普通 `Login` / `Sign in` 文案误判

## 验证

已运行：

```powershell
python -m pytest tests/test_server.py
```

结果：

```text
18 passed, 1 warning
```

warning 来自 FastAPI/Starlette TestClient 的 httpx deprecation，不影响本次后端链路。

## 后续注意

`POST /api/runs/{run_id}/verification/confirm` 仍只是记录确认。如果 browser-use 后台任务已经结束，确认会把 run 从 `awaiting_verification` 转为 `blocked`，不会假装继续一个不存在的浏览器任务。真正的 Web visible-browser verification continuation 仍需要后续把 CLI 的 auth-session/retry 语义抽成 server 可复用能力。
