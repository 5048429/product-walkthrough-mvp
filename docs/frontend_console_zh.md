# Prodwalk 前端控制台中文说明

本文档说明当前 `prodwalk` Web 控制台的能力、启动方式、简化后的使用流程、browser-use 支持状态、测试验收记录和常见问题。当前版本已经完成 Phase 7 Web 人工验证接管闭环：mock run 闭环可用，browser-use 请求可从前端提交，遇到 `awaiting_verification` 后可以打开可见浏览器让用户手动验证，并使用新登录态创建 retry run。

## 当前结论

当前阶段重点已经从 Phase 6 的 browser-use 接入，推进到 Phase 7 的人工验证接管和 retry 闭环：

1. 默认 UI 已简化，普通使用者优先看到 plan、run 状态、agent progress、report、evidence、evaluation 和 history。
2. Debug 信息默认收起，API / Debug、完整 Agent Status 和 Live Event Log 保留在 Details tab 中。
3. `mock` mode 是当前最稳定的 Web 控制台主路径。
4. `browser-use` mode 已能从 Web 控制台提交请求；当最终状态为 `awaiting_verification` 时，前端可以创建 auth-session、打开可见浏览器、保存登录态，并发起新的 retry run。
5. 旧 CLI 入口仍然可用，适合自动化脚本、真实 UAT 调试和回归验证。

## 当前能力

当前 Web 控制台具备以下能力：

- 本地 FastAPI 后端服务。
- React + Vite + TypeScript 前端控制台。
- 从前端读取 `examples/` 下的 research plan。
- 从前端启动 `mock` mode run。
- 从前端提交 `browser-use` mode run 参数。
- 通过 SSE 实时接收 run 事件。
- 展示当前 run 状态、进度、elapsed、run id 和 selected plan。
- 展示简化 Agent Progress 和 Recent Activity。
- run 完成后展示 `report.md` 预览。
- 展示 `evidence.json` 摘要、证据列表和截图入口。
- 展示 `evaluation.json` 评分。
- 展示历史 run。
- 支持 artifact、report、evidence、evaluation 和 screenshot 的安全读取接口。
- 保持原有 CLI 入口兼容。

## UI 简化后的使用说明

默认 Dashboard 现在面向日常 PM 走查，不再把调试信息作为第一屏主内容。

常用区域：

- Plan selector：选择 `examples/` 中的 research plan，并查看 plan summary。
- Mode selector：选择 `mock` 或 `browser-use`。
- Start Mock Run / Start Browser-use Run：启动当前 plan。
- Stop：请求取消当前 run。
- Open Report：在有 report artifact 后快速打开报告。
- Current Run Status：查看状态、进度、耗时和 run id。
- Agent Progress：查看各 agent 的精简进度。
- Recent Activity：查看最近事件摘要。
- Results shortcut：快速跳转 report、evidence、evaluation、screenshots。
- Report Preview：直接查看报告内容。
- Evidence / Screenshots：默认折叠，按需展开。
- Run History：打开历史 run。

调试区域：

- Details tab 中保留 `API / Debug`、`Agent Status`、`Live Event Log`。
- 默认 Dashboard 不直接显示 API source、SSE 状态、run dir、artifact ids 和 raw event payload。
- 如果 run 行为异常，先打开 Details tab 查看 SSE 是否连接、事件是否到达、artifact id 是否存在。

## browser-use 当前支持状态

当前状态可以概括为：可启动、可提交、可产物化，但还不是完全自动闭环。

已验证：

- 后端真实 `browser-use` 可以运行公开 smoke plan。
- 前端切换到 `browser-use` mode 后可以提交请求。
- 前端会显示 browser-use 参数，包括 max steps、timeout、verification mode 和 headless/visible server env note。
- Advanced browser-use parameters 默认折叠。
- 后端参数校验有效，例如 `browser_max_steps=0` 会返回可读错误。
- 真实 browser-use smoke run 已产出 report、evidence、evaluation、screenshots 和 browser history artifact。

Phase 6 验收记录：

```text
API valid run: run-20260617-142228-c53abd
final status: awaiting_verification
progress: 1/1
screenshots: 6
run error: Browser-use reported that manual verification is required.

Frontend valid run: run-20260617-143500-d11c97
final status: awaiting_verification
progress: 1/1
screenshots: 3
UI: Awaiting verification panel, Report Preview, Evidence summary, Evaluation 100%
```

