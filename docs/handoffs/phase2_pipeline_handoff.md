# Phase 2 Pipeline Instrumentation Handoff

## Files changed

- `src/prodwalk/events.py`
  - Added the `RunEvent` dataclass.
  - Added supported event type and agent name constants.
  - Added `dispatch_run_event(...)` for sync or async sinks/callbacks.
- `src/prodwalk/agents/director.py`
  - Added optional `event_sink` and `event_callback` constructor arguments.
  - Emits run lifecycle, agent lifecycle, blocked walkthrough, and artifact events.
  - Preserves existing CLI behavior when no sink/callback is passed.
- `tests/test_events.py`
  - Added mock-run instrumentation tests using `MockBrowserWalker`.
- `docs/handoffs/phase2_pipeline_handoff.md`
  - This handoff.

## RunEvent final fields

`RunEvent` is implemented in `src/prodwalk/events.py` with these fields:

```text
event_id: str
run_id: str
event_type: str
agent: str | None
status: str | None
message: str
product: str | None
scenario_id: str | None
artifact_type: str | None
artifact_path: str | None
data: dict[str, Any]
created_at: str
```

Supported `event_type` values:

```text
run_started
run_completed
run_failed
agent_started
agent_finished
agent_blocked
artifact_written
```

Supported `agent` values:

```text
ResearchDirector
ScenarioPlanner
BrowserWalker
EvidenceExtractor
ProductAnalyst
CompetitiveAnalyst
Reviewer
MarkdownReportWriter
Evaluator
```

Artifact events currently use these `artifact_type` values:

```text
evidence_json
report_markdown
evaluation_json
```

`run_id` is derived from `Path(run_dir).name`. For Web runs, pass a run directory named like the Web run id, for example `runs/run-20260616-101500`.

## How to pass an event sink

`ResearchDirector.__init__` now accepts either or both of:

```python
director = ResearchDirector(
    walker=MockBrowserWalker(),
    concurrency=3,
    event_sink=event_bus,
)
```

The sink may expose `emit(event)`, expose `append(event)`, or be directly callable. Sync and async handlers are both supported.

```python
class EventBus:
    async def emit(self, event: RunEvent) -> None:
        payload = event.to_dict()
        ...

director = ResearchDirector(
    walker=MockBrowserWalker(),
    event_callback=lambda event: print(event.to_dict()),
)
```

If neither `event_sink` nor `event_callback` is passed, `director.run(...)` follows the previous CLI path and only writes the existing artifacts.

## Backend API Agent subscription guidance

The Backend API Agent should create a per-run adapter object and pass it as `event_sink` when constructing `ResearchDirector`.

Recommended flow:

1. Create the Web run directory first, using the run id as the directory name.
2. Build an event sink with `emit(event: RunEvent)`.
3. In `emit`, convert with `event.to_dict()`.
4. Append the event to `events.jsonl`.
5. Update in-memory run/agent/artifact state.
6. Broadcast the same payload through the SSE event bus.

The current pipeline events use underscore event names. If the server contract keeps dot-style API names, map them in the backend adapter rather than changing the pipeline output. For example, `run_started` can map to `run.started`, `artifact_written` can map to `artifact.created`, and `agent_finished` can map to `agent.completed`.

## Current event coverage gaps

- No FastAPI/server code was added.
- No frontend code was added.
- No step-by-step browser-use telemetry is emitted yet.
- No `run_created`, `plan_loaded`, `run_finalizing`, cancel, or verification events are emitted yet.
- Screenshot files archived through evidence are not emitted as separate screenshot artifact events.
- Agent exception events are represented by `run_failed`; there is no separate `agent_failed` event in this phase because it was not in the required event set.

## Test commands and results

```text
python -m pytest tests/test_events.py
Result: 4 passed
```

```text
python -m pytest tests/test_mvp_pipeline.py::MvpPipelineTest
Result: 2 passed
```

```text
python -m pytest
Result: 34 passed
```
