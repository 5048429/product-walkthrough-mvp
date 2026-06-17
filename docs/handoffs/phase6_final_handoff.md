# Phase 6 Final Integration QA Handoff

## 验收结论

Phase 6 UI 简化、mock run 闭环、旧 CLI 入口、前端 browser-use 提交、后端 browser-use 真实 smoke run 均已验收。

本轮只做了小范围前端修复：
- `apps/web/src/hooks/useProdwalkConsole.ts`：默认 Current Run Status 不再把 API/artifact 读取错误误显示为 run issue。
- `apps/web/src/pages/ConsolePage.tsx`：Report/Evidence 预览只显示各自 artifact 读取错误，不再把 run-level blocker 误显示为 report/evidence refresh issue。

未修改核心 pipeline 大逻辑、报告生成格式、桌面壳或数据库。

## 验收环境

- 当前源码后端：`http://127.0.0.1:8001`
- 当前源码前端：`http://127.0.0.1:3000`
- 说明：开始时 `127.0.0.1:8000` 已有旧后端进程，browser-use 返回 `BAD_REQUEST: Only mock mode is supported by the first backend API version.`。最终验收未使用该旧进程结果。
- 安全范围：真实 browser-use 只跑 `examples/smoke_plan.json` 的公开 Wikipedia smoke，不做真实产品破坏性操作。

## UI 简化验收结果

通过。

默认 Dashboard 保留并验证了核心 PM 工作台能力：
- plan selector 和 plan summary。
- mock / browser-use mode selector。
- Start Mock Run / Start Browser-use Run / Stop / Open Report。
- 当前 run 状态、进度、elapsed、run id。
- 简化 Agent Progress 和 Recent Activity。
- Results shortcut、Report Preview。
- 折叠的 Evidence / Screenshots 和 Run History。

Debug 默认隐藏：
- 默认 Dashboard 未显示 `Live Event Log`。
- 默认 Dashboard 未直接展示 API source、SSE、run dir、artifact ids、raw event payload。
- Details tab 可显示 `API / Debug`、`Agent Status`、`Live Event Log`。

## Mock Run 验收结果

通过。

前端 mock run：
- 服务：前端 `127.0.0.1:3000` -> 后端 `127.0.0.1:8001`
- plan：`examples/smoke_plan.json`
- run：`run-20260617-142033-0198bc`
- status：`succeeded`
- progress：`1/1`
- artifacts：`report.md`、`evidence.json`、`evaluation.json` 均可读
- UI：Report Preview 显示 Wikipedia smoke 报告；Evidence 显示 5 items；Evaluation 显示 100%

## Browser-Use 支持状态

后端真实 browser-use 可运行；前端可提交 browser-use 请求。

真实 smoke run 结果：
- API valid run：`run-20260617-142228-c53abd`
  - final status：`awaiting_verification`
  - progress：`1/1`
  - report/evidence/evaluation：均生成
  - screenshots：6
  - browser history artifact：已注册
  - run error：`Browser-use reported that manual verification is required.`
- 前端 valid run：`run-20260617-143500-d11c97`
  - final status：`awaiting_verification`
  - progress：`1/1`
  - report/evidence/evaluation：均生成
  - screenshots：3
  - UI：显示 Awaiting verification panel、Report Preview、Evidence summary、Evaluation 100%

前端 browser-use 提交验证：
- 切换到 `browser-use` mode 后，UI 显示 max steps、timeout、verification mode、headless/visible server env note。
- Advanced browser-use parameters 默认折叠。
- 用 `browser_max_steps=0` 做无副作用校验请求时，当前后端返回：
  - `BAD_REQUEST: browser_max_steps must be between 1 and 200.: {"browser_max_steps":0}`
- 说明前端请求已打到 Phase 6 backend，而不是旧 mock-only backend。

当前未被依赖或 key 阻塞；真实 browser-use 已实际访问公开 smoke plan 并产出截图与 browser history。阻塞点是最终状态折算为 `awaiting_verification`，不是无法启动。

## Pytest 结果

命令：

```powershell
python -m pytest
```

结果：

```text
50 passed, 1 warning in 10.27s
```

warning 来自 FastAPI/Starlette TestClient 的 `httpx` deprecation。

## Npm Build 结果

命令：

```powershell
cd apps/web
npm run build
```

最终结果：

```text
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
55 modules transformed
built successfully
```

## 旧 CLI 验证结果

命令：

```powershell
$env:PYTHONPATH="src"
python -m prodwalk.cli run --config examples/smoke_plan.json --mode mock --out runs --concurrency 1
```

结果：

```text
MVP walkthrough run completed
Run dir: runs\run-20260617-140529
Evidence: runs\run-20260617-140529\evidence.json
Report: runs\run-20260617-140529\report.md
Evaluation: runs\run-20260617-140529\evaluation.json
```

`report.md` 可读，`evidence.json` 和 `evaluation.json` 可解析。

## 已知问题

- `awaiting_verification` 在顶部/StatusBadge 中显示为 `Blocked`，但页面内有 Awaiting verification 专用 panel；建议后续让 badge 和状态 copy 保留更精确的 `awaiting_verification`。
- 刷新后 selected plan 会回到列表第一项，而 active run 仍可能是 smoke run；顶部 Plan 可能短暂显示与 active run 不一致。
- browser-use smoke run 对公开 Wikipedia 仍被折算为 `awaiting_verification`，需要继续调优 final status 判断或 browser-use prompt/marker 解析。
- 当前允许连续启动多个 browser-use run；建议强化 single-active guard，至少对 `running` 和 `awaiting_verification` 状态都生效。
- 真实 browser-use run 的 Web confirm 仍只是记录/状态处理，完整可恢复的 visible-browser continuation 还需要后续打通。
- `apps/web/src/components/runs/` 仍受 `.gitignore` 中 `runs/` 规则影响，普通 `git status` 可能不显示该目录文件。
- 旧 8000 后端进程可能造成误验收；建议验收前固定清理旧 uvicorn/Vite 进程或使用明确端口。

## 下一阶段建议

1. 补一个 browser-use readiness API / panel：依赖、Playwright、浏览器、LLM key、server headless 配置。
2. 修正 `awaiting_verification` 的 UI 状态展示和 confirm continuation 闭环。
3. 强化 browser-use single-active guard，避免多个本地浏览器 run 并发。
4. 给前端启动服务加 `.env.local.example` 或脚本，减少 API base URL 指错到旧后端的风险。
5. 增加一条前端 E2E smoke：mock run 成功、debug 默认隐藏、browser-use 参数校验错误可读。
