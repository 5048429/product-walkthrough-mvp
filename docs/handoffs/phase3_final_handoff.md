# Phase 3 Final Frontend Integration Handoff

## Scope

This pass integrated and accepted the Phase 3 mock frontend console in `apps/web`.

Only these allowed areas were changed:

- `apps/web/`
- `docs/handoffs/phase3_final_handoff.md`

No backend, `src/prodwalk/`, FastAPI, or Phase 2 documents were modified.

## Frontend Commands

Install dependencies:

```bash
cd apps/web
npm install
```

Result: passed. The install was already up to date, audited 24 packages, and reported 0 vulnerabilities.

Start the local frontend:

```bash
cd apps/web
npm run dev
```

Verified URL:

```text
http://127.0.0.1:5173/
```

`vite.config.ts` keeps the dev proxy from `/api` to `http://127.0.0.1:8765`.

Build:

```bash
cd apps/web
npm run build
```

Result: passed.

Build command ran:

- `tsc --noEmit -p tsconfig.json`
- `tsc --noEmit -p tsconfig.node.json`
- `vite build`

Latest build output included:

- `dist/index.html`
- `dist/assets/index-D3_a6KUR.css`
- `dist/assets/index-2MURq6Ig.js`

## Browser Smoke Check

Checked `http://127.0.0.1:5173/` in the in-app browser.

Confirmed page contains:

- Run start area: `Run Start`
- Plan selection area: `Plan`
- Agent status area: `Agent Status`
- Realtime event log area: `Live Event Log`
- Evidence area: `Evidence`
- Report preview area: `Report Preview`

Additional checks:

- Browser console warnings/errors: none.
- Default viewport `1280x720`: no horizontal page scroll.
- Artifact links resolve through backend content endpoints, for example `/api/runs/{run_id}/artifacts/{artifact_id}/content`.
- Mock status selector changes state across run, agents, events, report, and evidence.
- `idle` state clears active run, events, report, and evidence.
- `blocked` state keeps recoverable report/evidence visible and shows missing screenshot handling.

## Page And Component Inventory

Entry:

- `apps/web/src/main.tsx`
- `apps/web/src/App.tsx`
- `apps/web/src/pages/ConsolePage.tsx`

Layout:

- `apps/web/src/components/layout/AppShell.tsx`
- `apps/web/src/components/layout/TopRunContextBar.tsx`

Run and plan:

- `apps/web/src/components/runs/RunLauncher.tsx`
- `apps/web/src/components/runs/RunStartPanel.tsx`
- `apps/web/src/components/runs/PlanSelector.tsx`
- `apps/web/src/components/runs/RunModeSelector.tsx`
- `apps/web/src/components/runs/RecentRunsList.tsx`

Agent status:

- `apps/web/src/components/agents/AgentStatusBoard.tsx`
- `apps/web/src/components/agents/AgentStatusPanel.tsx`
- `apps/web/src/components/agents/AgentTimeline.tsx`
- `apps/web/src/components/agents/AgentStatusCard.tsx`

Events:

- `apps/web/src/components/events/EventLog.tsx`

Evidence:

- `apps/web/src/components/evidence/EvidenceSnapshot.tsx`
- `apps/web/src/components/evidence/EvidenceList.tsx`
- `apps/web/src/components/evidence/EvidenceItemCard.tsx`

Report:

- `apps/web/src/components/reports/ReportPreview.tsx`
- `apps/web/src/components/reports/ReportToolbar.tsx`

Common UI:

- `apps/web/src/components/StatusBadge.tsx`
- `apps/web/src/components/common/ArtifactLink.tsx`
- `apps/web/src/components/common/EmptyState.tsx`
- `apps/web/src/components/common/ErrorState.tsx`

Styles:

- `apps/web/src/styles/globals.css`

## Mock Data

All current UI rendering is mock-driven.

The page uses:

- `apps/web/src/api/mockConsoleData.ts`

Underlying mock files:

- `apps/web/src/mock/plans.ts`
- `apps/web/src/mock/runs.ts`
- `apps/web/src/mock/agents.ts`
- `apps/web/src/mock/events.ts`
- `apps/web/src/mock/artifacts.ts`
- `apps/web/src/mock/evidence.ts`
- `apps/web/src/mock/report.ts`