当前限制：

- `awaiting_verification` 已有专用人工验证面板；旧 `/verification/confirm` 仍只记录确认，不会恢复原 browser-use task。
- 真实 browser-use run 的 Web 人工验证当前通过 auth-session 保存登录态后创建 retry run，不是同一个 browser-use task 原地续跑。
- 当前仍建议一次只跑一个 browser-use run，避免多个本地浏览器/CDP 会话并发。
- 真实 UAT 账号、Altcha、CAPTCHA、SSO、MFA 等流程可优先使用 Web auth-session；需要更低层调试时仍可回到 CLI 的 human-assisted profile 流程。

## 目录结构

核心结构如下：

```text
apps/web/
  src/
    api/              # 前端 API client、SSE、路径处理
    components/       # 控制台组件
    hooks/            # 控制台状态管理 hook
    mock/             # mock 数据
    pages/            # ConsolePage
    styles/           # 全局样式
    types/            # 前后端契约类型

src/prodwalk/
  events.py           # pipeline 结构化事件模型
  server/
    app.py            # FastAPI app 和 route
    models.py         # API request/response 模型
    runtime.py        # run 状态、后台任务、事件、artifact 管理

docs/
  api_event_contract.md
  frontend_console_mvp_spec.md
  frontend_console_zh.md
  handoffs/
    phase*_*.md       # 各阶段交接文档
```

## 启动命令

### 后端

首次使用时安装 server 依赖：

```powershell
pip install -e ".[server]"
```

如果需要本地 browser-use 能力，安装 browser-use local 依赖：

```powershell
pip install -e ".[browser-use-local]"
```

启动 FastAPI 后端：

```powershell
python -m uvicorn prodwalk.server.app:app --host 127.0.0.1 --port 8000
```

如果 `8000` 端口已有旧进程，可以换一个明确端口，例如：

```powershell
python -m uvicorn prodwalk.server.app:app --host 127.0.0.1 --port 8001
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

成功时会返回类似：

```text
ok=true, service=prodwalk-server
```

### 前端

进入前端目录并安装依赖：

```powershell
cd apps/web
npm install
```

启动开发服务器：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

如果后端使用 `8001`，前端也要指向同一个端口：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8001"
npm run dev -- --host 127.0.0.1 --port 3000
```

打开：

```text
http://127.0.0.1:5173/
```

或你实际指定的前端端口，例如：

```text
http://127.0.0.1:3000/
```

前端构建检查：

```powershell
cd apps/web
npm run build
```

## Web 控制台推荐流程

### Mock run

1. 启动后端，例如 `http://127.0.0.1:8000`。
2. 启动前端，并确认 `VITE_API_BASE_URL` 指向同一个后端端口。
3. 打开前端页面。
4. 在 Plan selector 中选择 `examples/smoke_plan.json`。
5. 选择 `mock` mode。
6. 点击 Start Mock Run。
7. 观察 Current Run Status、Agent Progress 和 Recent Activity。
8. run 完成后查看 Report Preview、Evidence、Evaluation。
9. 在 Run History 中重新打开历史 run。

### browser-use smoke run

1. 确认已安装 `pip install -e ".[browser-use-local]"`。
2. 确认本机有可用 Chrome/Edge。
3. 确认 LLM 配置可用，默认可继承本地 Codex 配置。
4. 启动后端和前端。
5. 选择 `examples/smoke_plan.json`。
6. 切换到 `browser-use` mode。
7. 设置较小的 max steps，例如 `12`。
8. 点击 Start Browser-use Run。
9. 如果进入 `awaiting_verification`，先查看 Report/Evidence/Screenshots 是否已生成；需要登录态时点击“开始人工验证”，完成浏览器验证后点击“我已完成，使用新登录态重新运行”。

## 原有 CLI 仍然可用

现有 CLI 没有被替换，仍然可以使用：

```powershell
$env:PYTHONPATH="src"
python -m prodwalk.cli run --config examples/smoke_plan.json --mode mock --out runs --concurrency 1
```

如果已经安装 editable package，也可以使用：

