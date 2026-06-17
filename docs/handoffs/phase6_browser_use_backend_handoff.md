# Phase 6 Browser-Use Backend Integration Handoff

## Scope

本阶段让 FastAPI 后端可以从 `POST /api/runs` 启动本地 browser-use run，改动范围保持在：

- `src/prodwalk/server/runtime.py`
- `src/prodwalk/server/models.py`
- `tests/test_server.py`

未修改 `apps/web/`、`src/prodwalk/agents/walker.py`、`src/prodwalk/cli.py`。

## Backend Behavior

`POST /api/runs` 现在支持：

- `mode=mock`
- `mode=browser-use`
- `mode=browser-use-local`

browser-use 两种 mode 都复用现有 `BrowserUseLocalWalker`，并继续通过 `ResearchDirector` 和 `PipelineEventAdapter` 发 SSE 事件。mock mode 仍走 `MockBrowserWalker`，默认 concurrency 仍为 `3`。

browser-use 参数支持：

- `browser_model`
- `browser_max_steps`
- `browser_timeout_sec`
- `browser_user_data_dir`
- `browser_storage_state`
- `verification_mode`
- `verification_timeout_sec`
- `verification_success_url_contains`
- `verification_login_url_contains`

`verification_mode=manual` 会被后端兼容归一为 `auto`，以接住当前 Web console 可能发送的值。`auto` / `off` 仍是后端标准值。

## Validation And Readiness

非 mock mode 增加了后端校验：

- browser-use mode 必须 `concurrency=1`。
- `browser_max_steps` 范围为 `1..200`。
- `browser_timeout_sec` 范围为 `0..7200`，`0` 表示由 walker 侧禁用超时。
- `verification_timeout_sec` 范围为 `1..3600`。
- `browser_user_data_dir` 和 `browser_storage_state` 请求路径必须留在 workspace 内。
- 启动前检查 `browser_use`、`playwright.async_api` 是否可 import。
- 启动前检查 LLM provider 所需 key 是否可用；OpenAI-compatible 路径支持环境变量或 Codex auth.json。

依赖或配置不足时，API 返回：

- HTTP `503`
- code `BROWSER_USE_UNAVAILABLE`
- details.errors 中包含可读原因

## Run Status Mapping

`ResearchDirector` 在产出 report/evidence/evaluation 后仍会发 pipeline completed 事件。后端会在最终更新 run manifest 前读取 `evidence.json`，对 browser-use mode 做状态折算：

- `succeeded`: 所有 browser-use walkthrough completed。
- `blocked`: 至少一个 walkthrough blocked。
- `timeout`: evidence/metrics 显示 browser-use timed out。
- `failed`: evidence 显示 browser-use run failed 或无有效结果。
- `awaiting_verification`: `verification_mode != off` 且结果文本包含 manual verification/auth markers。

新增 run status literal：

- `timeout`

SSE terminal event 对应：

- `run.completed`
- `run.blocked`
- `run.timeout`
- `run.failed`
- `run.awaiting_verification`

`awaiting_verification` 当前反映状态与事件；现有 `verification/confirm` 会记录确认。如果后台任务已经结束，confirm 会把 run 置为 `blocked`，不会假装恢复一个不存在的 task。

## Artifacts

固定 artifact 和 screenshot artifact 保持不变：

- `report.md`
- `evidence.json`
- `evaluation.json`
- `screenshots/**/*`

新增 browser history artifact：

- browser-use evidence 中的 `history_file` 会被复制到 `run_dir/browser-history/*.json`。
- `browser-history/*.json` 会注册为 `browser_history` artifact。
- history JSON 会做后端侧敏感字段清理。
- server browser-use evidence 会移除 raw `history_file`、`user_data_dir`、`storage_state`、`executable_path` 等本地敏感路径。
- 已归档的 `screenshots/...` 相对路径会保留，所以 Evidence API 仍可映射截图 artifact。

Evidence API 现在在保留旧字段 `screenshot_artifact_id` 的同时，补充：

- `screenshot_artifact_ids`

## Tests

新增/更新 `tests/test_server.py` 覆盖：

- mock run 仍生成 report/evidence/evaluation/events/agents/artifacts。
- browser-use 依赖不可用时返回清晰 `BROWSER_USE_UNAVAILABLE`。
- browser-use 参数校验。
- fake browser-use-local run 会调用 `BrowserUseLocalWalker` 参数，并暴露 screenshot、browser history、report、evidence、evaluation artifacts。
- browser-use final status 能反映 blocked、timeout、failed、awaiting_verification。

验证命令：

```powershell
pytest tests/test_server.py -q
pytest -q
```

结果：

- `tests/test_server.py`: 16 passed
- full suite: 50 passed

唯一 warning 来自 FastAPI/Starlette TestClient 的 httpx deprecation。

## Follow-Up Notes

本阶段没有修改前端，也没有重写 `auth_session.py` 的 terminal/manual-confirm 流程。后端已经能启动 browser-use，并能把 `awaiting_verification` 作为状态和 SSE 事件暴露；真正的 Web-driven visible-browser verification continuation 仍需要后续把 auth-session 的等待对象接到 `/verification/confirm`。
