# Phase 2 Final Integration Handoff

## Scope

This pass checked Phase 2 pipeline instrumentation, Backend SSE/API alignment, legacy CLI compatibility, and the FastAPI mock-run path. No frontend work or broad feature expansion was added.

## Integration Fix

Updated `src/prodwalk/server/runtime.py` so API-started mock runs now pass a per-run `PipelineEventAdapter` into `ResearchDirector(event_sink=...)`.

The adapter converts pipeline underscore events into the public API/SSE dot-style event contract:

- `run_started` -> `run.started` plus `stage.started`
- `agent_started` -> `agent.started`
- `agent_finished` -> `agent.completed` for succeeded agents, otherwise `agent.status_changed`
- `agent_blocked` -> `agent.status_changed` with `level=warn` and `status=waiting`
- `artifact_written` -> `artifact.created`
- report and evaluation artifact writes also emit `report.generated` and `evaluation.generated`
- `run_completed` -> `stage.completed` plus `run.completed`
- `run_failed` -> `run.failed`

The adapter also updates `run.json`, `agents.json`, and `artifacts.json` as pipeline events arrive. This gives `/api/runs/{run_id}/agents`, `/events`, and `/events/stream` the same contract-level state rather than relying only on backend wrapper events.

Added a server regression assertion in `tests/test_server.py` that verifies API-started mock runs expose dot-style `agent.started`, `agent.completed`, `artifact.created`, and `run.completed` events, and that a walker agent appears in `/agents`.

## Validation Results

### Pytest

Command:

```text
python -m pytest
```

Result:

```text
38 passed, 1 warning
```

The warning is the existing upstream FastAPI/Starlette `TestClient` deprecation warning.

### Legacy CLI

Command:

```text
python -m prodwalk.cli run --config examples/smoke_plan.json --mode mock --out runs_phase2_cli_smoke_py --concurrency 1
```

Result: succeeded and generated `evidence.json`, `report.md`, and `evaluation.json`.

Command:

```text
prodwalk run --config examples/smoke_plan.json --mode mock --out runs_phase2_cli_smoke_entry --concurrency 1
```

Result: succeeded and generated `evidence.json`, `report.md`, and `evaluation.json`.

The temporary smoke output directories were removed after validation.

### FastAPI Mock Run

Validation used a real uvicorn subprocess on `127.0.0.1:8765`, then terminated it at the end of the script.

Observed result:

```text
health 200 True
plans 200 5
post_run 200 run-20260616-163039-a33a65
run_status succeeded
agents 9 ['competitive_analyst', 'director', 'evaluator', 'evidence_extractor', 'planner', 'product_analyst', 'report_writer', 'reviewer', 'walker']
artifacts 8 ['art_agents_json', 'art_artifacts_json', 'art_evaluation_json', 'art_events_jsonl', 'art_evidence_json', 'art_plan_json', 'art_report_md', 'art_run_manifest']
events 29 run.created run.completed
dot_style True
core_artifacts_ok 200 200 200 True True True
sse 200 text/event-stream; charset=utf-8 ['id: 1', 'event: run.event', 'data: {..."type": "run.created"...}']
```

This confirms:

- `GET /api/health` works.
- `GET /api/plans` lists local example plans.
- `POST /api/runs` with `mode=mock` completes.
- `report`, `evidence`, and `evaluation` endpoints return generated content.
- `/events` returns contract-level dot-style event types only.
- `/events/stream` returns SSE with `id`, `event: run.event`, and JSON `data`.

## Remaining Non-Blocking Notes

- Browser-use step-by-step telemetry is still not implemented; mock mode now has lifecycle, agent, artifact, report, evaluation, and terminal run events.
- The current backend still focuses on the mock E2E path. Browser-use execution, richer cancel/resume behavior, and manual verification continuation remain outside this narrow Phase 2 integration fix.
- No frontend files were changed.
