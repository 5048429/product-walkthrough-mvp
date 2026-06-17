# Phase 5 Final Integration QA Handoff

## Scope

This handoff records the final Phase 5 integration QA for the local Prodwalk FastAPI server and `apps/web` console. It covers the frontend-launched mock run path, realtime events, report/evidence/evaluation readability, historical run selection, artifact path safety, tests, build, and legacy CLI compatibility.

No production code changes were required during this QA pass.

## Backend Start Command

Command used:

```powershell
python -m uvicorn prodwalk.server.app:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Result:

```text
ok=true, service=prodwalk-server, version=0.4.5
```

## Frontend Start Command

Command used:

```powershell
cd apps/web
cmd /c "set VITE_API_BASE_URL=http://127.0.0.1:8000&& npm run dev -- --host 127.0.0.1 --port 5173"
```

Open:

```text
http://127.0.0.1:5173/
```

Note: port `5175` was not accepted by the current backend CORS allowlist, so the final QA run used `5173`, which is allowed by `src/prodwalk/server/app.py`.

## Phase 5 Completed Capabilities

- Backend artifact APIs expose report, evidence, evaluation, fixed run files, safe run-relative artifact paths, and screenshot endpoints through API URLs only.
- Artifact responses include `X-Content-Type-Options: nosniff`.
- Artifact path traversal and unsafe path segments are rejected.
- Evidence Viewer supports search/filter/grouping, selected evidence details, real screenshot preview component states, and missing screenshot visibility.
- Report Preview renders Markdown into readable structured UI, keeps copy/download controls, and does not render raw HTML via unsafe injection.
- Run History shows artifact availability and can open historical report/evidence/evaluation without replacing the active run context.
- Evaluation is available as a standalone panel for active and historical runs.
- Realtime events still use `/api/runs/{run_id}/events/stream` and close cleanly after terminal events.

## Frontend Mock Run Acceptance

Run launched from the frontend:

```text
run_id: run-20260617-100055-c72785
config_path: examples/smoke_plan.json
mode: mock
final UI status: done
final UI source: closed
run_dir: runs/run-20260617-100055-c72785
```

Realtime UI result:

```text
Live Event Log: 29 of 29 events shown. SSE closed.
Top bar: Status done, Source closed.
Agent Status: all required stages completed or skipped.
```

Direct SSE check:

```text
GET /api/runs/run-20260617-100055-c72785/events/stream?after_seq=0
status: 200
content-type: text/event-stream; charset=utf-8
first frame: id: 1, event: run.event, data.type: run.created
```

Direct API check:

```text
run_status: succeeded
event_count: 29
first_event: run.created
last_event: run.completed
artifact_ids: art_run_manifest, art_plan_json, art_events_jsonl, art_agents_json, art_artifacts_json, art_evidence_json, art_report_md, art_evaluation_json
report_has_markdown: true
evidence_items: 5
evaluation_overall_score: 1.0
screenshot_count: 0
```

Browser console errors:

```text
none
```

## Evidence Viewer Acceptance

Accepted for active run and historical run:

```text
Evidence: art_evidence_json / 5 of 5 items
Search/filter/group controls visible
Selected Evidence panel visible
Evidence details include id, product, scenario, status, confidence, action, source URL, and artifact links where present
Missing screenshot state is visible per item and does not hide evidence
```

The active run did not emit evidence-id event tokens in the Event Log, so event-to-specific-evidence focus was not covered by this final run. Event artifact tokens were visible.

## Screenshot And Artifact Acceptance

Workspace scan found no real image files under `runs*/run-*/screenshots/`, and the accepted frontend run reported:

```text
screenshot_count: 0
```

Therefore real screenshot image display was not applicable for this workspace state. The Evidence Viewer correctly displayed `Missing screenshot` for mock evidence.

Backend screenshot/artifact behavior was covered by tests:

```text
test_runs_lists_historical_run_with_artifact_availability
test_text_artifact_and_screenshot_are_readable
```

Manual artifact path safety check against the accepted run:

```text
GET /api/runs/run-20260617-100055-c72785/artifacts/%2E%2E%2Fsecret.txt
status: 403
code: ARTIFACT_FORBIDDEN
```

Targeted artifact/path test result:

```text
python -m pytest tests/test_server.py -k "artifact or traversal or screenshot or forbidden or path" -q
6 passed, 6 deselected, 1 warning in 2.43s
```

## Report Preview Acceptance

Accepted for active run and historical run:

```text
Report Preview: art_report_md / en
Rendered heading: Product Walkthrough Research Report
Rendered sections: Scope, Scenario Coverage, Product Findings, Competitive Insights, Reviewer Notes, Evidence Appendix, Scenario Definitions
Copy Markdown button enabled
Download report.md button enabled
Evaluation artifact link visible
```

The rendered report stayed visible while evaluation data was loaded separately.

## Run History Acceptance

Historical run opened from the Run History panel:

```text
history_run_id: run-20260616-211717-4c6cc0
```

Accepted behavior:

```text
Run History listed local runs with report/evidence/evaluation availability and screenshot counts.
Clicking the historical run opened historical report/evidence/evaluation.
Historical panels showed Historical run context.
Back to Active was available.
Top bar and Live Event Log remained tied to active run run-20260617-100055-c72785.
```

## Evaluation Acceptance

Accepted for active run:

```text
Evaluation: Active run / art_evaluation_json
overall_score: 100%
task_completion_rate: 100%
evidence_coverage_rate: 100%
finding_grounding_rate: 100%
recommendation_actionability_rate: 100%
notes: MVP run meets the configured basic evaluation thresholds.
```

Accepted for historical run:

```text
Evaluation: Historical run / art_evaluation_json
overall_score: 100%
scores and notes visible
```

## Pytest Result

Command:

```powershell
python -m pytest
```

Result:

```text
46 passed, 1 warning in 5.94s
```

Known warning:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

## Frontend Build Result

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

## Legacy CLI Verification

Command:

```powershell
python -m prodwalk.cli run --config examples/smoke_plan.json --mode mock --out $env:TEMP\prodwalk_phase5_final_cli_py --concurrency 1
```

Result:

```text
MVP walkthrough run completed
Generated evidence.json, report.md, evaluation.json
```

Command:

```powershell
prodwalk run --config examples/smoke_plan.json --mode mock --out $env:TEMP\prodwalk_phase5_final_cli_entry --concurrency 1
```

Result:

```text
MVP walkthrough run completed
Generated evidence.json, report.md, evaluation.json
```

## Known Issues

- No real screenshot images exist in the current workspace run directories, so final UI QA could only verify missing screenshot states. Screenshot image serving remains covered by backend tests.
- Backend CORS currently allows `5173`, `5174`, and `3000`, but not arbitrary Vite ports such as `5175`.
- Event Log to Evidence focus could not be fully exercised because the accepted mock run did not include evidence id values in event payloads.
- Web browser-use run creation remains gated; Phase 5 final QA covered the required mock path.
- The console remains a single workbench rather than route-level pages.
- One backend log entry showed a Windows connection reset after the manual `curl --max-time` SSE check; this was caused by intentionally terminating the streaming client.

## Phase 6 Suggested Tasks

- Add a checked-in or generated non-sensitive screenshot fixture run for repeatable UI screenshot preview QA.
- Emit evidence-specific ids in relevant lifecycle/event payloads so Event Log to Evidence focus can be covered end to end.
- Decide whether local dev CORS should include a wider Vite port range or whether the frontend should standardize on `5173`.
- Add browser E2E automation for frontend mock run launch, SSE closure, report/evidence/evaluation rendering, historical run selection, and missing screenshot states.
- Add route-level deep links for active and historical report/evidence/evaluation views.
- Implement and QA Web browser-use run creation and manual verification flow when backend support is ready.
