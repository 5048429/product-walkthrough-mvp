# Phase 4 Frontend API Integration Handoff

## Scope

This pass connected the Phase 3 mock console in `apps/web` to the Phase 2 FastAPI backend while preserving a local mock fallback for preview when the API is unavailable.

No files under `src/prodwalk/`, `tests/`, `pyproject.toml`, or `docs/api_event_contract.md` were modified.

## Modified Files

- `apps/web/.env.example`
- `apps/web/src/api/client.ts`
- `apps/web/src/api/paths.ts`
- `apps/web/src/api/sse.ts`
- `apps/web/src/hooks/useProdwalkConsole.ts`
- `apps/web/src/types/contracts.ts`
- `apps/web/src/pages/ConsolePage.tsx`
- `apps/web/src/components/agents/AgentStatusCard.tsx`
- `apps/web/src/components/events/EventLog.tsx`
- `apps/web/src/components/evidence/EvidenceList.tsx`
- `apps/web/src/components/evidence/EvidenceSnapshot.tsx`
- `apps/web/src/components/layout/TopRunContextBar.tsx`
- `apps/web/src/components/reports/ReportPreview.tsx`
- `apps/web/src/components/runs/PlanSelector.tsx`
- `apps/web/src/components/runs/RecentRunsList.tsx`
- `apps/web/src/components/runs/RunLauncher.tsx`
- `apps/web/src/components/runs/RunStartPanel.tsx`
- `apps/web/src/styles/globals.css`
- `docs/handoffs/phase4_frontend_integration_handoff.md`

## API Client Usage

The API client lives in `apps/web/src/api/client.ts` and is exposed as `prodwalkApi`.

Connected methods:

- `prodwalkApi.getHealth()` -> `GET /api/health`
- `prodwalkApi.getPlans()` -> `GET /api/plans`
- `prodwalkApi.getPlan(planId)` -> `GET /api/plans/{name}`
- `prodwalkApi.createRun(body)` -> `POST /api/runs`
- `prodwalkApi.listRuns(limit)` -> `GET /api/runs`
- `prodwalkApi.getRun(runId)` -> `GET /api/runs/{run_id}`
- `prodwalkApi.getEvents(runId, afterSeq, limit)` -> `GET /api/runs/{run_id}/events`
- `prodwalkApi.getReport(runId)` -> `GET /api/runs/{run_id}/report`
- `prodwalkApi.getEvidence(runId)` -> `GET /api/runs/{run_id}/evidence`
- `prodwalkApi.getEvaluation(runId)` -> `GET /api/runs/{run_id}/evaluation`

The client parses the unified backend error payload into `ProdwalkApiError`. Network failures use `status=0` and `code=NETWORK_ERROR`, which is what the console uses to enter mock fallback.

The client also normalizes known contract drift:

- Historical run `mode: "unknown"` is accepted.
- `RunDetail.error` and `AgentExecution.error` may be objects or strings.
- Evidence items are normalized enough for the Phase 3 evidence UI.
- Raw local screenshot paths are not converted into links; screenshot access remains artifact-id based only.

## Environment Variables

`apps/web/src/api/paths.ts` reads:

```text
VITE_API_BASE_URL
```

Default:

```text
http://localhost:8000
```

The client appends `/api` automatically. If the value already ends with `/api`, it will not append a second `/api`.

Example:

```text
VITE_API_BASE_URL=http://localhost:8000
```

For a backend running on the Phase 2 smoke port, use:

```text
VITE_API_BASE_URL=http://127.0.0.1:8765
```

`VITE_PRODWALK_API_BASE_URL` is still accepted as a legacy fallback, but new setups should use `VITE_API_BASE_URL`.

## SSE Handling

SSE is implemented by `apps/web/src/api/sse.ts` and orchestrated by `apps/web/src/hooks/useProdwalkConsole.ts`.

The stream URL is:

```text
GET /api/runs/{run_id}/events/stream?after_seq=N
```

Behavior:

- After `POST /api/runs`, the console saves `activeRunId` in `localStorage`.
- The hook loads persisted events with `GET /events`.
- It opens `EventSource` using the latest known `seq` as `after_seq`.
- Incoming `run.event` frames are parsed and appended to the Event Log.
- Events are deduplicated by `seq`.
- `ping` frames are handled by the browser/EventSource layer and are not appended to the Event Log.
- Connection state is surfaced in the UI as `idle`, `connecting`, `open`, `error`, or `closed`.
- Native EventSource reconnect is allowed to run; duplicate replay is safe because of `seq` dedupe.
- Terminal events close the active stream UI state and trigger final artifact loading.

## Agent Status Derivation

Agent status is derived from `RunEvent` data in `deriveAgentsFromEvents()` inside `apps/web/src/hooks/useProdwalkConsole.ts`.

Rules:

- Agent identity uses `agent_id` when present.
- If `agent_id` is absent but `agent_type` exists, a stable fallback id is derived from type/product/scenario.
- `agent.started` -> `running`
- `agent.completed` -> `succeeded` unless event `status` is a valid agent status.
- `agent.failed` -> `failed`
- `agent.status_changed` -> event `status`, falling back to the previous agent status.
- `step_index` updates `current_step`.
- Primitive payload values are copied into `metrics`.
- Failed agents keep event payload/message as their displayable error.

No hard-coded Phase 3 mock agent list is used for the live Agent Status panel.

## Artifact Loading

When lifecycle or artifact events arrive, the hook refreshes run detail and artifacts. On terminal or report/evaluation/evidence artifact events, it loads:

- `GET /api/runs/{run_id}/report`
- `GET /api/runs/{run_id}/evidence`
- `GET /api/runs/{run_id}/evaluation`

Failures are stored independently:

- report failure does not hide evidence.
- evidence failure does not hide report.
- evaluation failure does not hide Markdown report.

## Mock Fallback

Fallback is automatic only for network-level API failures, such as the backend not running.

Fallback uses the existing Phase 3 fixtures:

- `apps/web/src/api/mockConsoleData.ts`
- `apps/web/src/mock/*`

The UI clearly shows `Mock fallback` and exposes a `Retry API` action. In fallback mode, the user can still preview idle/running/done/blocked/failed states with local fixture data.

## Frontend联调启动方式

Backend:

```bash
uvicorn prodwalk.server.app:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173/
```

If the backend uses another port:

```bash
cd apps/web
VITE_API_BASE_URL=http://127.0.0.1:8765 npm run dev
```

On Windows PowerShell:

```powershell
cd apps/web
$env:VITE_API_BASE_URL="http://127.0.0.1:8765"
npm run dev
```

## Build Result

Command:

```bash
cd apps/web
npm run build
```

Result:

```text
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
✓ built
```

Latest output:

- `dist/index.html`
- `dist/assets/index-D0U1z88j.css`
- `dist/assets/index-DT32I21b.js`

## Backend Follow-Up Needed

- `POST /api/runs/{run_id}/cancel` is still missing, so Stop remains disabled.
- `POST /api/runs/{run_id}/verification/confirm` is still missing, so manual verification cannot be completed from the UI.
- `POST /api/runs` currently supports only `mode="mock"`; Browser Run is gated in the UI.
- `GET /api/runs/{run_id}/evidence/{evidence_id}` is still missing, so evidence detail/deep-link behavior is local-only.
- Evidence response should be normalized by the backend and should avoid exposing raw local screenshot/storage/user-data paths.
- Screenshot files should eventually be registered as `screenshot` artifacts and referenced through `screenshot_artifact_id`.
- Backend can improve mock telemetry with optional `scenario.*`, `evidence.created`, and `finding.created` events, but the current frontend does not depend on them.
