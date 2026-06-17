from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, AsyncIterator
from urllib.parse import quote

from prodwalk.agents.director import ResearchDirector
from prodwalk.agents.planner import ScenarioPlanner
from prodwalk.agents.walker import MockBrowserWalker
from prodwalk.config_loader import ConfigError, parse_research_plan
from prodwalk.events import RunEvent as PipelineRunEvent
from prodwalk.models import ResearchPlan, normalize_report_language, to_jsonable, utc_now

from .models import (
    AgentExecution,
    Artifact,
    PlanDetailResponse,
    PlanListResponse,
    PlanSummary,
    Progress,
    RunActionResponse,
    RunDetail,
    RunListResponse,
    RunStartRequest,
    RunStartResponse,
    RunSummary,
)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(slots=True)
class PlanBundle:
    id: str
    name: str
    path: Path | None
    plan: ResearchPlan
    raw: dict[str, Any]


PIPELINE_AGENT_TYPES = {
    "ResearchDirector": "director",
    "ScenarioPlanner": "planner",
    "BrowserWalker": "walker",
    "EvidenceExtractor": "evidence_extractor",
    "ProductAnalyst": "product_analyst",
    "CompetitiveAnalyst": "competitive_analyst",
    "Reviewer": "reviewer",
    "MarkdownReportWriter": "report_writer",
    "Evaluator": "evaluator",
}

PIPELINE_ARTIFACT_IDS = {
    "evidence_json": "art_evidence_json",
    "report_markdown": "art_report_md",
    "evaluation_json": "art_evaluation_json",
}

AGENT_TERMINAL_STATUSES = {"succeeded", "failed", "skipped", "canceled"}
RUN_TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
SENSITIVE_DATA_KEYS = {
    "browser_storage_state",
    "browser_user_data_dir",
    "executable_path",
    "history_file",
    "screenshot",
    "screenshot_path",
    "screenshot_paths",
    "storage_state",
    "user_data_dir",
}


class PipelineEventAdapter:
    def __init__(self, runtime: "RunRuntime", run_id: str, run_dir: Path) -> None:
        self.runtime = runtime
        self.run_id = run_id
        self.run_dir = run_dir
        self.started_at: str | None = None
        self.finalizing_emitted = False
        self.stage_started_emitted = False
        self.terminal_emitted = False

    async def emit(self, event: PipelineRunEvent) -> None:
        if event.event_type == "run_started":
            await self._run_started(event)
        elif event.event_type == "run_completed":
            await self._run_completed(event)
        elif event.event_type == "run_failed":
            await self._run_failed(event)
        elif event.event_type == "agent_started":
            await self._agent_started(event)
        elif event.event_type == "agent_finished":
            await self._agent_finished(event)
        elif event.event_type == "agent_blocked":
            await self._agent_blocked(event)
        elif event.event_type == "artifact_written":
            await self._artifact_written(event)

    async def _run_started(self, event: PipelineRunEvent) -> None:
        self.started_at = event.created_at
        self.runtime._update_run(self.run_id, status="running", started_at=self.started_at)
        self.runtime._upsert_agent(
            self.run_id,
            event.agent or "ResearchDirector",
            "running",
            started_at=self.started_at,
        )
        await self.runtime.append_event(
            self.run_id,
            "run.started",
            event.message or "Run started",
            agent_id=self.runtime._agent_id(event.agent or "ResearchDirector"),
            agent_type=self.runtime._agent_type(event.agent),
            status="running",
            payload=dict(event.data),
        )
        await self._stage_started()

    async def _stage_started(self) -> None:
        if self.stage_started_emitted:
            return
        self.stage_started_emitted = True
        await self.runtime.append_event(
            self.run_id,
            "stage.started",
            "Mock research pipeline started",
            agent_id="agent_director",
            agent_type="director",
            status="running",
        )

    async def _run_completed(self, event: PipelineRunEvent) -> None:
        progress = self.runtime._progress_from_evidence(self.run_dir / "evidence.json")
        artifacts = self.runtime._refresh_artifacts(self.run_id)
        artifact_ids = [artifact["id"] for artifact in artifacts]
        completed_at = event.created_at
        self.runtime._update_run(
            self.run_id,
            status="succeeded",
            completed_at=completed_at,
            progress=progress,
            artifact_ids=artifact_ids,
        )
        self.runtime._upsert_agent(
            self.run_id,
            event.agent or "ResearchDirector",
            "succeeded",
            started_at=self.started_at,
            completed_at=completed_at,
            metrics=dict(event.data),
        )
        await self.runtime.append_event(
            self.run_id,
            "stage.completed",
            "Mock research pipeline completed",
            agent_id="agent_director",
            agent_type="director",
            status="finalizing",
            payload={"progress": progress},
        )
        await self.runtime.append_event(
            self.run_id,
            "run.completed",
            event.message or "Run completed",
            agent_id="agent_director",
            agent_type="director",
            status="succeeded",
            payload=dict(event.data),
            artifact_ids=artifact_ids,
        )
        self.terminal_emitted = True

    async def _run_failed(self, event: PipelineRunEvent) -> None:
        completed_at = event.created_at
        error = {
            "message": event.message or "Run failed",
            "type": event.data.get("error_type"),
            "details": event.data.get("error"),
        }
        self.runtime._update_run(self.run_id, status="failed", completed_at=completed_at, error=error)
        self.runtime._upsert_agent(
            self.run_id,
            event.agent or "ResearchDirector",
            "failed",
            started_at=self.started_at,
            completed_at=completed_at,
            error=error,
        )
        await self.runtime.append_event(
            self.run_id,
            "run.failed",
            event.message or "Run failed",
            level="error",
            agent_id="agent_director",
            agent_type="director",
            status="failed",
            payload=error,
        )
        self.terminal_emitted = True

    async def _agent_started(self, event: PipelineRunEvent) -> None:
        await self._stage_started()
        agent_id = self.runtime._agent_id(event.agent, event.product, event.scenario_id)
        agent_type = self.runtime._agent_type(event.agent)
        self.runtime._upsert_agent(
            self.run_id,
            event.agent,
            "running",
            product=event.product,
            scenario_id=event.scenario_id,
            started_at=event.created_at,
            metrics=self._metrics(event),
        )
        await self.runtime.append_event(
            self.run_id,
            "agent.started",
            event.message or f"{event.agent or 'Agent'} started",
            agent_id=agent_id,
            agent_type=agent_type,
            product=event.product,
            scenario_id=event.scenario_id,
            status="running",
            payload=dict(event.data),
        )

    async def _agent_finished(self, event: PipelineRunEvent) -> None:
        agent_status = self._agent_status(event.status)
        api_event_type = "agent.completed" if agent_status == "succeeded" else "agent.status_changed"
        self.runtime._upsert_agent(
            self.run_id,
            event.agent,
            agent_status,
            product=event.product,
            scenario_id=event.scenario_id,
            completed_at=event.created_at if agent_status in AGENT_TERMINAL_STATUSES else None,
            metrics=self._metrics(event),
        )
        await self.runtime.append_event(
            self.run_id,
            api_event_type,
            event.message or f"{event.agent or 'Agent'} completed",
            agent_id=self.runtime._agent_id(event.agent, event.product, event.scenario_id),
            agent_type=self.runtime._agent_type(event.agent),
            product=event.product,
            scenario_id=event.scenario_id,
            status=agent_status,
            payload=dict(event.data),
        )

    async def _agent_blocked(self, event: PipelineRunEvent) -> None:
        self.runtime._upsert_agent(
            self.run_id,
            event.agent,
            "waiting",
            product=event.product,
            scenario_id=event.scenario_id,
            metrics=self._metrics(event),
        )
        await self.runtime.append_event(
            self.run_id,
            "agent.status_changed",
            event.message or f"{event.agent or 'Agent'} is waiting",
            level="warn",
            agent_id=self.runtime._agent_id(event.agent, event.product, event.scenario_id),
            agent_type=self.runtime._agent_type(event.agent),
            product=event.product,
            scenario_id=event.scenario_id,
            status="waiting",
            payload=dict(event.data),
        )

    async def _artifact_written(self, event: PipelineRunEvent) -> None:
        if not self.finalizing_emitted:
            progress = self.runtime._progress_from_evidence(self.run_dir / "evidence.json")
            self.runtime._update_run(self.run_id, status="finalizing", progress=progress)
            await self.runtime.append_event(
                self.run_id,
                "run.finalizing",
                "Run artifacts are being finalized",
                agent_id="agent_director",
                agent_type="director",
                status="finalizing",
                payload={"progress": progress},
            )
            self.finalizing_emitted = True

        artifacts = self.runtime._refresh_artifacts(self.run_id)
        artifact_id = PIPELINE_ARTIFACT_IDS.get(event.artifact_type or "")
        known_artifact_ids = {artifact["id"] for artifact in artifacts}
        artifact_ids = [artifact_id] if artifact_id in known_artifact_ids else []
        payload = dict(event.data)
        if event.artifact_type:
            payload["artifact_type"] = event.artifact_type
        if event.artifact_path:
            payload["artifact_path"] = self.runtime._relative_path(Path(event.artifact_path))
        await self.runtime.append_event(
            self.run_id,
            "artifact.created",
            event.message or "Artifact created",
            agent_id=self.runtime._agent_id(event.agent),
            agent_type=self.runtime._agent_type(event.agent),
            status="finalizing",
            payload=payload,
            artifact_ids=artifact_ids,
        )
        if artifact_id == "art_report_md":
            await self.runtime.append_event(
                self.run_id,
                "report.generated",
                "Markdown report generated",
                agent_id="agent_report_writer",
                agent_type="report_writer",
                status="finalizing",
                artifact_ids=[artifact_id],
            )
        elif artifact_id == "art_evaluation_json":
            await self.runtime.append_event(
                self.run_id,
                "evaluation.generated",
                "Evaluation generated",
                agent_id="agent_evaluator",
                agent_type="evaluator",
                status="finalizing",
                artifact_ids=[artifact_id],
            )

    def _agent_status(self, status: str | None) -> str:
        if status == "blocked":
            return "waiting"
        if status in {"succeeded", "failed", "skipped", "canceled", "running", "waiting"}:
            return status
        return "succeeded"

    def _metrics(self, event: PipelineRunEvent) -> dict[str, Any]:
        metrics = event.data.get("metrics")
        if isinstance(metrics, dict):
            return dict(metrics)
        return {key: value for key, value in event.data.items() if key.endswith("_count") or key == "step_count"}