```powershell
prodwalk run --config examples/smoke_plan.json --mode mock --out runs --concurrency 1
```

browser-use CLI smoke：

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="true"
python -m prodwalk.cli run --config examples/smoke_plan.json --mode browser-use --out runs --concurrency 1 --browser-max-steps 12 --verification-mode off
```

Clink-style UAT 推荐继续使用持久浏览器 profile：

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="true"
python -m prodwalk.cli run --config examples/clink_uat_full_continuous_plan.json --mode browser-use --out runs-clink-full --concurrency 1 --browser-max-steps 55 --browser-timeout-sec 900 --browser-user-data-dir .prodwalk\browser-profiles\clink_uat_account --report-language zh
```

如果 verification 需要人工操作，按 CLI 提示完成浏览器窗口中的登录或验证，然后回到终端按 Enter。

## 主要 API

当前前端已接入或后端已提供的主要接口：

```text
GET  /api/health
GET  /api/plans
GET  /api/plans/{name}
POST /api/runs
GET  /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/events/stream
GET  /api/runs/{run_id}/agents
GET  /api/runs/{run_id}/artifacts
GET  /api/runs/{run_id}/artifacts/{artifact_id}/content
GET  /api/runs/{run_id}/artifacts/{artifact_ref}
GET  /api/runs/{run_id}/screenshots/{filename}
GET  /api/runs/{run_id}/report
GET  /api/runs/{run_id}/evidence
GET  /api/runs/{run_id}/evidence/{evidence_id}
GET  /api/runs/{run_id}/evaluation
POST /api/runs/{run_id}/cancel
POST /api/runs/{run_id}/verification/confirm
POST /api/auth-sessions
GET  /api/auth-sessions/{session_id}
POST /api/auth-sessions/{session_id}/confirm
POST /api/runs/{run_id}/retry-after-verification
```

## 事件机制

后端通过 pipeline 事件把原本 CLI 内部的执行过程暴露给前端。事件会被映射成前端可消费的 run event，例如：

```text
run.created
run.started
stage.started
agent.started
agent.completed
artifact.created
report.generated
evaluation.generated
stage.completed
run.completed
run.failed
```

前端通过 `EventSource` 订阅：

```text
/api/runs/{run_id}/events/stream
```

然后根据事件更新：

- Current Run Status
- Agent Progress
- Recent Activity
- Details tab 中的 Live Event Log
- Report/Evidence/Evaluation 加载状态

## 测试和验收

Phase 6 Final Integration QA 的验收记录：

```text
python -m pytest
50 passed, 1 warning in 10.27s
```

warning 来自 FastAPI/Starlette TestClient 的 `httpx` deprecation。

前端构建：

```text
cd apps/web
npm run build
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
built successfully
```

重新验收建议运行：

```powershell
python -m pytest
cd apps/web
npm run build
```

手动 smoke：

```text
前端启动 mock run -> SSE 事件出现 -> agent 状态完成 -> report/evidence/evaluation 可查看
```

browser-use smoke：

```text
前端提交 browser-use -> 后端创建 run -> report/evidence/evaluation/screenshots 生成 -> 若 awaiting_verification，确认 UI 有专用 panel 且 Details tab 可读
```

## 常见问题

### 前端报 API 错误或只支持 mock mode

通常是前端连到了旧后端。确认 `VITE_API_BASE_URL` 指向当前启动的 FastAPI 端口。Phase 6 验收中曾遇到 `127.0.0.1:8000` 有旧后端进程，导致 browser-use 返回：

```text
BAD_REQUEST: Only mock mode is supported by the first backend API version.
```

解决方式：

- 停掉旧 uvicorn 进程后重启当前后端。
- 或把当前后端启动在 `8001`，并把前端 `VITE_API_BASE_URL` 也设置为 `http://127.0.0.1:8001`。

### SSE 没有事件

先确认：

- 后端 `/api/health` 正常。
- 前端 API base URL 和后端端口一致。
- Details tab 中 SSE 状态不是断开。
- 浏览器控制台没有 CORS 或网络错误。

### report/evidence/evaluation 没有显示

