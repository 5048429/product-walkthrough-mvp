# Phase 5 Run History Evaluation Handoff

## Scope

This pass enhanced the frontend-only Run History and Evaluation surfaces for the local Prodwalk console.

Changed areas:

- `apps/web/src/types/contracts.ts`
- `apps/web/src/api/client.ts`
- `apps/web/src/hooks/useProdwalkConsole.ts`
- `apps/web/src/pages/ConsolePage.tsx`
- `apps/web/src/components/runs/RunHistoryPanel.tsx`
- `apps/web/src/components/evaluation/EvaluationSummary.tsx`
- `apps/web/src/mock/runs.ts`

No backend code, `src/prodwalk/`, ReportPreview body, or Evidence Viewer body was modified.

## Run History Data Flow

Run history is sourced from:

```text
ConsolePage
  -> useProdwalkConsole.initializeApi()
  -> prodwalkApi.listRuns(20)
  -> GET /api/runs
  -> normalizeRunSummary()
  -> recentRuns
  -> RunHistoryPanel
```

Manual refresh uses:

```text
RunHistoryPanel Refresh
  -> useProdwalkConsole.refreshRunHistory()
  -> prodwalkApi.listRuns(50)
  -> GET /api/runs
  -> recentRuns
```

`RunSummary` now consumes both `id` and `run_id`, plus:

- `report_exists`
- `evidence_exists`
- `evaluation_exists`
- `screenshot_count`

The Run History panel displays run id, status, created time, mode/research goal, artifact availability, screenshot count, active marker, and selected historical viewing marker.

## Historical Run Selection

Clicking a non-active historical run no longer overwrites `activeRunId`.

The hook keeps active and historical state separate:

- Active state: `activeRun`, `events`, `artifacts`, `report`, `evidence`, `evaluation`
- Historical state: `selectedHistoryRun`, `historyArtifacts`, `historyReport`, `historyEvidence`, `historyEvaluation`

Top bar, Agent Status, Live Event Log, and SSE remain tied to the active run. Report, Evidence, and Evaluation panels use the selected historical bundle when `viewingHistory` is true.

Clicking the active run row or `Back to Active` clears historical selection and returns the artifact panels to active-run data.

## Interfaces Loaded After Historical Click

For an API-backed historical selection:

```text
GET /api/runs/{run_id}
GET /api/runs/{run_id}/artifacts
GET /api/runs/{run_id}/report        when report.md is available
GET /api/runs/{run_id}/evidence      when evidence.json is available
GET /api/runs/{run_id}/evaluation    when evaluation.json is available
```

If the run detail reports a missing artifact, the UI records an unavailable state instead of issuing a guaranteed 404 for that artifact.

## Evaluation Display Logic

`EvaluationSummary` is a new standalone panel. It displays:

- `overall_score`
- every item in `scores`
- `notes`
- active vs historical context
- loading, empty, and unavailable states

ReportPreview still receives `report.evaluation` when evaluation loads successfully, so the existing report-side evaluation remains compatible.

## Build Result

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
55 modules transformed
dist/index.html
dist/assets/index-D0U1z88j.css
dist/assets/index-DJScRL3g.js
built successfully
```

## Remaining Issues

- The console is still a single workbench page rather than route-level run history/detail pages.
- Historical Agent Status and Event Log are not loaded; they remain active-run focused by design in this pass.
- Browser-use Web run creation remains gated by existing backend behavior.
- ReportPreview still renders raw Markdown in a `<pre>` and was intentionally not modified.
- Evidence detail still uses the existing list/detail behavior; no new evidence detail endpoint wiring was added in this pass.
