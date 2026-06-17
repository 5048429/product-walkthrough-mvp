# Browser-use Frontend Handoff

日期：2026-06-17

## 本次范围

只修改 Web 控制台前端，未修改 `src/prodwalk/server/` 和 Python pipeline。

涉及文件：
- `apps/web/src/types/contracts.ts`
- `apps/web/src/hooks/useProdwalkConsole.ts`
- `apps/web/src/components/runs/`
- `apps/web/src/components/agents/`
- `apps/web/src/components/evidence/`
- `apps/web/src/components/reports/`
- `apps/web/src/pages/ConsolePage.tsx`
- `apps/web/src/styles/globals.css`

## 已完成

- Run mode 继续支持“模拟走查”和“真实浏览器”。
- browser-use 启动面板默认保持简洁：只暴露人工验证模式，高级参数折叠到 `高级 browser-use 参数`。
- 公开 smoke 默认使用 `verification_mode=off`：
  - UI 初始值为 `off`。
  - 切换到真实浏览器时重置为 `off`。
  - hook 漏传 `verificationMode` 时也回退到 `off`，不再默认 `auto`。
- 登录态 / UAT 场景可在 UI 中切换为 `verification_mode=auto`，并可在高级参数里配置 profile、storage state、success URL、login URL、超时与 max steps。
- browser-use 提交仍走 `POST /api/runs`，mode 为 `browser-use`，并强制 concurrency 为 `1`。
- `awaiting_verification` 已成为前端独立状态，不再只归并到 blocked：
  - SSE 终态包含 `run.awaiting_verification`。
  - artifact refresh 会在等待验证事件后触发。
  - StatusBadge、当前任务、历史列表、Agent timeline、Report/Evidence 面板均可显示该状态。
- 等待验证提示改为中文，并避免暗示当前后端一定会续跑；按钮语义为“记录已完成验证”。
- 结果区显式展示 Report、Evidence、Evaluation、Screenshots 四个入口。
- mock 预览补齐 `awaiting_verification`、`blocked`、`timeout` 的独立事件路径，保留离线预览能力。

## 注意事项

- `POST /verification/confirm` 当前后端仍只是记录确认；如果 browser-use 后台任务已结束，后端可能返回 `blocked`。前端文案已经按这个真实语义处理。
- 真正的 Web visible-browser continuation 仍需要后端把 CLI auth-session / retry 能力抽成 server 可复用能力。
- 前端没有修改 browser-use readiness 检查，只消费现有 FastAPI 错误和 409 guard。

## 验证建议

- `cd apps/web && npm run build`
- 手动检查：
  - mock 模式可切换 running / awaiting_verification / done / blocked / failed / timeout。
  - browser-use 默认 payload 中 `verification_mode=off`。
  - 切换人工验证为自动后，payload 中 `verification_mode=auto`。
  - run 进入 `awaiting_verification` 后，报告、证据、评分、截图入口仍保留。