先看 Current Run Status 是否完成，再打开 Details tab 检查 artifact ids。artifact 已生成但预览失败时，通常是 artifact 读取路径或 artifact id 问题；run 本身失败时，优先看 Recent Activity 和 Live Event Log。

### browser-use 一直 awaiting_verification

这代表 browser-use 已启动但认为需要人工验证，或最终状态被保守折算为需要验证。当前可以先检查已生成的 report/evidence/screenshots；如果是真实 UAT 或登录流程，在等待验证面板点击“开始人工验证”，完成可见浏览器里的登录/验证后再点击“我已完成，使用新登录态重新运行”。系统会创建新的 retry run，不会伪装成恢复原 task。

### 启动多个 browser-use run 是否安全

不建议。当前本地 browser-use 仍建议一次一个 run，尤其是可见浏览器、持久 profile 或需要人工验证时。多个本地浏览器/CDP 会话并发可能导致启动超时或状态混淆。

### apps/web/src/components/runs/ 文件不显示在 git status

仓库 `.gitignore` 中的 `runs/` 规则可能影响该路径。后续如果需要新增该目录下文件，要特别检查 ignore 规则或使用明确的 git add 路径。

## 给后续 agent 的接手说明

后续 agent 开始前建议先读：

```text
docs/frontend_console_zh.md
docs/frontend_console_mvp_spec.md
docs/api_event_contract.md
docs/handoffs/phase6_final_handoff.md
```

如果是做后端：

```text
src/prodwalk/server/app.py
src/prodwalk/server/runtime.py
src/prodwalk/server/models.py
src/prodwalk/events.py
```

如果是做前端：

```text
apps/web/src/hooks/useProdwalkConsole.ts
apps/web/src/api/
apps/web/src/types/contracts.ts
apps/web/src/pages/ConsolePage.tsx
apps/web/src/components/
```

如果是做真实走查：

```text
README.md
examples/smoke_plan.json
examples/clink_uat_full_continuous_plan.json
src/prodwalk/agents/walker.py
src/prodwalk/auth_session.py
```

## Phase 7：Web 人工验证接管闭环

Phase 7 后，Web 控制台可以把 `awaiting_verification` 的 browser-use run 接到一个可见浏览器人工验证流程：

1. browser-use run 遇到登录、Altcha、CAPTCHA、MFA、SSO 等阻塞后，后端将原 run 标记为 `awaiting_verification`。
2. 前端 Current Run Status 会显示“需要你手动完成登录/验证”面板，并明确说明当前版本会创建 retry run，而不是恢复原 browser-use task。
3. 点击“开始人工验证”后，后端创建 `auth-session`，打开一个可见 Chrome/Edge 浏览器窗口。
4. 用户在浏览器中手动完成登录或验证。
5. 回到 Web 控制台点击“我已完成，使用新登录态重新运行”。
6. 后端保存 profile/storage state，关闭可见浏览器，并用同一个 plan 创建新的 browser-use retry run。
7. 原 run 的 metadata 会记录 `verification_session_id` 和 `retry_run_id`；retry run 的 metadata 会记录 `parent_run_id`、`retry_of_run_id` 和 `verification_session_id`。
8. History 面板会显示原 run、auth-session 和 retry run 的关系，retry run 完成后仍可打开 report、evidence、evaluation、screenshots。

新增 API：

```text
POST /api/auth-sessions
GET  /api/auth-sessions/{session_id}
POST /api/auth-sessions/{session_id}/confirm
POST /api/runs/{run_id}/retry-after-verification
```

旧接口 `POST /api/runs/{run_id}/verification/confirm` 现在只记录确认，不会暗示原 browser-use task 会继续。如果 run 已经没有 active browser task，它会返回明确说明：需要通过 auth-session 后创建 retry run。

安全注意：

- 不要把账号、密码、token、API key 写入 plan、代码、日志或报告。
- profile/storage state 路径会被限制在当前 workspace 下；未传路径时默认写入 `.prodwalk/browser-profiles/<ref-or-host>/`。
- `.prodwalk/` 和 `runs/` 是本地产物，不应提交。
- 截图和浏览器历史可能包含邮箱、租户名或页面内敏感信息；Phase 7 会隐藏本地 profile/storage path 和常见 secret/token 文本，但登录页截图仍需要人工判断后再分享。
