# Phase 4 Final Integration QA Handoff

## Scope

本次验收完成前后端真实联调，覆盖 FastAPI 后端、`apps/web` 前端、真实 API、SSE、artifact 读取、测试、build、旧 CLI mock run。

本次小范围修复：

- `src/prodwalk/server/app.py`: CORS allowlist 增加 `http://localhost:5174` 和 `http://127.0.0.1:5174`，用于并行启动带显式 API env 的 Vite 验收实例。
- `apps/web/src/hooks/useProdwalkConsole.ts`: 终端事件到达后主动关闭 EventSource，并避免 API 初始化流程在 run 完成后把连接状态覆盖回 `connecting`。
- `apps/web/src/components/layout/TopRunContextBar.tsx`: 修正 Stop 按钮 title，避免误称后端 cancel route 未实现。

## Backend Start Command

依赖未安装时：

```powershell
pip install -e ".[server]"
```

本次验收使用：

```powershell
python -m uvicorn prodwalk.server.app:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

结果：

```text
ok=true, service=prodwalk-server, version=0.4.5
```

## Frontend Start Command

本次验收使用独立 Vite 端口 `5174`，并显式指定 API base，避免浏览器环境把 `localhost` 解析到不可达地址：

```powershell
cd apps/web
cmd /c "set VITE_API_BASE_URL=http://127.0.0.1:8000&& npm run dev -- --host 127.0.0.1 --port 5174"
```

打开：

```text
http://127.0.0.1:5174/
```

也可使用 5173：

```powershell
cd apps/web
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

## Full Integration Steps

1. 启动 FastAPI 后端到 `http://127.0.0.1:8000`。
2. 启动 `apps/web` 到 `http://127.0.0.1:5174/`，设置 `VITE_API_BASE_URL=http://127.0.0.1:8000`。
3. 打开前端，确认 Run Start 显示 `API connected`，不是 `Mock fallback`。
4. 在 Plan 下拉中选择 `examples/smoke_plan.json`。
5. 点击 `Start Mock Run`。
6. 观察 Active Run 从 running 进入 done。
7. 观察 Live Event Log 从 `0 of 0 events shown. SSE connecting.` 更新到 `29 of 29 events shown. SSE closed.`。
8. 观察 Agent Status 从 running/idle 过渡到 `All required agent stages completed or were skipped. done`。
9. 观察 Report Preview 显示 `art_report_md / en` 和 `# Product Walkthrough Research Report`。
10. 观察 Evidence 显示 `art_evidence_json / 5 items`，mock run 的截图区域以 `Missing screenshot` 显示。
11. 观察 Report Preview 右侧 Evaluation 显示基础分数，包括 task completion、evidence coverage、finding grounding、recommendation actionability 和 overall score。
12. 直接调用 API 确认 report/evidence/evaluation/events/artifacts 均可读取。
13. 运行 `python -m pytest`。
14. 运行 `npm run build`。
15. 运行旧 CLI mock run 的 `python -m prodwalk.cli` 和 `prodwalk` 两种入口。

## UI Acceptance Record

未保存截图到仓库；以下是 Browser DOM 观察记录。

最终 UI 验收 run：

```text
run_id: run-20260616-211717-4c6cc0
mode: mock
status: done
source: closed
run_dir: runs/run-20260616-211717-4c6cc0
```

观察结果：

```text
Run Start: Run completed. Report, evidence, and evaluation artifacts are available.
Live Event Log: 29 of 29 events shown. SSE closed.
Event types include: run.created, run.started, stage.started, agent.started, agent.completed, run.finalizing, artifact.created, report.generated, evaluation.generated, stage.completed, run.completed.
Agent Status: All required agent stages completed or were skipped. done.
Report Preview: art_report_md / en, Markdown starts with # Product Walkthrough Research Report.
Evidence: art_evidence_json / 5 items.
Evaluation: task completion rate 100%, evidence coverage rate 100%, finding grounding rate 100%, recommendation actionability rate 100%, overall score 100%.
```

Direct API check for the same run:

```text
run_status: succeeded
event_count: 29
first_event: run.created
last_event: run.completed
agent_count: 9
agent_statuses: succeeded
artifact_ids: art_run_manifest, art_plan_json, art_events_jsonl, art_agents_json, art_artifacts_json, art_evidence_json, art_report_md, art_evaluation_json
report_has_markdown: true
evidence_items: 5
evaluation_overall_score: 1.0
evaluation_notes: MVP run meets the configured basic evaluation thresholds.
```

