# Phase 6 UI Simplification Handoff

## Scope

This pass simplified `apps/web` from a multi-panel engineering console into a product-manager workbench while preserving the Phase 5 mock run loop.

No backend files, `src/prodwalk/`, or `pyproject.toml` were modified.

## Before / After

Before:
- The homepage rendered launch controls, run history, evaluation, agent board, live event log, report, and evidence at the same time.
- API source, SSE state, run directory, artifact ids, request payload, mock fallback state controls, and raw event details were visible by default.
- Report and evidence were pushed into the lower workbench area instead of being the primary review surface.

After:
- The homepage is a PM workbench with a top run context bar, view tabs, and a default Dashboard.
- Default Dashboard shows plan selection, run mode, Start Mock Run / Stop, current run status, simplified agent progress, recent activity, Report Preview, and collapsed Evidence/Screenshots and Run History entries.
- Report, Evidence, History, and Details are single-task views selected by tabs.
- Full Agent Status, Live Event Log, source/API/SSE details, run params, artifact links, and raw-ish debug views live under Details or explicit collapsible sections.

## Hidden / Folded / Reduced

- Hidden from the default homepage:
  - Full Live Event Log.
  - Raw event payload summaries.
  - Source/SSE/run directory fields in the top bar.
  - API request / mock request payload.
  - Mock fallback status selector.
  - Browser-use start CTA as an equal primary action.
  - Raw `report.md` / `evaluation.json` artifact links.
  - Evidence artifact ids, sanitized data, and `final_output`.
  - Run history raw yes/no artifact availability and screenshot counts.
- Folded into Details / Debug:
  - API health/source/SSE state.
  - Retry API.
  - Run params.
  - Artifact ids and artifact links.
  - Agent Status full board.
  - Live Event Log full stream.
  - Mock fallback preview state controls.
- Reduced in default views:
  - Evidence filters now default to Search, Product, Scenario; Kind/Status/Group moved under More filters.
  - Report toolbar defaults to Copy Markdown; download/source links are under More.
  - Top bar now shows plan, mode, status, progress, elapsed, run, and primary actions.

## Core Functions Kept

- Local plan selection and plan summary.
- Mock run launch path.
- Active run status, progress, and run context.
- SSE-driven events and derived agent state.
- Report Preview with Markdown rendering, copy, download, and evaluation summary.
- Evidence viewer with search/filter, selected evidence details, screenshots/missing screenshot states, and safe artifact links.
- Run History selection for historical report/evidence/evaluation review.
- Partial artifact behavior for running/blocked/failed runs.
- Debug access to event log, agents, artifacts, and API state.

## Validation

Build:

```text
cd apps/web
npm run build
```

Result:

```text
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
55 modules transformed
built successfully
```

Browser smoke check:
- Opened `http://127.0.0.1:5173/` with the API unavailable, so the UI used mock fallback preview.
- Default Dashboard showed `Prodwalk PM Workbench`, `Start Mock Run`, and `Report Preview`.
- Default Dashboard did not expose `Live Event Log`.
- Details tab showed `API / Debug`, `Agent Status`, and `Live Event Log`.
- Desktop and narrow viewport checks reported no horizontal overflow.
- Browser console error check returned no errors.

Frontend-launched mock run check:
- Reused the running backend at `http://127.0.0.1:8000`.
- Started the frontend at `http://127.0.0.1:5173/`.
- Selected `examples/smoke_plan.json`.
- Launched a mock run from the Dashboard launcher.
- Resulting active run: `run-20260617-113018-1daa94`.
- Final UI state: Done, progress `1/1`, report visible, Evidence/Screenshots entry visible, no `Live Event Log` on the default Dashboard.
- Browser console error check returned no errors.

## Notes

- `apps/web/src/components/runs/` is ignored by the repository because `.gitignore` contains `runs/`. The files in that directory still exist and are imported by the app, and this pass updated their local contents, but they do not appear in ordinary `git diff` / `git status` output unless the ignore rule is changed or files are force-added.
- Browser-use run creation remains gated. The UI keeps browser-use visible only as a disabled/gated advanced option until the backend path is ready.
- Stop remains visible but disabled because the existing console did not expose a wired stop action through the current hook.
- Real screenshot image rendering was not re-verified because the available mock data still has missing screenshot states rather than real screenshot files.
