# Phase 3.1 Frontend Scaffold Handoff

## 本阶段范围

本阶段创建了 `apps/web` 前端控制台工程骨架，技术栈为 React + Vite + TypeScript。页面默认展示内部控制台工作台，不包含 landing page 或 hero section。

本阶段未修改：

- `src/prodwalk/`
- `tests/`
- `pyproject.toml`
- `docs/api_event_contract.md`

## 创建的文件

前端工程配置：

- `apps/web/package.json`
- `apps/web/package-lock.json`
- `apps/web/.gitignore`
- `apps/web/index.html`
- `apps/web/vite.config.ts`
- `apps/web/tsconfig.json`
- `apps/web/tsconfig.node.json`

前端入口：

- `apps/web/src/main.tsx`
- `apps/web/src/App.tsx`
- `apps/web/src/vite-env.d.ts`

API 与类型：

- `apps/web/src/api/client.ts`
- `apps/web/src/api/sse.ts`
- `apps/web/src/api/mockConsoleData.ts`
- `apps/web/src/types/contracts.ts`

mock 数据：

- `apps/web/src/mock/plans.ts`
- `apps/web/src/mock/runs.ts`
- `apps/web/src/mock/agents.ts`
- `apps/web/src/mock/events.ts`
- `apps/web/src/mock/evidence.ts`
- `apps/web/src/mock/report.ts`

布局、页面和组件：

- `apps/web/src/pages/ConsolePage.tsx`
- `apps/web/src/components/StatusBadge.tsx`
- `apps/web/src/components/layout/AppShell.tsx`
- `apps/web/src/components/layout/TopRunContextBar.tsx`
- `apps/web/src/components/runs/RunLauncher.tsx`
- `apps/web/src/components/runs/RecentRunsList.tsx`
- `apps/web/src/components/agents/AgentStatusBoard.tsx`
- `apps/web/src/components/events/EventLog.tsx`
- `apps/web/src/components/reports/ReportPreview.tsx`
- `apps/web/src/components/evidence/EvidenceSnapshot.tsx`
- `apps/web/src/styles/globals.css`

## 如何安装依赖

```bash
cd apps/web
npm install
```

当前安装后 `npm audit --audit-level=moderate` 结果为 `found 0 vulnerabilities`。

## 如何启动前端

```bash
cd apps/web
npm run dev
```

默认 Vite dev server 端口为 `5173`。`vite.config.ts` 已配置 `/api` proxy 到 `http://127.0.0.1:8765`，便于后续连接 Phase 2 FastAPI 服务。

## 如何 build

```bash
cd apps/web
npm run build
```

本阶段已验证通过。

## 当前 mock 数据说明

所有 mock 数据都放在 `apps/web/src/mock/`：

- `plans.ts`：模拟 `GET /api/plans` 的本地 plan 列表。
- `runs.ts`：模拟 active run 与 recent run history，覆盖 running、done、blocked、failed 历史状态。
- `agents.ts`：模拟 director、planner、walker、report writer、evaluator 等 agent execution。
- `events.ts`：模拟 dot-style API/SSE 事件，例如 `run.created`、`agent.started`、`artifact.created`、`evaluation.generated`。
- `evidence.ts`：模拟 evidence list，并故意保留 screenshot missing 状态。
- `report.ts`：模拟 report markdown 与 evaluation summary。

UI 层单独定义了 `idle`、`running`、`done`、`blocked`、`failed` 控制台状态，并通过 `toConsoleStatus` 映射 API run status。默认页面使用 mock 数据，不依赖后端即可展示。

## 给 UI Component Agent 的下一步建议

- 将当前基础组件继续拆成更细的复用组件，例如 plan selector、run action bar、agent card、event row、evaluation score card。
- 补充更完整的 empty、loading、error、partial artifact 状态，尤其是 report not ready、evidence available but screenshot missing、evaluation unavailable。
- 增强 Report Preview 的 markdown 渲染。当前只是轻量预览，不是完整 markdown renderer。
- 优化小屏布局和长文本边界，确保 event payload、run id、artifact id 在窄屏不会压坏布局。
- 可以增加页面级导航或 route skeleton，但默认入口仍应是控制台工作台。

## 给 Frontend Integration Agent 的注意事项

- API 类型集中在 `apps/web/src/types/contracts.ts`，需要继续和 `docs/api_event_contract.md` 以及 `docs/frontend_console_mvp_spec.md` 对齐。
- API client 已预留在 `apps/web/src/api/client.ts`，SSE wrapper 已预留在 `apps/web/src/api/sse.ts`。
- 实时事件必须接 `/api/runs/{run_id}/events/stream`，不要使用废弃的 `/stream` 路径。
- Screenshot 不要拼接本地路径读取，必须走 artifact content endpoint。
- 后续接真实 API 时，可以先保留 mock fallback，以便无后端环境仍能开发 UI。
- Browser-use 和 manual verification UI 目前只是入口占位，不能假设后端已经支持完整恢复流程。
