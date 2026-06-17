# Phase 1 Architecture Handoff

## 本 Agent 产出的文件

- `docs/frontend_console_technical_spec.md`
  - Web 控制台总体技术规格。
  - 覆盖前端目录、后端目录、数据流、实时事件、run 生命周期、artifact 管理、CLI 兼容策略、风险与后续阶段建议。

- `docs/api_event_contract.md`
  - 前后端 API 与事件契约。
  - 覆盖 `RunEvent` JSON schema、`RunStatus`、`AgentStatus`、artifact 类型、API 示例、SSE 示例、错误响应和 mock mode 约束。

- `docs/handoffs/phase1_architecture_handoff.md`
  - 给后续后端、pipeline instrumentation、前端 Agent 的交接说明。

本阶段未创建 `apps/web`，未创建 `src/prodwalk/server`，未修改 `src/prodwalk` 下任何文件。

## 关键技术决策

- 第一版控制台定位为本地单机 Web 控制台，不做多人协作 SaaS。
- 前端规划为 React + Vite + TypeScript，目录为 `apps/web`。
- 后端规划为 FastAPI，目录为 `src/prodwalk/server`。
- 保留现有 CLI，不让 CLI 依赖 Web server。
- Web 后端复用当前 `ResearchDirector` 和 walker，不重写 pipeline。
- 第一版使用文件存储，继续以 run directory 和 artifact 文件为事实来源。
- 新增 Web 元数据文件建议为 `run.json`、`agents.json`、`events.jsonl`、`artifacts.json`。
- 实时事件流采用 SSE，不采用 WebSocket。
- artifact 访问必须通过后端 registry 和 path 校验，前端不直接读取本地路径。
- mock mode 是第一版端到端验收路径。
- browser-use 第一版只做参数入口和状态展示，细粒度 step telemetry 可后置。

## 后端 Agent 下一步应该读哪些章节

优先阅读：

- `docs/frontend_console_technical_spec.md`
  - `推荐目录结构`
  - `后端 FastAPI 模块设计`
  - `数据流`
  - `run 生命周期`
  - `artifact 管理方式`
  - `CLI 兼容策略`

- `docs/api_event_contract.md`
  - `基础对象`
  - `API 列表`
  - `API 示例`
  - `错误响应格式`
  - `mock mode 第一版约束`

后端 Agent 的建议起步顺序：

1. 创建 `src/prodwalk/server` 骨架。
2. 实现 Pydantic schemas。
3. 实现只读 history run 扫描。
4. 实现 mock mode `POST /api/runs`。
5. 实现 `events.jsonl` 和 SSE。
6. 实现 artifact registry 和 report/evidence/evaluation 读取。

## Pipeline Instrumentation Agent 下一步应该读哪些章节

优先阅读：

- `docs/frontend_console_technical_spec.md`
  - `当前项目结构理解`
  - `实时事件流`
  - `run 生命周期`
  - `风险与取舍`
  - `Phase 2/3/4 的开发建议`

- `docs/api_event_contract.md`
  - `RunEvent JSON Schema`
  - `RunStatus 枚举`
  - `AgentStatus 枚举`
  - `SSE 事件格式示例`
  - `mock mode 第一版约束`

Pipeline Instrumentation Agent 的建议重点：

1. 先不要大改 `ResearchDirector`，优先通过 wrapper 发 stage 级事件。
2. 后续再为 planner、walker、evidence、analyst、reviewer、report、evaluator 加 callback。
3. browser-use step 级事件初期可从 `WalkthroughResult.steps` 和 history 文件回放生成。
4. 将 browser history 归档进 run directory，避免根目录散落 `browser_use_history_*.json`。
5. 强化 screenshot artifact 注册，避免前端遇到临时绝对路径。

## Frontend Agent 下一步应该读哪些章节

优先阅读：

- `docs/frontend_console_technical_spec.md`
  - `前端 React 模块设计`
  - `数据流`
  - `实时事件流`
  - `run 生命周期`
  - `artifact 管理方式`

- `docs/api_event_contract.md`
  - `基础对象`
  - `API 列表`
  - `API 示例`
  - `SSE 事件格式示例`
  - `错误响应格式`

Frontend Agent 的建议起步顺序：

1. 创建 `apps/web` Vite + React + TypeScript 项目。
2. 建立 `api/contracts.ts`，手动同步本文档中的类型。
3. 实现 Run List 和 Run Launcher。
4. 实现 Run Detail 页面骨架。
5. 接入 SSE event stream。
6. 实现 Agent Status、Event Stream、Report Viewer。
7. 最后实现 Evidence Explorer 和 Artifact Preview。

## 未解决问题

- 是否允许同时运行多个 browser-use run。建议第一版限制为一个 active browser-use run。
- Web verification confirm 如何与当前 terminal `input()` 流程协调。建议第一版先复用现有手动确认，后续再改造成 Web 驱动确认。
- browser-use history 文件是否必须迁移到 run directory。建议后续实现时迁移。
- 旧 run 中引用临时绝对截图路径时是否尝试自动复制。出于安全考虑，建议第一版不读取任意 run directory 外路径。
- 是否需要 SQLite。建议第一版不需要，除非 run 数量和筛选能力超过文件扫描可承受范围。
- report Markdown 中的本地截图链接如何稳定重写。建议由 `ArtifactService` 统一转换。
- 前端 UI 组件库尚未决定。建议先使用轻量 CSS 或项目选定的 UI 基础库，避免因视觉系统选择阻塞 MVP。
