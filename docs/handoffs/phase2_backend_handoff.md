# Phase 2 Backend API Handoff

## What Changed

Added the first FastAPI service layer under `src/prodwalk/server/`:

- `app.py`: `create_app()` and module-level `app`, CORS, routes, and unified JSON errors.
- `models.py`: API request/response models and shared enum literals.
- `runtime.py`: in-memory run state, plan loading, run directory scanning, event JSONL, SSE fanout, artifact registry, and mock pipeline background execution.

The existing CLI path is unchanged. The backend reuses `ResearchDirector` with `MockBrowserWalker` for API-started mock runs.

## Implemented Endpoints

- `GET /api/health`
- `GET /api/plans`
- `GET /api/plans/{name}`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/agents`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/events/stream`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}/content`
- `GET /api/runs/{run_id}/report`
- `GET /api/runs/{run_id}/evidence`
- `GET /api/runs/{run_id}/evaluation`

`GET /api/runs/{run_id}/events` returns JSON by default, but also serves SSE when the request `Accept` header contains `text/event-stream`. The canonical frontend SSE path should be `/api/runs/{run_id}/events/stream`.

## Start The Server

Install the server extra, then run uvicorn:

```bash
pip install -e ".[server]"
uvicorn prodwalk.server.app:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`.

## POST /api/runs Example

```json
{
  "plan_name": "smoke_plan.json",
  "mode": "mock",
  "out": "runs",
  "concurrency": 3,
  "report_language": "en"
}
```

Also supported:

- `config_path`: for plans under `examples/`, for example `examples/research_plan.json`
- `config`: either an inline plan object or a plan path string
- `plan`: inline plan object

The response includes top-level `run_id`, `status`, `created_at`, `events_url`, `report_url`, `evidence_url`, and `evaluation_url`, plus a `run` summary object.

## SSE Consumption

Use browser `EventSource`:

```ts
const source = new EventSource(`/api/runs/${runId}/events/stream?after_seq=${lastSeq}`);

source.addEventListener("run.event", (event) => {
  const payload = JSON.parse(event.data);
  // Deduplicate by payload.seq.
});
```

Heartbeat events are sent as `event: ping` with `{ "time": "..." }`.

## Current Mode Support

Only `mode: "mock"` is implemented for API-started runs. Browser-use fields are accepted in the request model for contract stability, but non-mock modes return `BAD_REQUEST` for now.

## Frontend Agent Next Steps

- Use `GET /api/plans` for the plan picker and pass `plan_name` or `config_path` to `POST /api/runs`.
- Navigate to the returned `run_id` and subscribe to `events_url`.
- Use `GET /api/runs/{run_id}` for status refresh and `GET /api/runs/{run_id}/events?after_seq=N` for reconnect backfill.
- Render report from `GET /api/runs/{run_id}/report` using the `markdown` field.
- Render evidence from `GET /api/runs/{run_id}/evidence`.
- Render evaluation from `GET /api/runs/{run_id}/evaluation`.

## Tests

Command run:

```bash
python -m pytest tests/test_server.py
```

Result: `4 passed`.

Full regression command also run:

```bash
python -m pytest
```

Result: `38 passed`, with one upstream Starlette/FastAPI `TestClient` deprecation warning.

## Pipeline Instrumentation Alignment Points

`docs/handoffs/phase2_pipeline_handoff.md` was not present when this backend pass started. The backend currently emits lifecycle, stage, artifact, report, evaluation, and terminal run events from the wrapper around `ResearchDirector`.

The Pipeline Instrumentation Agent should align on:

- Whether `ResearchDirector` should expose callbacks for planner, walker, analyst, reviewer, report writer, and evaluator stages.
- How to emit per-scenario and per-step events without duplicating or reordering events already written by the backend wrapper.
- Whether future browser-use screenshots and history files should be registered immediately as artifacts or only during finalization.
- How manual verification states should transition between `awaiting_verification`, `running`, `blocked`, and `failed`.
- A stable contract for agent IDs beyond the current minimal `agent_director` placeholder.