class RunRuntime:
    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.examples_dir = self.workspace_root / "examples"
        self._runs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    def list_plans(self) -> PlanListResponse:
        items: list[PlanSummary] = []
        if not self.examples_dir.exists():
            return PlanListResponse(items=items)
        for path in sorted(self.examples_dir.glob("*.json")):
            try:
                raw = self._read_json(path)
                plan = parse_research_plan(raw)
            except Exception:
                continue
            scenarios = ScenarioPlanner().plan(plan)
            rel_path = self._relative_path(path)
            items.append(
                PlanSummary(
                    id=rel_path,
                    name=path.name,
                    path=rel_path,
                    title=plan.research_goal,
                    product_count=len(plan.products),
                    scenario_count=len(scenarios),
                    report_language=plan.report_language,
                )
            )
        return PlanListResponse(items=items)

    def get_plan(self, name: str) -> PlanDetailResponse:
        bundle = self._load_plan_from_name(name)
        assert bundle.path is not None
        rel_path = self._relative_path(bundle.path)
        return PlanDetailResponse(id=rel_path, name=bundle.name, path=rel_path, plan=bundle.raw)

    async def start_run(self, request: RunStartRequest) -> RunStartResponse:
        if request.mode != "mock":
            raise ApiError(400, "BAD_REQUEST", "Only mock mode is supported by the first backend API version.")
        if request.concurrency is not None and request.concurrency < 1:
            raise ApiError(400, "BAD_REQUEST", "concurrency must be greater than or equal to 1.")

        bundle = self._resolve_request_plan(request)
        out_root = self._resolve_output_root(request.out)
        run_id = self._new_run_id()
        run_dir = out_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        created_at = utc_now()
        scenarios = ScenarioPlanner().plan(bundle.plan)
        total_scenarios = len(bundle.plan.products) * len(scenarios)
        try:
            report_language = (
                normalize_report_language(request.report_language)
                if request.report_language
                else bundle.plan.report_language
            )
        except ValueError as exc:
            raise ApiError(400, "BAD_REQUEST", str(exc), {"report_language": request.report_language}) from exc
        params = self._request_params(request, report_language=report_language)
        run = {
            "id": run_id,
            "status": "queued",
            "mode": request.mode,
            "research_goal": bundle.plan.research_goal,
            "run_dir": self._relative_path(run_dir),
            "created_at": created_at,
            "started_at": None,
            "completed_at": None,
            "progress": {
                "total_scenarios": total_scenarios,
                "completed_scenarios": 0,
                "failed_scenarios": 0,
            },
            "params": params,
            "artifact_ids": [],
            "error": None,
        }
        self._write_json(run_dir / "plan.json", bundle.raw)
        self._write_json(run_dir / "run.json", run)
        self._write_json(run_dir / "agents.json", [self._agent(run_id, "pending")])
        self._write_json(run_dir / "artifacts.json", [])
        (run_dir / "events.jsonl").write_text("", encoding="utf-8")

        self._runs[run_id] = {"run": run, "run_dir": run_dir, "last_seq": 0}
        await self.append_event(run_id, "run.created", "Run created", status="queued")
        self._refresh_artifacts(run_id)
        task = asyncio.create_task(self._execute_mock_run(run_id, bundle.plan, run_dir, request))
        self._tasks[run_id] = task

        summary = self._summary_from_record(run)
        return RunStartResponse(
            run_id=run_id,
            status=run["status"],
            created_at=created_at,
            events_url=f"/api/runs/{run_id}/events/stream",
            report_url=f"/api/runs/{run_id}/report",
            evidence_url=f"/api/runs/{run_id}/evidence",
            evaluation_url=f"/api/runs/{run_id}/evaluation",
            run=summary,
        )

    def list_runs(self, limit: int = 50) -> RunListResponse:
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for run_id, state in self._runs.items():
            records.append(dict(state["run"]))
            seen.add(run_id)

        for run_dir in self._scan_run_dirs():
            run_id = run_dir.name
            if run_id in seen:
                continue
            record = self._read_run_record(run_dir)
            if record:
                records.append(record)

        records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return RunListResponse(items=[self._summary_from_record(item) for item in records[:limit]], next_cursor=None)

    def get_run(self, run_id: str) -> RunDetail:
        record = self._record_for_run(run_id)
        return self._detail_from_record(record)

    def ensure_run_exists(self, run_id: str) -> None:
        self._run_dir_for_id(run_id)

    async def cancel_run(self, run_id: str, reason: str | None = None) -> RunActionResponse:
        state = self._state_for_run(run_id)
        current_status = str(state["run"].get("status") or "")
        if current_status in RUN_TERMINAL_STATUSES:
            raise ApiError(
                400,
                "RUN_NOT_CANCELABLE",
                f"Run is not cancelable in status: {current_status}",
                {"run_id": run_id, "status": current_status},
            )

        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()

        completed_at = utc_now()
        payload = {"reason": reason} if reason else {}
        self._update_run(run_id, status="canceled", completed_at=completed_at)
        self._upsert_agent(run_id, "ResearchDirector", "canceled", completed_at=completed_at)
        await self.append_event(
            run_id,
            "run.canceled",
            "Run canceled",
            level="warn",
            agent_id="agent_director",
            agent_type="director",
            status="canceled",
            payload=payload,
        )
        return RunActionResponse(run_id=run_id, status="canceled", accepted=True)

    async def confirm_verification(
        self,
        run_id: str,
        *,
        confirmed: bool,
        note: str | None = None,
    ) -> RunActionResponse:
        state = self._state_for_run(run_id)
        status = str(state["run"].get("status") or "running")
        if confirmed and status == "awaiting_verification":
            status = "running"
            self._update_run(run_id, status=status)
        await self.append_event(
            run_id,
            "agent.status_changed",
            "Manual verification confirmation recorded",
            agent_id="agent_auth_session",
            agent_type="auth_session",
            status=status,
            payload={"confirmed": confirmed, "note": note},
        )
        return RunActionResponse(run_id=run_id, status=status, accepted=True)

    def list_agents(self, run_id: str) -> list[AgentExecution]:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "agents.json"
        if not path.exists():
            return [self._agent(run_id, "succeeded")]
        payload = self._read_json(path)
        if not isinstance(payload, list):
            return []
        return [AgentExecution(**item) for item in payload if isinstance(item, dict)]

    def list_events(self, run_id: str, after_seq: int = 0, limit: int = 100) -> dict[str, Any]:
        events = self._read_events(run_id, after_seq=after_seq, limit=limit)
        last_seq = events[-1]["seq"] if events else after_seq
        return {"items": events, "last_seq": last_seq}

    async def stream_events(self, run_id: str, after_seq: int = 0) -> AsyncIterator[str]:
        self._run_dir_for_id(run_id)
        for event in self._read_events(run_id, after_seq=after_seq, limit=10_000):
            yield self._format_sse_event(event)
        if self._stream_complete_after_replay(run_id):
            return

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(run_id, set()).add(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield self._format_sse_event(event)
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({'time': utc_now()})}\n\n"
        finally:
            subscribers = self._subscribers.get(run_id)
            if subscribers is not None:
                subscribers.discard(queue)

    def _stream_complete_after_replay(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            return False
        try:
            status = str(self._record_for_run(run_id).get("status") or "")
        except ApiError:
            return True
        return status in RUN_TERMINAL_STATUSES

    def list_artifacts(self, run_id: str) -> list[Artifact]:
        run_dir = self._run_dir_for_id(run_id)
        artifacts = self._build_artifacts(run_id, run_dir)
        seen_ids = {str(item.get("id")) for item in artifacts}
        path = run_dir / "artifacts.json"
        if path.exists():
            try:
                payload = self._read_json(path)
            except Exception:
                payload = []
            if isinstance(payload, list):
                for item in payload:
                    artifact = self._validated_persisted_artifact(run_id, run_dir, item)
                    if artifact is None or artifact["id"] in seen_ids:
                        continue
                    artifacts.append(artifact)
                    seen_ids.add(artifact["id"])
        return [Artifact(**item) for item in artifacts]

    def find_artifact(self, run_id: str, artifact_id: str) -> Artifact | None:
        for artifact in self.list_artifacts(run_id):
            if artifact.id == artifact_id:
                return artifact
        return None

    def get_artifact(self, run_id: str, artifact_id: str) -> Artifact:
        artifact = self.find_artifact(run_id, artifact_id)
        if artifact is not None:
            return artifact
        raise ApiError(404, "ARTIFACT_NOT_FOUND", f"Artifact not found: {artifact_id}", {"artifact_id": artifact_id})

    def artifact_path(self, run_id: str, artifact_id: str) -> Path:
        run_dir = self._run_dir_for_id(run_id)
        artifact = self.get_artifact(run_id, artifact_id)
        path = self._resolve_run_relative_path(run_dir, artifact.path)
        if not path.exists():
            raise ApiError(404, "ARTIFACT_NOT_FOUND", f"Artifact file is missing: {artifact.path}")
        return path

    def artifact_file(self, run_id: str, artifact_path: str) -> tuple[Path, str]:
        run_dir = self._run_dir_for_id(run_id)
        path = self._resolve_run_relative_path(run_dir, artifact_path)
        if not path.exists() or not path.is_file():
            raise ApiError(
                404,
                "ARTIFACT_NOT_FOUND",
                f"Artifact file is missing: {artifact_path}",
                {"path": artifact_path},
            )
        rel_path = path.relative_to(run_dir.resolve()).as_posix()
        artifact = next((item for item in self.list_artifacts(run_id) if item.path == rel_path), None)
        return path, artifact.media_type if artifact is not None else self._media_type_for_path(path)

    def screenshot_file(self, run_id: str, filename: str) -> tuple[Path, str]:
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or filename in {".", ".."}
            or ":" in filename
        ):
            raise ApiError(403, "ARTIFACT_FORBIDDEN", "Screenshot filename is not allowed.", {"filename": filename})
        run_dir = self._run_dir_for_id(run_id)
        screenshots_dir = (run_dir / "screenshots").resolve()
        path = (screenshots_dir / filename).resolve()
        if not path.is_relative_to(screenshots_dir) or not path.is_relative_to(run_dir.resolve()):
            raise ApiError(403, "ARTIFACT_FORBIDDEN", "Screenshot path is outside the run directory.")
        media_type = IMAGE_MEDIA_TYPES.get(path.suffix.lower())
        if media_type is None or not path.exists() or not path.is_file():
            raise ApiError(
                404,
                "ARTIFACT_NOT_FOUND",
                f"Screenshot file is missing: {filename}",
                {"filename": filename},
            )
        return path, media_type

    def read_report(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "report.md"
        if not path.exists():
            raise ApiError(404, "ARTIFACT_NOT_FOUND", "report.md is not available yet.", {"run_id": run_id})
        evaluation = None
        evaluation_path = run_dir / "evaluation.json"
        if evaluation_path.exists():
            evaluation = self._read_json(evaluation_path)
        return {
            "run_id": run_id,
            "language": self._record_for_run(run_id).get("params", {}).get("report_language"),
            "markdown_artifact_id": "art_report_md",
            "evaluation_artifact_id": "art_evaluation_json" if evaluation_path.exists() else None,
            "markdown": path.read_text(encoding="utf-8"),
            "evaluation": evaluation,
            "generated_at": self._mtime_iso(path),
        }

    def read_evidence(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "evidence.json"
        if not path.exists():
            raise ApiError(404, "ARTIFACT_NOT_FOUND", "evidence.json is not available yet.", {"run_id": run_id})
        payload = self._read_json(path)
        artifacts = self._build_artifacts(run_id, run_dir)
        screenshot_map = self._screenshot_artifact_map(run_dir, artifacts)
        raw_results = payload.get("results", [])
        raw_evidence = payload.get("evidence", [])
        evidence_context = self._evidence_context(raw_results)
        return {
            "run_id": run_id,
            "artifact_id": "art_evidence_json",
            "created_at": payload.get("created_at"),
            "report_language": payload.get("report_language"),
            "results": self._normalize_results(raw_results, screenshot_map),
            "evidence": self._normalize_evidence_items(raw_evidence, evidence_context, screenshot_map),
            "plan": payload.get("plan"),
            "scenarios": payload.get("scenarios", []),
        }

    def read_evidence_item(self, run_id: str, evidence_id: str) -> dict[str, Any]:
        payload = self.read_evidence(run_id)
        for item in payload["evidence"]:
            if item.get("id") == evidence_id:
                return {
                    "run_id": run_id,
                    "artifact_id": payload["artifact_id"],
                    "evidence": item,
                }
        raise ApiError(
            404,
            "ARTIFACT_NOT_FOUND",
            f"Evidence item not found: {evidence_id}",
            {"run_id": run_id, "evidence_id": evidence_id},
        )

    def read_evaluation(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "evaluation.json"
        if not path.exists():
            raise ApiError(404, "ARTIFACT_NOT_FOUND", "evaluation.json is not available yet.", {"run_id": run_id})
        payload = self._read_json(path)
        return {"run_id": run_id, "artifact_id": "art_evaluation_json", **payload}

    def _normalize_results(
        self,
        raw_results: Any,
        screenshot_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_results, list):
            return []
        results: list[dict[str, Any]] = []
        for result in raw_results:
            if not isinstance(result, dict):
                continue
            steps: list[dict[str, Any]] = []
            raw_steps = result.get("steps")
            if not isinstance(raw_steps, list):
                raw_steps = []
            for step in raw_steps:
                if not isinstance(step, dict):
                    continue
                steps.append(
                    {
                        "index": step.get("index"),
                        "action": step.get("action"),
                        "status": step.get("status"),
                        "observation": step.get("observation"),
                        "url": step.get("url"),
                        "elapsed_ms": step.get("elapsed_ms", 0),
                        "evidence_ids": step.get("evidence_ids", []),
                        "screenshot_artifact_id": self._screenshot_artifact_id(
                            step.get("screenshot"),
                            screenshot_map,
                        ),
                    }
                )
            results.append(
                {
                    "product": result.get("product"),
                    "product_kind": result.get("product_kind"),
                    "scenario_id": result.get("scenario_id"),
                    "scenario_title": result.get("scenario_title"),
                    "status": result.get("status"),
                    "started_at": result.get("started_at"),
                    "completed_at": result.get("completed_at"),
                    "steps": steps,
                    "metrics": result.get("metrics", {}),
                    "errors": result.get("errors", []),
                }
            )
        return results

    def _normalize_evidence_items(
        self,
        raw_evidence: Any,
        context_by_id: dict[str, dict[str, Any]],
        screenshot_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_evidence, list):
            return []
        items: list[dict[str, Any]] = []
        for item in raw_evidence:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            context = context_by_id.get(item_id, {})
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            screenshot_artifact_id = self._screenshot_artifact_id(item.get("screenshot"), screenshot_map)
            if screenshot_artifact_id is None:
                screenshot_artifact_id = self._screenshot_artifact_id(data.get("screenshot_path"), screenshot_map)
            if screenshot_artifact_id is None:
                screenshot_paths = data.get("screenshot_paths")
                if isinstance(screenshot_paths, list):
                    for screenshot_path in screenshot_paths:
                        screenshot_artifact_id = self._screenshot_artifact_id(screenshot_path, screenshot_map)
                        if screenshot_artifact_id:
                            break

            errors = data.get("errors")
            if not isinstance(errors, list):
                errors = context.get("errors", [])

            items.append(
                {
                    "id": item_id,
                    "product": item.get("product"),
                    "product_kind": context.get("product_kind"),
                    "scenario_id": item.get("scenario_id"),
                    "scenario_title": context.get("scenario_title"),
                    "kind": item.get("kind"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "url": item.get("url"),
                    "status": data.get("status") or context.get("status"),
                    "step_index": context.get("step_index"),
                    "action": data.get("action") or context.get("action"),
                    "screenshot_artifact_id": screenshot_artifact_id,
                    "confidence": item.get("confidence"),
                    "created_at": item.get("created_at"),
                    "errors": errors,
                    "final_output": data.get("final_output") if isinstance(data.get("final_output"), str) else None,
                    "data": self._sanitize_evidence_data(data),
                }
            )
        return items

    def _evidence_context(self, raw_results: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(raw_results, list):
            return {}
        context: dict[str, dict[str, Any]] = {}
        for result in raw_results:
            if not isinstance(result, dict):
                continue
            result_context = {
                "product_kind": result.get("product_kind"),
                "scenario_title": result.get("scenario_title"),
                "status": result.get("status"),
                "errors": result.get("errors", []),
            }
            raw_steps = result.get("steps")
            if not isinstance(raw_steps, list):
                raw_steps = []
            for step in raw_steps:
                if not isinstance(step, dict):
                    continue
                step_context = {
                    **result_context,
                    "step_index": step.get("index"),
                    "action": step.get("action"),
                    "status": step.get("status") or result_context["status"],
                }
                for evidence_id in step.get("evidence_ids", []):
                    if evidence_id:
                        context[str(evidence_id)] = step_context
            raw_evidence = result.get("evidence")
            if not isinstance(raw_evidence, list):
                raw_evidence = []
            for item in raw_evidence:
                if isinstance(item, dict) and item.get("id") and str(item.get("id")) not in context:
                    context[str(item["id"])] = result_context
        return context

    def _sanitize_evidence_data(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._sanitize_evidence_data(item) for item in value]
        if not isinstance(value, dict):
            return value

        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_DATA_KEYS:
                continue
            if any(marker in lowered for marker in ("secret", "token", "credential", "password", "api_key")):
                sanitized[key_text] = "<redacted>"
                continue
            sanitized[key_text] = self._sanitize_evidence_data(item)
        return sanitized

    def _screenshot_artifact_map(self, run_dir: Path, artifacts: list[dict[str, Any]]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        root = run_dir.resolve()
        for artifact in artifacts:
            if artifact.get("type") != "screenshot":
                continue
            artifact_id = str(artifact.get("id") or "")
            rel_path = str(artifact.get("path") or "").replace("\\", "/")
            if not artifact_id or not rel_path:
                continue
            mapping[rel_path] = artifact_id
            mapping[Path(rel_path).name] = artifact_id
            abs_path = (root / rel_path).resolve()
            mapping[str(abs_path)] = artifact_id
            mapping[str(abs_path).replace("\\", "/")] = artifact_id
        return mapping

    def _screenshot_artifact_id(self, ref: Any, screenshot_map: dict[str, str]) -> str | None:
        if not isinstance(ref, str) or not ref.strip():
            return None
        normalized = ref.strip().replace("\\", "/")
        if normalized in screenshot_map:
            return screenshot_map[normalized]
        name = PurePosixPath(normalized).name
        if name in screenshot_map:
            return screenshot_map[name]
        return None

    async def append_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        *,
        level: str = "info",
        agent_id: str | None = None,
        agent_type: str | None = None,
        product: str | None = None,
        scenario_id: str | None = None,
        step_index: int | None = None,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
        artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            state = self._state_for_run(run_id)
            seq = int(state.get("last_seq") or self._last_event_seq(state["run_dir"])) + 1
            event = {
                "id": f"evt_{seq:06d}",
                "run_id": run_id,
                "seq": seq,
                "ts": utc_now(),
                "type": event_type,
                "level": level,
                "message": message,
                "agent_id": agent_id,
                "agent_type": agent_type,
                "product": product,
                "scenario_id": scenario_id,
                "step_index": step_index,
                "status": status,
                "payload": payload or {},
                "artifact_ids": artifact_ids or [],
            }
            events_path = state["run_dir"] / "events.jsonl"
            with events_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
            state["last_seq"] = seq

        for queue in list(self._subscribers.get(run_id, set())):
            queue.put_nowait(event)
        return event

    async def _execute_mock_run(
        self,
        run_id: str,
        plan: ResearchPlan,
        run_dir: Path,
        request: RunStartRequest,
    ) -> None:
        adapter = PipelineEventAdapter(self, run_id, run_dir)
        try:
            report_language = request.report_language or plan.report_language
            director = ResearchDirector(
                walker=MockBrowserWalker(),
                concurrency=request.concurrency or 3,
                report_language=report_language,
                event_sink=adapter,
            )
            await director.run(plan, run_dir)
            if not adapter.terminal_emitted:
                progress = self._progress_from_evidence(run_dir / "evidence.json")
                artifacts = self._refresh_artifacts(run_id)
                artifact_ids = [artifact["id"] for artifact in artifacts]
                completed_at = utc_now()
                self._update_run(
                    run_id,
                    status="succeeded",
                    completed_at=completed_at,
                    progress=progress,
                    artifact_ids=artifact_ids,
                )
                self._upsert_agent(
                    run_id,
                    "ResearchDirector",
                    "succeeded",
                    started_at=adapter.started_at,
                    completed_at=completed_at,
                )
                await self.append_event(run_id, "run.completed", "Run completed", status="succeeded")
        except Exception as exc:  # noqa: BLE001 - surfaced through run status and events.
            if not adapter.terminal_emitted:
                completed_at = utc_now()
                error = {"message": str(exc), "type": type(exc).__name__}
                self._update_run(run_id, status="failed", completed_at=completed_at, error=error)
                self._upsert_agent(run_id, "ResearchDirector", "failed", completed_at=completed_at, error=error)
                await self.append_event(
                    run_id,
                    "run.failed",
                    f"Run failed: {exc}",
                    level="error",
                    status="failed",
                    payload=error,
                )

    def _resolve_request_plan(self, request: RunStartRequest) -> PlanBundle:
        inline = request.plan or (request.config if isinstance(request.config, dict) else None)
        identifiers = [
            request.plan_name,
            request.config_path,
            request.config if isinstance(request.config, str) else None,
        ]
        provided = [item for item in identifiers if item]
        if inline and provided:
            raise ApiError(400, "BAD_REQUEST", "Pass either an inline plan/config or a local plan name, not both.")
        if len(provided) > 1:
            raise ApiError(400, "BAD_REQUEST", "Pass only one of plan_name, config_path, or config path.")
        if inline:
            try:
                plan = parse_research_plan(inline)
            except ConfigError as exc:
                raise ApiError(400, "PLAN_INVALID", str(exc)) from exc
            return PlanBundle(id="inline", name="inline", path=None, plan=plan, raw=inline)
        if not provided:
            raise ApiError(400, "BAD_REQUEST", "config, config_path, plan_name, or plan is required.")
        return self._load_plan_from_name(str(provided[0]))

    def _load_plan_from_name(self, name: str) -> PlanBundle:
        path = self._resolve_plan_path(name)
        if not path.exists():
            raise ApiError(404, "PLAN_NOT_FOUND", f"Plan not found: {name}", {"plan": name})
        try:
            raw = self._read_json(path)
            if not isinstance(raw, dict):
                raise ConfigError("Plan JSON must be an object")
            plan = parse_research_plan(raw)
        except ConfigError as exc:
            raise ApiError(400, "PLAN_INVALID", str(exc), {"plan": self._relative_path(path)}) from exc
        except json.JSONDecodeError as exc:
            raise ApiError(400, "PLAN_INVALID", f"Plan JSON is invalid: {exc}", {"plan": self._relative_path(path)}) from exc
        return PlanBundle(id=self._relative_path(path), name=path.name, path=path, plan=plan, raw=raw)

    def _resolve_plan_path(self, name: str) -> Path:
        if not name or "\\" in name:
            raise ApiError(400, "BAD_REQUEST", "Plan name is invalid.", {"plan": name})
        parsed = PurePosixPath(name)
        parts = parsed.parts
        if any(part in {"", ".", ".."} for part in parts) or parsed.is_absolute():
            raise ApiError(400, "BAD_REQUEST", "Plan path traversal is not allowed.", {"plan": name})
        if parts and parts[0] == "examples":
            parts = parts[1:]
        if len(parts) != 1:
            raise ApiError(400, "BAD_REQUEST", "Only plans directly under examples/ are supported.", {"plan": name})
        filename = parts[0]
        if not filename.endswith(".json"):
            filename = f"{filename}.json"
        path = (self.examples_dir / filename).resolve()
        if not path.is_relative_to(self.examples_dir.resolve()):
            raise ApiError(400, "BAD_REQUEST", "Plan path traversal is not allowed.", {"plan": name})
        return path

    def _resolve_output_root(self, out: str | None) -> Path:
        raw = out or "runs"
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.workspace_root / path
        resolved = path.resolve()
        if not resolved.is_relative_to(self.workspace_root):
            raise ApiError(400, "BAD_REQUEST", "out must stay inside the prodwalk workspace.", {"out": raw})
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def _new_run_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"run-{timestamp}-{uuid.uuid4().hex[:6]}"

    def _request_params(self, request: RunStartRequest, *, report_language: str) -> dict[str, Any]:
        return {
            "mode": request.mode,
            "concurrency": request.concurrency or 3,
            "report_language": report_language,
            "browser_model": request.browser_model,
            "browser_max_steps": request.browser_max_steps,
            "browser_timeout_sec": request.browser_timeout_sec,
            "verification_mode": request.verification_mode,
            "verification_timeout_sec": request.verification_timeout_sec,
            "verification_success_url_contains": request.verification_success_url_contains,
            "verification_login_url_contains": request.verification_login_url_contains,
        }

    def _scan_run_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        for root in sorted(self.workspace_root.glob("runs*")):
            if not root.is_dir():
                continue
            dirs.extend(path for path in root.iterdir() if path.is_dir() and path.name.startswith("run-"))
        return dirs

    def _run_dir_for_id(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        state = self._runs.get(run_id)
        if state:
            return Path(state["run_dir"]).resolve()
        for run_dir in self._scan_run_dirs():
            if run_dir.name == run_id:
                return run_dir.resolve()
        raise ApiError(404, "RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id})

    def _record_for_run(self, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        state = self._runs.get(run_id)
        if state:
            return dict(state["run"])
        run_dir = self._run_dir_for_id(run_id)
        record = self._read_run_record(run_dir)
        if not record:
            raise ApiError(404, "RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id})
        return record

    def _state_for_run(self, run_id: str) -> dict[str, Any]:
        state = self._runs.get(run_id)
        if state:
            return state
        run_dir = self._run_dir_for_id(run_id)
        record = self._read_run_record(run_dir)
        if not record:
            raise ApiError(404, "RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id})
        state = {"run": record, "run_dir": run_dir, "last_seq": self._last_event_seq(run_dir)}
        self._runs[run_id] = state
        return state

    def _read_run_record(self, run_dir: Path) -> dict[str, Any] | None:
        manifest = run_dir / "run.json"
        if manifest.exists():
            try:
                payload = self._read_json(manifest)
                if isinstance(payload, dict):
                    payload = dict(payload)
                    payload["id"] = run_dir.name
                    payload["run_dir"] = self._relative_path(run_dir)
                    return payload
            except Exception:
                return None
        return self._infer_run_record(run_dir)

    def _infer_run_record(self, run_dir: Path) -> dict[str, Any] | None:
        artifact_paths = [run_dir / "evidence.json", run_dir / "report.md", run_dir / "evaluation.json"]
        if not any(path.exists() for path in artifact_paths):
            return None
        evidence: dict[str, Any] = {}
        if (run_dir / "evidence.json").exists():
            try:
                evidence = self._read_json(run_dir / "evidence.json")
            except Exception:
                evidence = {}
        results = evidence.get("results") if isinstance(evidence.get("results"), list) else []
        completed = sum(1 for result in results if isinstance(result, dict) and result.get("status") == "completed")
        failed = sum(1 for result in results if isinstance(result, dict) and result.get("status") not in {None, "completed"})
        created_at = evidence.get("created_at") or self._mtime_iso(next(path for path in artifact_paths if path.exists()))
        return {
            "id": run_dir.name,
            "status": "succeeded" if all(path.exists() for path in artifact_paths) else "failed",
            "mode": "unknown",
            "research_goal": evidence.get("plan", {}).get("research_goal", "Historical prodwalk run"),
            "run_dir": self._relative_path(run_dir),
            "created_at": created_at,
            "started_at": None,
            "completed_at": max((self._mtime_iso(path) for path in artifact_paths if path.exists()), default=created_at),
            "progress": {
                "total_scenarios": len(results),
                "completed_scenarios": completed,
                "failed_scenarios": failed,
            },
            "params": {"mode": "unknown", "report_language": evidence.get("report_language")},
            "artifact_ids": [artifact["id"] for artifact in self._build_artifacts(run_dir.name, run_dir)],
            "error": None,
        }

    def _summary_from_record(self, record: dict[str, Any]) -> RunSummary:
        run_id = record["id"]
        availability = self._artifact_availability(run_id)
        return RunSummary(
            id=run_id,
            run_id=run_id,
            status=record.get("status", "failed"),
            mode=record.get("mode", "unknown"),
            research_goal=record.get("research_goal", ""),
            run_dir=record.get("run_dir", ""),
            created_at=record.get("created_at", ""),
            started_at=record.get("started_at"),
            completed_at=record.get("completed_at"),
            progress=Progress(**record.get("progress", {})),
            report_exists=availability["report_exists"],
            evidence_exists=availability["evidence_exists"],
            evaluation_exists=availability["evaluation_exists"],
            screenshot_count=availability["screenshot_count"],
        )

    def _detail_from_record(self, record: dict[str, Any]) -> RunDetail:
        summary = self._summary_from_record(record)
        summary_data = summary.model_dump() if hasattr(summary, "model_dump") else summary.dict()
        return RunDetail(
            **summary_data,
            params=record.get("params", {}),
            artifact_ids=record.get("artifact_ids", []),
            error=record.get("error"),
        )

    def _update_run(self, run_id: str, **updates: Any) -> None:
        state = self._state_for_run(run_id)
        run = state["run"]
        run.update(updates)
        self._write_json(state["run_dir"] / "run.json", run)

    def _agent(
        self,
        run_id: str,
        status: str,
        *,
        started_at: str | None = None,
        completed_at: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": "agent_director",
            "run_id": run_id,
            "type": "director",
            "status": status,
            "label": "ResearchDirector",
            "product": None,
            "scenario_id": None,
            "current_step": None,
            "started_at": started_at,
            "updated_at": completed_at or started_at,
            "completed_at": completed_at,
            "metrics": {},
            "error": error,
        }

    def _upsert_agent(
        self,
        run_id: str,
        agent: str | None,
        status: str,
        *,
        product: str | None = None,
        scenario_id: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        metrics: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "agents.json"
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                payload = self._read_json(path)
            except Exception:
                payload = []
            if isinstance(payload, list):
                existing = [item for item in payload if isinstance(item, dict)]

        agent_id = self._agent_id(agent, product, scenario_id)
        now = completed_at or started_at or utc_now()
        agent_status = self._agent_status(status)
        for item in existing:
            if item.get("id") != agent_id:
                continue
            item.update(
                {
                    "status": agent_status,
                    "updated_at": now,
                    "completed_at": completed_at if agent_status in AGENT_TERMINAL_STATUSES else item.get("completed_at"),
                    "metrics": metrics or item.get("metrics", {}),
                    "error": error,
                }
            )
            if started_at and not item.get("started_at"):
                item["started_at"] = started_at
            self._write_json(path, existing)
            return

        existing.append(
            {
                "id": agent_id,
                "run_id": run_id,
                "type": self._agent_type(agent) or "director",
                "status": agent_status,
                "label": self._agent_label(agent, product, scenario_id),
                "product": product,
                "scenario_id": scenario_id,
                "current_step": None,
                "started_at": started_at,
                "updated_at": now,
                "completed_at": completed_at if agent_status in AGENT_TERMINAL_STATUSES else None,
                "metrics": metrics or {},
                "error": error,
            }
        )
        self._write_json(path, existing)

    def _agent_status(self, status: str) -> str:
        if status == "blocked":
            return "waiting"
        if status in {"pending", "running", "waiting", "succeeded", "failed", "skipped", "canceled"}:
            return status
        return "succeeded"

    def _agent_type(self, agent: str | None) -> str | None:
        if agent is None:
            return None
        return PIPELINE_AGENT_TYPES.get(agent)

    def _agent_id(
        self,
        agent: str | None,
        product: str | None = None,
        scenario_id: str | None = None,
    ) -> str:
        agent_type = self._agent_type(agent) or "agent"
        if agent_type == "walker" and (product or scenario_id):
            return f"agent_walker_{self._slug(product or 'product')}_{self._slug(scenario_id or 'scenario')}"
        return f"agent_{agent_type}"

    def _agent_label(
        self,
        agent: str | None,
        product: str | None = None,
        scenario_id: str | None = None,
    ) -> str:
        label = agent or "Agent"
        if product or scenario_id:
            return f"{label}: {product or 'unknown product'} / {scenario_id or 'unknown scenario'}"
        return label

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
        return slug or "item"

    def _progress_from_evidence(self, path: Path) -> dict[str, int]:
        if not path.exists():
            return {"total_scenarios": 0, "completed_scenarios": 0, "failed_scenarios": 0}
        try:
            payload = self._read_json(path)
        except Exception:
            return {"total_scenarios": 0, "completed_scenarios": 0, "failed_scenarios": 0}
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        return {
            "total_scenarios": len(results),
            "completed_scenarios": sum(
                1 for result in results if isinstance(result, dict) and result.get("status") == "completed"
            ),
            "failed_scenarios": sum(
                1 for result in results if isinstance(result, dict) and result.get("status") != "completed"
            ),
        }

    def _refresh_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        run_dir = self._run_dir_for_id(run_id)
        artifacts = self._build_artifacts(run_id, run_dir)
        self._write_json(run_dir / "artifacts.json", artifacts)
        state = self._runs.get(run_id)
        if state:
            state["run"]["artifact_ids"] = [artifact["id"] for artifact in artifacts]
            self._write_json(run_dir / "run.json", state["run"])
        return artifacts

    def _build_artifacts(self, run_id: str, run_dir: Path) -> list[dict[str, Any]]:
        specs = [
            ("art_run_manifest", "run_manifest", "run.json", "run.json", "application/json"),
            ("art_plan_json", "plan_json", "plan.json", "plan.json", "application/json"),
            ("art_events_jsonl", "events_jsonl", "events.jsonl", "events.jsonl", "application/x-ndjson"),
            ("art_agents_json", "agents_json", "agents.json", "agents.json", "application/json"),
            ("art_artifacts_json", "artifacts_json", "artifacts.json", "artifacts.json", "application/json"),
            ("art_evidence_json", "evidence_json", "evidence.json", "evidence.json", "application/json"),
            ("art_report_md", "report_markdown", "report.md", "report.md", "text/markdown; charset=utf-8"),
            ("art_evaluation_json", "evaluation_json", "evaluation.json", "evaluation.json", "application/json"),
        ]
        artifacts: list[dict[str, Any]] = []
        for artifact_id, artifact_type, title, rel_path, media_type in specs:
            path = run_dir / rel_path
            if not path.exists():
                continue
            artifacts.append(
                {
                    "id": artifact_id,
                    "run_id": run_id,
                    "type": artifact_type,
                    "title": title,
                    "path": rel_path,
                    "media_type": media_type,
                    "size_bytes": path.stat().st_size,
                    "created_at": self._mtime_iso(path),
                    "metadata": {
                        "content_url": f"/api/runs/{run_id}/artifacts/{artifact_id}/content",
                        "path_url": f"/api/runs/{run_id}/artifacts/{quote(rel_path, safe='/')}",
                    },
                }
            )
        screenshots_dir = run_dir / "screenshots"
        if screenshots_dir.exists():
            for path in sorted(screenshots_dir.rglob("*")):
                if not path.is_file():
                    continue
                media_type = IMAGE_MEDIA_TYPES.get(path.suffix.lower())
                if media_type is None:
                    continue
                resolved = path.resolve()
                run_root = run_dir.resolve()
                if not resolved.is_relative_to(run_root):
                    continue
                rel_path = resolved.relative_to(run_root).as_posix()
                artifacts.append(
                    {
                        "id": self._artifact_id_for_path("art_screenshot", rel_path),
                        "run_id": run_id,
                        "type": "screenshot",
                        "title": path.name,
                        "path": rel_path,
                        "media_type": media_type,
                        "size_bytes": path.stat().st_size,
                        "created_at": self._mtime_iso(path),
                        "metadata": {
                            "content_url": (
                                f"/api/runs/{run_id}/artifacts/"
                                f"{self._artifact_id_for_path('art_screenshot', rel_path)}/content"
                            ),
                            "path_url": f"/api/runs/{run_id}/artifacts/{quote(rel_path, safe='/')}",
                            "screenshot_url": f"/api/runs/{run_id}/screenshots/{quote(path.name)}",
                        },
                    }
                )
        return artifacts

    def _validated_persisted_artifact(
        self,
        run_id: str,
        run_dir: Path,
        item: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        artifact_id = item.get("id")
        rel_path = item.get("path")
        if not isinstance(artifact_id, str) or not artifact_id:
            return None
        if not isinstance(rel_path, str) or not rel_path:
            return None
        try:
            path = self._resolve_run_relative_path(run_dir, rel_path)
        except ApiError:
            return None
        if not path.exists() or not path.is_file():
            return None
        run_root = run_dir.resolve()
        normalized_path = path.relative_to(run_root).as_posix()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata = {
            **metadata,
            "content_url": f"/api/runs/{run_id}/artifacts/{quote(artifact_id)}/content",
            "path_url": f"/api/runs/{run_id}/artifacts/{quote(normalized_path, safe='/')}",
        }
        return {
            "id": artifact_id,
            "run_id": run_id,
            "type": str(item.get("type") or "log_text"),
            "title": str(item.get("title") or Path(normalized_path).name),
            "path": normalized_path,
            "media_type": str(item.get("media_type") or self._media_type_for_path(path)),
            "size_bytes": path.stat().st_size,
            "created_at": str(item.get("created_at") or self._mtime_iso(path)),
            "metadata": metadata,
        }

    def _resolve_run_relative_path(self, run_dir: Path, artifact_path: str) -> Path:
        if not artifact_path or "\\" in artifact_path:
            raise ApiError(
                403,
                "ARTIFACT_FORBIDDEN",
                "Artifact path must be a relative path inside the run directory.",
                {"path": artifact_path},
            )
        parsed = PurePosixPath(artifact_path)
        parts = parsed.parts
        if parsed.is_absolute() or not parts or any(part in {"", ".", ".."} or ":" in part for part in parts):
            raise ApiError(
                403,
                "ARTIFACT_FORBIDDEN",
                "Artifact path must be a relative path inside the run directory.",
                {"path": artifact_path},
            )
        run_root = run_dir.resolve()
        path = run_root.joinpath(*parts).resolve()
        if not path.is_relative_to(run_root):
            raise ApiError(403, "ARTIFACT_FORBIDDEN", "Artifact path is outside the run directory.")
        return path

    def _media_type_for_path(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in IMAGE_MEDIA_TYPES:
            return IMAGE_MEDIA_TYPES[suffix]
        if suffix == ".md":
            return "text/markdown; charset=utf-8"
        if suffix == ".json":
            return "application/json"
        if suffix == ".jsonl":
            return "application/x-ndjson"
        if suffix in {".log", ".txt"}:
            return "text/plain; charset=utf-8"
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or "application/octet-stream"

    def _artifact_availability(self, run_id: str) -> dict[str, Any]:
        try:
            run_dir = self._run_dir_for_id(run_id)
        except ApiError:
            return {
                "report_exists": False,
                "evidence_exists": False,
                "evaluation_exists": False,
                "screenshot_count": 0,
            }
        screenshots_dir = run_dir / "screenshots"
        screenshot_count = 0
        if screenshots_dir.exists():
            screenshot_count = sum(
                1
                for path in screenshots_dir.rglob("*")
                if path.is_file() and IMAGE_MEDIA_TYPES.get(path.suffix.lower()) is not None
            )
        return {
            "report_exists": (run_dir / "report.md").is_file(),
            "evidence_exists": (run_dir / "evidence.json").is_file(),
            "evaluation_exists": (run_dir / "evaluation.json").is_file(),
            "screenshot_count": screenshot_count,
        }

    def _artifact_id_for_path(self, prefix: str, rel_path: str) -> str:
        digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:8]
        slug = self._slug(Path(rel_path).stem)
        return f"{prefix}_{slug}_{digest}"

    def _read_events(self, run_id: str, *, after_seq: int, limit: int) -> list[dict[str, Any]]:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "events.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(event.get("seq", 0)) > after_seq:
                    events.append(event)
                if len(events) >= limit:
                    break
        return events

    def _last_event_seq(self, run_dir: Path) -> int:
        path = run_dir / "events.jsonl"
        if not path.exists():
            return 0
        last_seq = 0
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    last_seq = int(json.loads(line).get("seq", last_seq))
                except Exception:
                    continue
        return last_seq

    def _format_sse_event(self, event: dict[str, Any]) -> str:
        return f"id: {event['seq']}\nevent: run.event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    def _validate_run_id(self, run_id: str) -> None:
        if not re.fullmatch(r"run-[A-Za-z0-9_.-]+", run_id or ""):
            raise ApiError(404, "RUN_NOT_FOUND", f"Run not found: {run_id}", {"run_id": run_id})

    def _read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(to_jsonable(payload), indent=2, ensure_ascii=False), encoding="utf-8")

    def _relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.workspace_root).as_posix()
        except ValueError:
            return resolved.as_posix()

    def _mtime_iso(self, path: Path) -> str:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
