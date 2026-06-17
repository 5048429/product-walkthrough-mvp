# Browser-use Real Smoke Handoff

日期：2026-06-17

## 结论

本次通过 Web 控制台完成公开页面 browser-use 真实 smoke 闭环验收。

- 最终 run：`run-20260617-171441-8c318b`
- 最终状态：`succeeded`
- 计划：`examples/smoke_plan.json`
- 页面：`https://www.wikipedia.org`
- 模式：`browser-use`
- verification：`verification_mode=off`
- 进度：`1/1`
- 错误：无

最终状态已经是 `succeeded`，因此不需要归因到依赖、LLM、浏览器、网络、状态判定或人工验证误判。

## 已执行检查

### 后端/仓库测试

```powershell
python -m pytest
```

结果：

```text
52 passed, 1 warning in 14.84s
```

warning 来自 FastAPI/Starlette TestClient 的 `httpx` deprecation，不影响本次 smoke。

### 前端构建

```powershell
cd apps/web
npm run build
```

结果：

```text
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
✓ built in 441ms
```

## 服务启动

为避免连接到已有旧服务，本次启动了一组独立服务：

- FastAPI：`http://127.0.0.1:8002`
- Web Console：`http://127.0.0.1:3000`
- 日志目录：`C:\Users\Administrator\AppData\Local\Temp\prodwalk-real-smoke-20260617-170743`

`8000/5173` 已有本仓库进程，但提交 browser-use 时返回旧 API 错误：

```text
BAD_REQUEST: Only mock mode is supported by the first backend API version.
```

`5175 -> 8002` 曾用于排查，但被当前 CORS 白名单拒绝；后端当前只允许 `5173`、`5174`、`3000` 等来源。最终使用 `3000 -> 8002` 完成验收。

已关闭排查用的 `5175` 前端进程；`8002` 后端和 `3000` 前端仍保留运行，便于复查。

## Web 控制台路径

在 Web 控制台执行：

1. 选择 `examples/smoke_plan.json`。
2. 选择 `真实浏览器`。
3. 人工验证保持默认 `关闭（公开页面推荐）`，UI 明确提示将以 `verification_mode=off` 提交。
4. 点击 `启动真实页面测试`。

新 run 成功创建：

```text
run-20260617-171441-8c318b
```

启动后 API 参数确认：

```json
{
  "mode": "browser-use",
  "concurrency": 1,
  "browser_max_steps": 25,
  "browser_timeout_sec": 600.0,
  "verification_mode": "off"
}
```

## SSE 验证

SSE endpoint：

```text
GET /api/runs/run-20260617-171441-8c318b/events/stream
```

stream 抽样返回了事件：

```text
id: 1
event: run.event
data: ... "type": "run.created" ...

id: 2
event: run.event
data: ... "type": "run.started" ...

id: 7
event: run.event
data: ... "type": "agent.started", "message": "BrowserWalker started" ...
```

最终事件列表：

- event count：`30`
- last seq：`30`
- terminal event：`run.completed`
- terminal status：`succeeded`

## Artifact 验证

最终 run API：

```text
status=succeeded
report_exists=true
evidence_exists=true
evaluation_exists=true
screenshot_count=4
```

artifact 类型：

```text
run_manifest
plan_json
events_jsonl
agents_json
artifacts_json
evidence_json
report_markdown
evaluation_json
screenshot x4
browser_history
```

产物文件位于：

```text
runs/run-20260617-171441-8c318b/
```

关键文件：

- `report.md`
- `evidence.json`
- `evaluation.json`
- `screenshots/*.png`
- `browser-history/*.json`

4 个 screenshot artifact 均可通过 API 读取，HTTP `200`，Content-Type 为 `image/png`。

## Evidence / Evaluation 摘要

`evidence.json`：

- results：`1`
- evidence：`6`
- 主证据：`ev-wikipedia-smoke-public_entry_smoke-browser-use-local`
- 主证据 status：`completed`
- browser history artifact：`art_browser_history_browser_use_history_open_https_www_wikipedia_org_and_perform_a_product_walkthr_c0432047fb_03553664`
- final output：`manual_verification_required=false`
- URLs seen：
  - `https://www.wikipedia.org`
  - `https://www.wikipedia.org/`
  - `https://zh.wikipedia.org/wiki/Special:Search?search=product+management&go=Go`
  - `https://zh.wikipedia.org/wiki/%E7%94%A2%E5%93%81%E7%AE%A1%E7%90%86?wprov=srpw1_0`

`evaluation.json`：

```json
{
  "task_completion_rate": 1.0,
  "evidence_coverage_rate": 1.0,
  "finding_grounding_rate": 1.0,
  "recommendation_actionability_rate": 1.0,
  "evidence_items": 6,
  "findings": 2,
  "overall_score": 1.0
}
```

`report.md` 生成成功，约 8 KB，包含 Wikipedia Smoke 的 scenario coverage、findings、evidence appendix 和 screenshot links。

## UI 最终状态

Web 控制台最终显示：

- 状态：`已完成`
- 模式：`真实浏览器走查`
- 进度：`1/1`
- Run：`run-20260617-171441-8c318b`
- Results：
  - Report：Ready to review
  - Evidence：6 items
  - Evaluation：100%

观察到两个不阻断本次验收的 UI 残余现象：

1. Report Preview 曾显示 `Report refresh issue / NETWORK_ERROR: Failed to fetch`，但同一页面仍展示了完整报告内容，且 `/report` API 多次返回 `200`。
2. UI 的 Screenshots 文案显示 `5 archived screenshots`，而后端 artifact 列表中实际 screenshot artifact 为 `4`。看起来 UI 使用 evidence-with-screenshot 口径，后端使用实际图片 artifact 口径。

## 范围确认

- 只跑了公开 Wikipedia smoke。
- 未运行 Clink UAT。
- 未改 credentials。
- 未执行任何真实产品写操作。
- 未提交 destructive 操作。
