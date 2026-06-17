# Phase 4 Backend Integration Handoff

## Scope

This pass fixed the FastAPI backend surface needed for Phase 4 local frontend integration. No frontend files, database, multi-user auth, or browser-use integration work was added. Mock mode remains the supported E2E path.

## Modified Files

- `src/prodwalk/server/app.py`
- `src/prodwalk/server/models.py`
- `src/prodwalk/server/runtime.py`
- `tests/test_server.py`
- `docs/handoffs/phase4_backend_integration_handoff.md`

## Backend Changes

- CORS allows `http://localhost:5173` and `http://127.0.0.1:5173`.
- `POST /api/runs` still returns immediately with top-level `run_id` and a `run` summary.
- `GET /api/runs` items now include both `id` and `run_id`, plus `status` and `created_at`.
- `GET /api/runs/{run_id}/events` can serve SSE when `Accept: text/event-stream` is present.
- `GET /api/runs/{run_id}/events/stream` validates `run_id` before creating the stream, so missing runs return the unified JSON error.
- Terminal runs replay stored SSE events and then close the stream; active runs stay open for live events and pings.
- Background mock failures set run status to `failed`, persist `run.json`, and emit `run.failed`.
- Evidence responses are normalized for frontend use and no longer expose raw screenshot/local browser paths. Screenshots under `run_dir/screenshots` are exposed only as `screenshot` artifacts.
- Added simple contract-compatible endpoints:
  - `POST /api/runs/{run_id}/cancel`
  - `POST /api/runs/{run_id}/verification/confirm`
  - `GET /api/runs/{run_id}/evidence/{evidence_id}`

## Start Command

From the repo root:

```bash
pip install -e ".[server]"
uvicorn prodwalk.server.app:app --host 127.0.0.1 --port 8765 --reload
```

The Phase 3 Vite proxy expects the backend at `http://127.0.0.1:8765`.

## API Examples

Health:

```bash
curl http://127.0.0.1:8765/api/health
```

List plans:

```bash
curl http://127.0.0.1:8765/api/plans
```

Start a mock run:

```bash
curl -X POST http://127.0.0.1:8765/api/runs \
  -H "Content-Type: application/json" \
  -d '{"config_path":"examples/smoke_plan.json","mode":"mock","out":"runs","concurrency":1}'
```

Read completed artifacts:

```bash
curl http://127.0.0.1:8765/api/runs/{run_id}/report
curl http://127.0.0.1:8765/api/runs/{run_id}/evidence
curl http://127.0.0.1:8765/api/runs/{run_id}/evaluation
```

Missing run error shape:

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run not found: run-missing",
    "details": {
      "run_id": "run-missing"
    },
    "request_id": "req_..."
  }
}
```

## SSE Example

Canonical endpoint:

```text
GET /api/runs/{run_id}/events/stream?after_seq=0
Accept: text/event-stream
```

Frame format:

```text
id: 1
event: run.event
data: {"id":"evt_000001","run_id":"run-...","seq":1,"ts":"2026-06-16T12:23:37.499343+00:00","type":"run.created","level":"info","message":"Run created","agent_id":null,"agent_type":null,"product":null,"scenario_id":null,"step_index":null,"status":"queued","payload":{},"artifact_ids":[]}

```

Heartbeat for active streams:

```text
event: ping
data: {"time":"2026-06-16T12:24:00.000000+00:00"}

```

## Validation

Server tests:

```text
python -m pytest tests/test_server.py
8 passed, 1 warning
```

Full test suite:

```text
python -m pytest
42 passed, 1 warning
```

The warning is the existing FastAPI/Starlette `TestClient` deprecation warning.

Real uvicorn smoke on `127.0.0.1:8765`:

```text
health True
cors_origin http://localhost:5173
status succeeded
sse ['id: 1', 'event: run.event', 'data: {...']
```

## Legacy CLI Verification

Both legacy commands were verified and produced `evidence.json`, `report.md`, and `evaluation.json`:

```bash
python -m prodwalk.cli run --config examples/smoke_plan.json --mode mock --out runs_phase4_cli_smoke_py --concurrency 1
prodwalk run --config examples/smoke_plan.json --mode mock --out runs_phase4_cli_smoke_entry --concurrency 1
```

Temporary smoke output directories were removed after verification.

## Frontend Follow-Up

- Continue using `/api/runs/{run_id}/events/stream` and listen for `run.event`.
- Browser-use mode is still intentionally gated; `POST /api/runs` supports mock mode only for Phase 4.
- Frontend error handling should parse the unified `error` payload instead of showing only generic HTTP errors.
- `RunDetail.error` and `AgentExecution.error` remain structured objects or `null`; render them as formatted messages.
- The new evidence detail route exists, but the Phase 3 frontend client still needs a `getEvidenceDetail` method if deep links are wired.
- Inferred historical CLI runs may still have `mode: "unknown"` because old run folders do not store Web metadata.