Status-derived mock helpers:

- `getMockAgentsForStatus(status)`
- `getMockEventsForStatus(status)`

Prepared API/SSE code exists but is not called by `ConsolePage` yet:

- `apps/web/src/api/client.ts`
- `apps/web/src/api/sse.ts`

## API And Event Types

Central frontend contract file:

- `apps/web/src/types/contracts.ts`

Aligned type groups:

- `RunStatus`
- `AgentStatus`
- `AgentType`
- `ArtifactType`
- `EventLevel`
- `RunEventType`
- `ConsoleStatus`
- `RunMode`
- `VerificationMode`
- `RunSummary`
- `RunDetail`
- `RunParams`
- `RunCreateRequest`
- `AgentExecution`
- `Artifact`
- `RunEvent`
- `PlanSummary`
- `EvidenceItem`
- `EvidenceResponse`
- `ReportResponse`
- `EvaluationResponse`
- shared list/action/API response envelopes

Status mapping helpers now live with the contracts:

- `toConsoleStatus(status)`
- `toRunStatus(status)`

API URL construction is centralized in:

- `apps/web/src/api/paths.ts`

SSE wrapper uses the final endpoint:

- `/api/runs/{run_id}/events/stream`

Artifact links use only the backend content endpoint:

- `/api/runs/{run_id}/artifacts/{artifact_id}/content`

No frontend code reads or joins local artifact filesystem paths.

## Phase 4 API Integration Touch Points

Recommended files to update when connecting real FastAPI data:

- `apps/web/src/pages/ConsolePage.tsx`
  - Replace `mockConsoleData` wiring with real query/state orchestration.
  - Load plans, active run, agents, events, evidence, report, and evaluation through API calls.

- `apps/web/src/api/client.ts`
  - Use existing typed methods for plans, runs, cancel, verification confirm, agents, events, artifacts, report, evidence, and evaluation.
  - Add a stricter single-evidence detail response type after the backend schema is finalized.

- `apps/web/src/api/sse.ts`
  - Subscribe to `openRunEventStream` for the active run.
  - Dedupe events by `seq`.
  - Reconnect with `after_seq`.
  - Refetch run/agents/artifacts on lifecycle and artifact events.

- `apps/web/src/api/mockConsoleData.ts` and `apps/web/src/mock/*`
  - Keep as fallback fixtures or remove once the API path is stable.

- `apps/web/src/components/runs/RunStartPanel.tsx`
  - Replace mock status buttons with `prodwalkApi.createRun`.
  - Wire `Start Mock Run` and browser-use/manual verification params into `RunCreateRequest`.

- `apps/web/src/components/layout/TopRunContextBar.tsx`
  - Wire top actions to create, cancel, retry, and report navigation.

- `apps/web/src/components/events/EventLog.tsx`
  - Feed persisted events plus SSE events.
  - Add reconnect state display if needed.

- `apps/web/src/components/reports/ReportPreview.tsx`
  - Feed real `/report` and `/evaluation`.
  - Keep partial report behavior when evaluation is missing.

- `apps/web/src/components/evidence/EvidenceList.tsx`
  - Feed real `/evidence`.
  - Add single evidence detail loading if Phase 4 adds a detail drawer route.

- `apps/web/src/components/common/ArtifactLink.tsx`
  - Already points to backend artifact content URLs and should continue to avoid local path access.

## Current Remaining Issues

- No real backend API calls are made by the page yet.
- No live SSE subscription is active yet.
- Route-level pages are not implemented; this is still one integrated console workbench.
- Top context bar action buttons are visual placeholders; run controls in `RunStartPanel` only change mock UI state.
- Report preview is a lightweight Markdown display, not a full Markdown renderer.
- Screenshot previews are link/missing-state based; no real image preview is fetched yet.
- Single evidence detail endpoint type is intentionally not fixed in the frontend until the backend response schema is final.
- No automated frontend test runner is configured; verification is currently `npm run build` plus browser smoke checks.
