# Prodwalk 前端控制台中文说明

本文档说明当前 `prodwalk` 前端控制台的阶段性成果、启动方式、使用流程、系统架构和后续建议。当前版本已经完成 Phase 1 到 Phase 5 的核心闭环：可以通过本地 Web 页面启动 mock 产品走查、实时查看 agent 事件、查看报告、证据、评估结果和历史 run。

## 当前结论

Phase 6 不需要立刻开始。Phase 6 更适合作为正式发布前的稳定化、真实 browser-use 验证和桌面化评估阶段。

当前更优先的事情是：

1. 保存已有工作到远程仓库。
2. 固化一份中文说明文档，方便后续 agent 或团队成员接手。
3. 在需要真实 UAT 走查时，再进入 Phase 6 或单独做 browser-use 联调。

## 当前能力

当前 Web 控制台已经具备以下能力：

- 本地 FastAPI 后端服务。
- React + Vite + TypeScript 前端控制台。
- 从前端读取 `examples/` 下的 research plan。
- 从前端启动 `mock` mode run。
- 通过 SSE 实时展示 run 事件。
- 展示各 agent 的运行状态。
- run 完成后展示 `report.md`。
- 展示 `evidence.json` 中的证据列表。
- 展示 `evaluation.json` 中的评分结果。
- 展示历史 run。
- 支持 artifact 和 screenshot 安全读取接口。
- 保持原有 CLI 入口兼容。

## 目录结构

核心新增结构如下：

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

## 后端启动

首次使用时建议安装 server 依赖：

```powershell
pip install -e ".[server]"
```

启动 FastAPI 后端：

```powershell
python -m uvicorn prodwalk.server.app:app --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

成功时会返回类似：

```text
ok=true, service=prodwalk-server
```

## 前端启动

进入前端目录：

```powershell
cd apps/web
npm install
```

启动开发服务器：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173/
```

构建检查：

```powershell
npm run build
```

## 使用流程

推荐第一条验证路径：

1. 启动后端 `http://127.0.0.1:8000`。
2. 启动前端 `http://127.0.0.1:5173/`。
3. 在前端选择 `examples/smoke_plan.json`。
4. 选择 `mock` mode。
5. 点击启动 run。
6. 观察 Live Event Log 中的实时事件。
7. 观察 Agent Status 中各 agent 状态变化。
8. run 完成后查看 Report、Evidence、Evaluation。
9. 在 Run History 中打开历史 run。

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
```

其中 Phase 5 已验证的主路径是：

- `mock` run 创建。
- SSE 实时事件。
- report/evidence/evaluation 读取。
- artifact 安全读取。
- history run 打开。

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

- Live Event Log
- Agent Status
- Active Run 状态
- Report/Evidence/Evaluation 加载状态

## 当前限制

当前版本仍有这些限制：

- Web 控制台主路径只完整验证了 `mock` mode。
- `browser-use` run 在 Web 控制台中仍属于后续增强项。
- 人工登录 checkpoint 和验证码/Altcha 流程还没有在 Web UI 中完整闭环。
- 当前没有引入数据库，run 状态主要由内存状态和 `runs/` 目录扫描组成。
- 当前没有多用户、权限、云端部署。
- 截图展示能力已有后端接口和前端状态，但当前 workspace 中没有真实截图样例可做完整 UI 验证。
- CORS 当前主要面向本地开发端口，例如 `5173`、`5174`、`3000`。

## 测试和验收

Phase 5 结束时的验收记录显示：

```text
python -m pytest
46 passed, 1 warning
```

前端构建：

```text
cd apps/web
npm run build
built successfully
```

旧 CLI mock run 也已验证可用。

如果后续重新验收，建议运行：

```powershell
python -m pytest
cd apps/web
npm run build
```

再手动验证：

```text
前端启动 mock run -> SSE 事件出现 -> agent 状态完成 -> report/evidence/evaluation 可查看
```

## 后续建议

建议后续不要立刻继续堆功能，而是按优先级选择：

### 选项 A：先封存 v0.1

适合当前要保存成果、同步远程仓库、让团队或后续 agent 接手。

要做的事：

- 提交代码。
- 推送远程仓库。
- 保留本文档作为中文入口说明。

### 选项 B：进入 Phase 6

适合准备把它作为稳定工具使用。

Phase 6 应聚焦：

- 稳定性审计。
- browser-use smoke 验证。
- 文档完善。
- 是否封装 Tauri 桌面应用的决策。

### 选项 C：直接做 browser-use Web 联调

适合你已经要用它跑真实 Clink UAT 走查。

要重点处理：

- Web UI 启动 browser-use 参数。
- 人工验证 checkpoint。
- 浏览器 profile 选择。
- 真实截图和 browser history artifact 展示。
- read-only 安全约束。

## 给后续 agent 的接手说明

后续 agent 开始前建议先读：

```text
docs/frontend_console_zh.md
docs/frontend_console_mvp_spec.md
docs/api_event_contract.md
docs/handoffs/phase5_final_handoff.md
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