SSE direct check:

```text
GET /api/runs/run-20260616-211717-4c6cc0/events/stream?after_seq=0
status: 200
content-type: text/event-stream; charset=utf-8
first frame: id: 1, event: run.event, data.type: run.created
```

## Pytest Result

Command:

```powershell
python -m pytest
```

Result:

```text
42 passed, 1 warning in 6.48s
```

Warning:

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.
```

## Frontend Build Result

Command:

```powershell
cd apps/web
npm run build
```

Result:

```text
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
51 modules transformed
dist/index.html
dist/assets/index-D0U1z88j.css
dist/assets/index-CXER23rN.js
built successfully
```

## Legacy CLI Verification

Command:

```powershell
python -m prodwalk.cli run --config examples/smoke_plan.json --mode mock --out $env:TEMP\prodwalk_phase4_final_cli_smoke_py --concurrency 1
```

Result:

```text
MVP walkthrough run completed
Generated evidence.json, report.md, evaluation.json
```

Command:

```powershell
prodwalk run --config examples/smoke_plan.json --mode mock --out $env:TEMP\prodwalk_phase4_final_cli_smoke_entry --concurrency 1
```

Result:

```text
MVP walkthrough run completed
Generated evidence.json, report.md, evaluation.json
```

## Current Supported Mode

Web API / UI:

- `mock`: supported end to end.
- `browser-use`: UI entry is present but gated; backend `POST /api/runs` currently rejects non-mock mode.

Legacy CLI:

- `mock`: verified.
- `browser-use` and `browser-use-local`: CLI options still exist, but were not part of this Phase 4 mock E2E acceptance run.

## Currently Connected APIs

Frontend is wired and verified for:

- `GET /api/health`
- `GET /api/plans`
- `GET /api/plans/{plan_id}`
- `POST /api/runs` with `mode=mock`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/events/stream`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}/content` via artifact/report/evaluation links
- `GET /api/runs/{run_id}/report`
- `GET /api/runs/{run_id}/evidence`
- `GET /api/runs/{run_id}/evaluation`

Backend also implements:

- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/verification/confirm`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`
- `GET /api/runs/{run_id}/evidence/{evidence_id}`

## Currently Not Connected In UI

- Stop button does not call `POST /api/runs/{run_id}/cancel` yet.
- Manual verification UI does not call `POST /api/runs/{run_id}/verification/confirm` yet.
- Evidence detail/deep-link UI does not call `GET /api/runs/{run_id}/evidence/{evidence_id}` yet.
- Browser-use run launch is gated because backend run creation currently supports only `mode=mock`.
- The current app remains a single console workbench rather than separate route-level pages.

## Known Issues

- Set `VITE_API_BASE_URL=http://127.0.0.1:8000` during local frontend testing. The default `http://localhost:8000` can fail in some browser environments when the backend is bound only to IPv4 `127.0.0.1`.
- Mock mode does not generate real screenshots; Evidence correctly shows `Missing screenshot`.
- Mock event telemetry is still lifecycle/agent/artifact oriented. It does not emit the full scenario/evidence/finding event set from the final contract.
- Historical CLI runs can still appear with inferred `mode: unknown`.
- Browser-use API path is not implemented for Web run creation.

## Phase 5 Suggested Tasks

- Wire Stop to `POST /api/runs/{run_id}/cancel` with disabled/loading/error states.
- Wire manual verification confirmation to `POST /api/runs/{run_id}/verification/confirm`.
- Add evidence detail/deep-link UI using `GET /api/runs/{run_id}/evidence/{evidence_id}`.
- Implement browser-use Web run creation and visible/manual verification flow.
- Add route-level pages for runs, agents, events, evidence, report, and history if the console grows beyond the current workbench.
- Add automated browser E2E tests for the Web mock run path, including SSE event replay and terminal artifact loading.
- Decide whether the default frontend API base should be `127.0.0.1` or proxy-relative `/api` for local development.
- Expand telemetry to include optional `scenario.*`, `evidence.created`, `finding.created`, and screenshot artifact events when browser-use is connected.
