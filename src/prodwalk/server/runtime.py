from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, AsyncIterator
from urllib.parse import quote, urlparse, urlunparse

from prodwalk.auth_session import (
    AuthSessionRequest as ManualAuthSessionRequest,
    ManualAuthSession,
    close_manual_auth_session,
    complete_manual_auth_session,
    open_manual_auth_session,
)
from prodwalk.agents.director import ResearchDirector
from prodwalk.agents.map_builder import BUILD_VERSION as WALKTHROUGH_MAP_BUILD_VERSION
from prodwalk.agents.map_builder import WALKTHROUGH_MAP_ARTIFACT_ID, build_walkthrough_map
from prodwalk.agents.planner import ScenarioPlanner
from prodwalk.agents.walker import (
    DEFAULT_DISCOVER_ALL_PAGES,
    DEFAULT_DISCOVERY_MAX_DEPTH,
    DEFAULT_DISCOVERY_MAX_PAGES,
    BrowserUseLocalWalker,
    BrowserWalker,
    MockBrowserWalker,
)
from prodwalk.config_loader import ConfigError, parse_research_plan
from prodwalk.credentials import normalize_ref
from prodwalk.events import RunEvent as PipelineRunEvent
from prodwalk.models import ResearchPlan, normalize_report_language, slugify, to_jsonable, utc_now

from .models import (
    AgentExecution,
    Artifact,
    AuthSessionCreateRequest,
    AuthSessionDetail,
    PlanDetailResponse,
    PlanListResponse,
    PlanSummary,
    Progress,
    RetryAfterVerificationRequest,
    RetryAfterVerificationResponse,
    RunActionResponse,
    RunClearResponse,
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


@dataclass(slots=True)
class RunExecutionOptions:
    mode: str
    concurrency: int
    report_language: str
    browser_user_data_dir: str | None = None
    browser_storage_state: str | None = None
    auth_session_id: str | None = None
    verification_mode: str = "off"


PIPELINE_AGENT_TYPES = {
    "ResearchDirector": "director",
    "ScenarioPlanner": "planner",
    "BrowserWalker": "walker",
    "AuthSession": "auth_session",
    "EvidenceExtractor": "evidence_extractor",
    "ProductAnalyst": "product_analyst",
    "CompetitiveAnalyst": "competitive_analyst",
    "Reviewer": "reviewer",
    "MarkdownReportWriter": "report_writer",
    "Evaluator": "evaluator",
}

PIPELINE_ARTIFACT_IDS = {
    "evidence_json": "art_evidence_json",
    "issues_json": "art_issues_json",
    "report_markdown": "art_report_md",
    "evaluation_json": "art_evaluation_json",
}

PIPELINE_STAGE_LABELS = {
    "ResearchDirector": "Research orchestration",
    "ScenarioPlanner": "Planning scenarios",
    "BrowserWalker": "Browser walkthrough",
    "EvidenceExtractor": "Collecting evidence",
    "ProductAnalyst": "Analyzing product experience",
    "CompetitiveAnalyst": "Comparing products",
    "Reviewer": "Reviewing findings",
    "Evaluator": "Scoring results",
    "MarkdownReportWriter": "Writing report",
    "AuthSession": "Manual authentication",
}
PIPELINE_FIXED_STAGE_COUNT = 7

AGENT_TERMINAL_STATUSES = {"succeeded", "failed", "skipped", "canceled"}
RUN_TERMINAL_STATUSES = {"succeeded", "blocked", "timeout", "failed", "canceled"}
BROWSER_USE_MODES = {"browser-use", "browser-use-local"}
IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
PAGE_EVIDENCE_ARTIFACT_TYPES = {
    "accessibility_tree.json": "accessibility_tree",
    "accessibility-tree.json": "accessibility_tree",
    "console_log.json": "console_log",
    "console-log.json": "console_log",
    "dom_snapshot.json": "dom_snapshot",
    "dom-snapshot.json": "dom_snapshot",
    "elements.json": "page_elements",
    "manifest.json": "page_evidence_manifest",
    "network_log.json": "network_log",
    "network-log.json": "network_log",
    "page.html": "page_html",
    "text.json": "page_text",
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
PAGE_EVIDENCE_PATH_KEYS = {
    "accessibility_tree_path",
    "artifact_path",
    "console_log_path",
    "dom_snapshot_path",
    "elements_path",
    "html_path",
    "manifest_path",
    "network_log_path",
    "page_evidence_artifact_path",
    "text_path",
}
PAGE_EVIDENCE_PATH_LIST_KEYS = {
    "artifact_paths",
    "page_evidence_artifact_paths",
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
        progress = self.runtime._progress_with_runtime_context(
            self.run_id,
            stage_key="director",
            stage_label=self.runtime._stage_label(event.agent or "ResearchDirector", self.run_id),
            stage_started_at=self.started_at,
            event_time=event.created_at,
            status="running",
        )
        self.runtime._update_run(self.run_id, status="running", started_at=self.started_at, progress=progress)
        self.runtime._upsert_agent(
            self.run_id,
            event.agent or "ResearchDirector",
            "running",
            started_at=self.started_at,
            metrics={
                **dict(event.data),
                **self.runtime._agent_progress_metrics(
                    self.run_id,
                    agent=event.agent or "ResearchDirector",
                    stage_started_at=self.started_at,
                    status="running",
                ),
            },
        )
        await self.runtime.append_event(
            self.run_id,
            "run.started",
            event.message or "Run started",
            agent_id=self.runtime._agent_id(event.agent or "ResearchDirector"),
            agent_type=self.runtime._agent_type(event.agent),
            status="running",
            payload={
                **dict(event.data),
                **self.runtime._event_progress_fields(
                    self.run_id,
                    agent=event.agent or "ResearchDirector",
                    base_progress=progress,
                    stage_started_at=self.started_at,
                    event_time=event.created_at,
                    status="running",
                ),
            },
        )
        await self._stage_started()

    async def _stage_started(self) -> None:
        if self.stage_started_emitted:
            return
        self.stage_started_emitted = True
        payload = self.runtime._event_progress_fields(
            self.run_id,
            agent="ResearchDirector",
            stage_key="pipeline",
            stage_label="Research pipeline",
            stage_started_at=self.started_at,
            status="running",
        )
        await self.runtime.append_event(
            self.run_id,
            "stage.started",
            "Research pipeline started",
            agent_id="agent_director",
            agent_type="director",
            status="running",
            payload=payload,
        )

    async def _run_completed(self, event: PipelineRunEvent) -> None:
        self.runtime._postprocess_run_outputs(self.run_id, self.run_dir)
        progress = self.runtime._progress_from_evidence(self.run_dir / "evidence.json")
        artifacts = self.runtime._refresh_artifacts(self.run_id)
        artifact_ids = [artifact["id"] for artifact in artifacts]
        final_status, final_error = self.runtime._final_status_from_evidence(self.run_id, self.run_dir)
        completed_at = event.created_at
        if final_status == "awaiting_verification":
            progress = self.runtime._progress_for_awaiting_verification(progress)
        progress = self.runtime._progress_with_runtime_context(
            self.run_id,
            base_progress=progress,
            stage_key=final_status,
            stage_label=self.runtime._terminal_message(final_status),
            stage_started_at=completed_at,
            event_time=completed_at,
            status=final_status,
        )
        run_completed_at = None if final_status == "awaiting_verification" else completed_at
        self.runtime._update_run(
            self.run_id,
            status=final_status,
            completed_at=run_completed_at,
            progress=progress,
            artifact_ids=artifact_ids,
            error=final_error,
        )
        self.runtime._upsert_agent(
            self.run_id,
            event.agent or "ResearchDirector",
            "waiting" if final_status == "awaiting_verification" else "succeeded",
            started_at=self.started_at,
            completed_at=None if final_status == "awaiting_verification" else completed_at,
            metrics={
                **dict(event.data),
                **self.runtime._agent_progress_metrics(
                    self.run_id,
                    agent=event.agent or "ResearchDirector",
                    stage_started_at=self.started_at,
                    completed_at=completed_at,
                    status=final_status,
                ),
            },
            error=final_error if final_status == "awaiting_verification" else None,
        )
        await self.runtime.append_event(
            self.run_id,
            "stage.completed",
            "Research pipeline completed",
            agent_id="agent_director",
            agent_type="director",
            status="finalizing",
            payload=self.runtime._event_progress_fields(
                self.run_id,
                agent="ResearchDirector",
                stage_key="finalizing",
                base_progress=progress,
                stage_label="Research pipeline completed",
                stage_started_at=completed_at,
                event_time=completed_at,
                status="finalizing",
            ),
        )
        for artifact in artifacts:
            if artifact.get("type") != "browser_history":
                continue
            artifact_payload = {
                "artifact_type": "browser_history",
                "artifact_path": artifact.get("path"),
                **self.runtime._event_progress_fields(
                    self.run_id,
                    agent="ResearchDirector",
                    stage_key="finalizing",
                    base_progress=progress,
                    stage_label="Archiving browser history",
                    stage_started_at=completed_at,
                    event_time=completed_at,
                    status="finalizing",
                ),
            }
            await self.runtime.append_event(
                self.run_id,
                "artifact.created",
                "Browser history archived",
                agent_id="agent_director",
                agent_type="director",
                status="finalizing",
                payload=artifact_payload,
                artifact_ids=[str(artifact["id"])],
            )
        terminal_event_type = self.runtime._terminal_event_type(final_status)
        terminal_level = "info" if final_status == "succeeded" else ("error" if final_status == "failed" else "warn")
        terminal_message = event.message if final_status == "succeeded" and event.message else self.runtime._terminal_message(final_status)
        await self.runtime.append_event(
            self.run_id,
            terminal_event_type,
            terminal_message,
            level=terminal_level,
            agent_id="agent_director",
            agent_type="director",
            status=final_status,
            payload={
                **dict(event.data),
                "final_status": final_status,
                "error": final_error,
                **self.runtime._event_progress_fields(
                    self.run_id,
                    agent="ResearchDirector",
                    stage_key=final_status,
                    base_progress=progress,
                    stage_label=self.runtime._terminal_message(final_status),
                    stage_started_at=completed_at,
                    event_time=completed_at,
                    status=final_status,
                ),
            },
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
        progress = self.runtime._progress_with_runtime_context(
            self.run_id,
            stage_key="failed",
            stage_label="Run failed",
            stage_started_at=completed_at,
            event_time=completed_at,
            status="failed",
        )
        self.runtime._update_run(self.run_id, status="failed", completed_at=completed_at, progress=progress, error=error)
        self.runtime._upsert_agent(
            self.run_id,
            event.agent or "ResearchDirector",
            "failed",
            started_at=self.started_at,
            completed_at=completed_at,
            metrics=self.runtime._agent_progress_metrics(
                self.run_id,
                agent=event.agent or "ResearchDirector",
                stage_started_at=self.started_at,
                completed_at=completed_at,
                status="failed",
            ),
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
            payload={
                **error,
                **self.runtime._event_progress_fields(
                    self.run_id,
                    agent="ResearchDirector",
                    stage_key="failed",
                    base_progress=progress,
                    stage_label="Run failed",
                    stage_started_at=completed_at,
                    event_time=completed_at,
                    status="failed",
                ),
            },
        )
        self.terminal_emitted = True

    async def _agent_started(self, event: PipelineRunEvent) -> None:
        await self._stage_started()
        agent_id = self.runtime._agent_id(event.agent, event.product, event.scenario_id)
        agent_type = self.runtime._agent_type(event.agent)
        browser_fields = self.runtime._browser_use_start_fields(self.run_id, event.agent)
        stage_label = browser_fields.get("stage_label") or self.runtime._stage_label(event.agent, self.run_id)
        progress = self.runtime._progress_with_runtime_context(
            self.run_id,
            stage_key=agent_type or "agent",
            stage_label=str(stage_label),
            stage_started_at=event.created_at,
            event_time=event.created_at,
            status="running",
        )
        self.runtime._update_run(self.run_id, progress=progress)
        self.runtime._upsert_agent(
            self.run_id,
            event.agent,
            "running",
            product=event.product,
            scenario_id=event.scenario_id,
            started_at=event.created_at,
            metrics={
                **self._metrics(event),
                **browser_fields,
                **self.runtime._agent_progress_metrics(
                    self.run_id,
                    agent=event.agent,
                    stage_started_at=event.created_at,
                    status="running",
                ),
            },
        )
        message = event.message or f"{event.agent or 'Agent'} started"
        if event.agent == "BrowserWalker" and browser_fields:
            message = f"Browser-use walkthrough started: {event.product or 'product'} / {event.scenario_id or 'scenario'}"
        await self.runtime.append_event(
            self.run_id,
            "agent.started",
            message,
            agent_id=agent_id,
            agent_type=agent_type,
            product=event.product,
            scenario_id=event.scenario_id,
            status="running",
            payload={
                **dict(event.data),
                **browser_fields,
                **self.runtime._event_progress_fields(
                    self.run_id,
                    agent=event.agent,
                    base_progress=progress,
                    stage_label=str(stage_label),
                    stage_started_at=event.created_at,
                    event_time=event.created_at,
                    status="running",
                ),
            },
        )

    async def _agent_finished(self, event: PipelineRunEvent) -> None:
        agent_status = self._agent_status(event.status)
        api_event_type = "agent.completed" if agent_status == "succeeded" else "agent.status_changed"
        started_at = self.runtime._agent_started_at(self.run_id, event.agent, event.product, event.scenario_id)
        completed_at = event.created_at if agent_status in AGENT_TERMINAL_STATUSES else None
        completion_fields = self.runtime._browser_use_completion_fields(self.run_id, event.agent, dict(event.data))
        self.runtime._upsert_agent(
            self.run_id,
            event.agent,
            agent_status,
            product=event.product,
            scenario_id=event.scenario_id,
            completed_at=completed_at,
            metrics={
                **self._metrics(event),
                **completion_fields,
                **self.runtime._agent_progress_metrics(
                    self.run_id,
                    agent=event.agent,
                    stage_started_at=started_at,
                    completed_at=event.created_at,
                    status=agent_status,
                ),
            },
        )
        stage_label = self.runtime._stage_label(event.agent, self.run_id)
        progress = self.runtime._progress_with_runtime_context(
            self.run_id,
            stage_key=self.runtime._stage_key(event.agent),
            stage_label=stage_label,
            stage_started_at=started_at or event.created_at,
            event_time=event.created_at,
            status=agent_status,
        )
        self.runtime._update_run(self.run_id, progress=progress)
        message = event.message or f"{event.agent or 'Agent'} completed"
        if event.agent == "BrowserWalker" and completion_fields:
            if agent_status == "succeeded":
                message = f"Browser-use walkthrough completed: {event.product or 'product'} / {event.scenario_id or 'scenario'}"
            else:
                message = f"Browser-use walkthrough status changed: {event.product or 'product'} / {event.scenario_id or 'scenario'}"
        await self.runtime.append_event(
            self.run_id,
            api_event_type,
            message,
            agent_id=self.runtime._agent_id(event.agent, event.product, event.scenario_id),
            agent_type=self.runtime._agent_type(event.agent),
            product=event.product,
            scenario_id=event.scenario_id,
            status=agent_status,
            payload={
                **dict(event.data),
                **self.runtime._event_progress_fields(
                    self.run_id,
                    agent=event.agent,
                    base_progress=progress,
                    stage_label=stage_label,
                    stage_started_at=started_at or event.created_at,
                    event_time=event.created_at,
                    status=agent_status,
                ),
                **completion_fields,
            },
        )

    async def _agent_blocked(self, event: PipelineRunEvent) -> None:
        started_at = self.runtime._agent_started_at(self.run_id, event.agent, event.product, event.scenario_id)
        completion_fields = self.runtime._browser_use_completion_fields(self.run_id, event.agent, dict(event.data))
        self.runtime._upsert_agent(
            self.run_id,
            event.agent,
            "waiting",
            product=event.product,
            scenario_id=event.scenario_id,
            metrics={
                **self._metrics(event),
                **completion_fields,
                **self.runtime._agent_progress_metrics(
                    self.run_id,
                    agent=event.agent,
                    stage_started_at=started_at,
                    completed_at=event.created_at,
                    status="waiting",
                ),
            },
        )
        stage_label = self.runtime._stage_label(event.agent, self.run_id)
        progress = self.runtime._progress_with_runtime_context(
            self.run_id,
            stage_key=self.runtime._stage_key(event.agent),
            stage_label=stage_label,
            stage_started_at=started_at or event.created_at,
            event_time=event.created_at,
            status="waiting",
        )
        self.runtime._update_run(self.run_id, progress=progress)
        message = event.message or f"{event.agent or 'Agent'} is waiting"
        if event.agent == "BrowserWalker" and completion_fields:
            message = f"Browser-use walkthrough needs attention: {event.product or 'product'} / {event.scenario_id or 'scenario'}"
        await self.runtime.append_event(
            self.run_id,
            "agent.status_changed",
            message,
            level="warn",
            agent_id=self.runtime._agent_id(event.agent, event.product, event.scenario_id),
            agent_type=self.runtime._agent_type(event.agent),
            product=event.product,
            scenario_id=event.scenario_id,
            status="waiting",
            payload={
                **dict(event.data),
                **self.runtime._event_progress_fields(
                    self.run_id,
                    agent=event.agent,
                    base_progress=progress,
                    stage_label=stage_label,
                    stage_started_at=started_at or event.created_at,
                    event_time=event.created_at,
                    status="waiting",
                ),
                **completion_fields,
            },
        )

    async def _artifact_written(self, event: PipelineRunEvent) -> None:
        artifacts = self.runtime._refresh_artifacts(self.run_id)
        progress = self.runtime._progress_with_runtime_context(
            self.run_id,
            base_progress=self.runtime._progress_from_evidence(self.run_dir / "evidence.json"),
            stage_key="finalizing",
            stage_label="Finalizing artifacts",
            stage_started_at=event.created_at,
            event_time=event.created_at,
            status="finalizing",
        )
        if not self.finalizing_emitted:
            self.runtime._update_run(self.run_id, status="finalizing", progress=progress)
            await self.runtime.append_event(
                self.run_id,
                "run.finalizing",
                "Run artifacts are being finalized",
                agent_id="agent_director",
                agent_type="director",
                status="finalizing",
                payload=self.runtime._event_progress_fields(
                    self.run_id,
                    agent="ResearchDirector",
                    stage_key="finalizing",
                    base_progress=progress,
                    stage_label="Finalizing artifacts",
                    stage_started_at=event.created_at,
                    event_time=event.created_at,
                    status="finalizing",
                ),
            )
            self.finalizing_emitted = True

        artifact_id = PIPELINE_ARTIFACT_IDS.get(event.artifact_type or "")
        known_artifact_ids = {artifact["id"] for artifact in artifacts}
        artifact_ids = [artifact_id] if artifact_id in known_artifact_ids else []
        payload = dict(event.data)
        if event.artifact_type:
            payload["artifact_type"] = event.artifact_type
        if event.artifact_path:
            payload["artifact_path"] = self.runtime._relative_path(Path(event.artifact_path))
        payload.update(
            self.runtime._event_progress_fields(
                self.run_id,
                agent=event.agent,
                stage_key="finalizing",
                base_progress=progress,
                stage_label="Finalizing artifacts",
                stage_started_at=event.created_at,
                event_time=event.created_at,
                status="finalizing",
            )
        )
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
                payload=self.runtime._event_progress_fields(
                    self.run_id,
                    agent="MarkdownReportWriter",
                    base_progress=progress,
                    stage_label="Report generated",
                    stage_started_at=event.created_at,
                    event_time=event.created_at,
                    status="finalizing",
                ),
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
                payload=self.runtime._event_progress_fields(
                    self.run_id,
                    agent="Evaluator",
                    base_progress=progress,
                    stage_label="Evaluation generated",
                    stage_started_at=event.created_at,
                    event_time=event.created_at,
                    status="finalizing",
                ),
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
            merged = dict(metrics)
        else:
            merged = {}
        for key, value in event.data.items():
            if key.endswith("_count") or key in {
                "step_count",
                "result_status",
                "scenario_title",
                "overall_score",
                "language",
            }:
                merged[key] = value
        return merged


class RunRuntime:
    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.examples_dir = self.workspace_root / "examples"
        self._runs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._active_browser_run_id: str | None = None
        self._auth_sessions: dict[str, dict[str, Any]] = {}
        self._auth_session_handles: dict[str, ManualAuthSession] = {}
        self._auth_session_timeout_tasks: dict[str, asyncio.Task[None]] = {}
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
        bundle = self._resolve_request_plan(request)
        mode = self._normalize_run_mode(request.mode, target_url=request.target_url)
        out_root = self._resolve_output_root(request.out)
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

        options = self._execution_options(request, mode=mode, report_language=report_language)
        if mode in BROWSER_USE_MODES:
            self._ensure_no_active_browser_use_run()
            readiness_errors = self._browser_use_readiness_errors(
                request,
                user_data_dir=options.browser_user_data_dir,
                storage_state=options.browser_storage_state,
            )
            if readiness_errors:
                raise ApiError(
                    503,
                    "BROWSER_USE_UNAVAILABLE",
                    "browser-use mode is not ready on this server.",
                    {"errors": readiness_errors},
                )

        run_id = self._new_run_id()
        run_dir = out_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        created_at = utc_now()
        params = self._request_params(request, options=options)
        run = {
            "id": run_id,
            "status": "queued",
            "mode": mode,
            "research_goal": bundle.plan.research_goal,
            "run_dir": self._relative_path(run_dir),
            "created_at": created_at,
            "started_at": None,
            "completed_at": None,
            "progress": {
                "total_scenarios": total_scenarios,
                "completed_scenarios": 0,
                "failed_scenarios": 0,
                "current_stage": "queued",
                "current_stage_label": "Queued",
                "current_stage_status": "queued",
                "stage_started_at": None,
                "elapsed_ms": 0,
                "elapsed_sec": 0.0,
                "stage_elapsed_ms": 0,
                "stage_elapsed_sec": 0.0,
                "completed_stage_count": 0,
                "total_stage_count": total_scenarios + PIPELINE_FIXED_STAGE_COUNT,
                "evidence_count": 0,
                "artifact_count": 0,
                "screenshot_count": 0,
                "browser_history_count": 0,
            },
            "params": params,
            "artifact_ids": [],
            "error": None,
            "metadata": (
                {"auth_session_id": options.auth_session_id, "auth_status": "auth_ready"}
                if options.auth_session_id
                else {}
            ),
        }
        self._write_json(run_dir / "plan.json", bundle.raw)
        self._write_json(run_dir / "run.json", run)
        self._write_json(run_dir / "agents.json", [self._agent(run_id, "pending")])
        self._write_json(run_dir / "artifacts.json", [])
        (run_dir / "events.jsonl").write_text("", encoding="utf-8")

        self._runs[run_id] = {"run": run, "run_dir": run_dir, "last_seq": 0}
        await self.append_event(run_id, "run.created", "Run created", status="queued")
        self._refresh_artifacts(run_id)
        if mode in BROWSER_USE_MODES:
            self._active_browser_run_id = run_id
        task = asyncio.create_task(self._execute_run(run_id, bundle.plan, run_dir, request, options))
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
            record = self._normalize_run_record(dict(state["run"]))
            records.append(self._reconcile_browser_use_terminal_status(run_id, Path(state["run_dir"]), record))
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

    async def delete_run(self, run_id: str) -> RunActionResponse:
        run_dir = self._run_dir_for_id(run_id)
        self._ensure_run_is_deletable(run_id)
        self._remove_run_state(run_id)
        self._delete_run_directory(run_dir)
        return RunActionResponse(
            run_id=run_id,
            status="deleted",
            accepted=True,
            message="Run record was deleted.",
        )

    async def clear_runs(self) -> RunClearResponse:
        deleted: list[str] = []
        skipped: list[str] = []
        run_ids = sorted({run_dir.name for run_dir in self._scan_run_dirs()} | set(self._runs.keys()))
        for run_id in run_ids:
            try:
                run_dir = self._run_dir_for_id(run_id)
                self._ensure_run_is_deletable(run_id)
                self._remove_run_state(run_id)
                self._delete_run_directory(run_dir)
                deleted.append(run_id)
            except ApiError as exc:
                if exc.code in {"RUN_DELETE_ACTIVE", "RUN_NOT_FOUND"}:
                    skipped.append(run_id)
                    continue
                raise
        return RunClearResponse(
            deleted_run_ids=deleted,
            skipped_run_ids=skipped,
            message=f"Deleted {len(deleted)} run records; skipped {len(skipped)} active records.",
        )

    async def confirm_verification(
        self,
        run_id: str,
        *,
        confirmed: bool,
        note: str | None = None,
    ) -> RunActionResponse:
        state = self._state_for_run(run_id)
        status = str(state["run"].get("status") or "running")
        message = (
            "Manual verification was recorded, but this endpoint does not resume a finished browser-use task. "
            "Create an auth session and start a retry run to continue with the refreshed login state."
        )
        await self.append_event(
            run_id,
            "agent.status_changed",
            "Manual verification confirmation recorded",
            agent_id="agent_auth_session",
            agent_type="auth_session",
            status=status,
            payload={"confirmed": confirmed, "note": note, "resume_supported": False, "message": message},
        )
        return RunActionResponse(run_id=run_id, status=status, accepted=True, message=message)

    async def create_auth_session(self, request: AuthSessionCreateRequest) -> AuthSessionDetail:
        run_id = request.run_id
        state: dict[str, Any] | None = None
        if run_id:
            state = self._state_for_run(run_id)
            status = str(state["run"].get("status") or "")
            if status != "awaiting_verification":
                raise ApiError(
                    400,
                    "RUN_NOT_AWAITING_VERIFICATION",
                    "Auth sessions for an existing run can only be created while it is awaiting manual verification.",
                    {"run_id": run_id, "status": status},
                )
        self._ensure_no_active_auth_session()

        run_dir = state["run_dir"] if state else None
        url = self._auth_session_url(request, run_dir)
        credentials_ref = request.credentials_ref or (self._auth_session_credentials_ref(run_dir) if run_dir else None)
        user_data_dir = self._resolve_auth_user_data_dir(request.browser_user_data_dir, credentials_ref, url)
        storage_state = self._resolve_auth_storage_state(request.browser_storage_state, user_data_dir)
        session_id = self._new_auth_session_id()
        now = utc_now()
        record = {
            "id": session_id,
            "session_id": session_id,
            "run_id": run_id,
            "status": "created",
            "auth_status": "auth_not_ready",
            "purpose": "verification_retry" if run_id else "manual_login_first",
            "url": url,
            "credentials_ref": credentials_ref,
            "browser_user_data_dir": str(user_data_dir),
            "browser_storage_state": str(storage_state),
            "browser_user_data_dir_configured": True,
            "browser_storage_state_configured": True,
            "storage_state_saved": False,
            "success_url_contains": [marker for marker in request.success_url_contains if marker.strip()],
            "login_url_contains": request.login_url_contains or "/auth/login",
            "timeout_sec": request.timeout_sec,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "retry_run_id": None,
            "error": None,
            "message": "Visible browser login session created.",
        }
        self._auth_sessions[session_id] = record
        self._write_auth_session_record(record)
        if run_id:
            self._merge_run_metadata(
                run_id,
                {
                    "verification_session_id": session_id,
                    "verification_status": "created",
                },
            )
            self._upsert_agent(run_id, "AuthSession", "running", started_at=now)
            await self.append_event(
                run_id,
                "auth_session.started",
                "Visible browser auth session started",
                agent_id="agent_auth_session",
                agent_type="auth_session",
                status="running",
                payload={
                    "session_id": session_id,
                    "url": self._safe_url_for_logs(url),
                    "credentials_ref": credentials_ref,
                    "storage_state_configured": True,
                },
            )

        self._set_auth_session_status(session_id, "running", message="Opening a visible browser window.")
        try:
            manual_request = ManualAuthSessionRequest(
                url=url,
                credentials_ref=credentials_ref,
                user_data_dir=user_data_dir,
                storage_state=storage_state,
                success_url_contains=list(record["success_url_contains"]),
                login_url_contains=str(record["login_url_contains"]),
                timeout_sec=float(record["timeout_sec"]),
                manual_confirm=True,
            )
            handle = await open_manual_auth_session(manual_request)
        except RuntimeError as exc:
            error_text = self._safe_error_text(str(exc))
            self._set_auth_session_failed(session_id, exc, status="failed")
            if run_id:
                self._upsert_agent(run_id, "AuthSession", "failed", completed_at=utc_now(), error=self._error_payload(exc))
                await self.append_event(
                    run_id,
                    "auth_session.failed",
                    "Visible browser auth session failed to start",
                    level="error",
                    agent_id="agent_auth_session",
                    agent_type="auth_session",
                    status="failed",
                    payload={"session_id": session_id, "error": error_text},
                )
            raise ApiError(
                503,
                "AUTH_SESSION_UNAVAILABLE",
                "Visible browser auth session could not be started.",
                {"session_id": session_id, "error": error_text},
            ) from exc
        except Exception as exc:  # noqa: BLE001
            error_text = self._safe_error_text(str(exc))
            self._set_auth_session_failed(session_id, exc, status="failed")
            if run_id:
                self._upsert_agent(run_id, "AuthSession", "failed", completed_at=utc_now(), error=self._error_payload(exc))
                await self.append_event(
                    run_id,
                    "auth_session.failed",
                    "Visible browser auth session failed to start",
                    level="error",
                    agent_id="agent_auth_session",
                    agent_type="auth_session",
                    status="failed",
                    payload={"session_id": session_id, "error": error_text},
                )
            raise ApiError(
                500,
                "AUTH_SESSION_FAILED",
                "Visible browser auth session failed to start.",
                {"session_id": session_id, "error": error_text},
            ) from exc

        self._auth_session_handles[session_id] = handle
        self._set_auth_session_status(
            session_id,
            "awaiting_user",
            message="Waiting for the user to complete login or verification.",
        )
        if run_id:
            self._merge_run_metadata(
                run_id,
                {
                    "verification_session_id": session_id,
                    "verification_status": "awaiting_user",
                },
            )
            await self.append_event(
                run_id,
                "auth_session.awaiting_user",
                "Visible browser is waiting for manual login or verification",
                agent_id="agent_auth_session",
                agent_type="auth_session",
                status="waiting",
                payload={"session_id": session_id, "timeout_sec": request.timeout_sec},
            )
        self._auth_session_timeout_tasks[session_id] = asyncio.create_task(
            self._auth_session_timeout(session_id, float(request.timeout_sec))
        )
        if run_id:
            self._persist_auth_session_artifact(run_id, session_id)
        return self._auth_session_detail(session_id)

    def get_auth_session(self, session_id: str) -> AuthSessionDetail:
        return self._auth_session_detail(session_id)

    async def confirm_auth_session(
        self,
        session_id: str,
        *,
        confirmed: bool = True,
        note: str | None = None,
    ) -> AuthSessionDetail:
        record = self._auth_session_record(session_id)
        run_id = record.get("run_id") if isinstance(record.get("run_id"), str) else None
        if not confirmed:
            await self._close_auth_session(session_id)
            self._set_auth_session_status(session_id, "canceled", completed_at=utc_now(), message="Auth session canceled.")
            if run_id:
                self._upsert_agent(run_id, "AuthSession", "canceled", completed_at=utc_now())
                await self.append_event(
                    run_id,
                    "auth_session.failed",
                    "Visible browser auth session canceled",
                    level="warn",
                    agent_id="agent_auth_session",
                    agent_type="auth_session",
                    status="canceled",
                    payload={"session_id": session_id, "note": note},
                )
                self._persist_auth_session_artifact(run_id, session_id)
            return self._auth_session_detail(session_id)

        if record.get("status") not in {"running", "awaiting_user"}:
            return self._auth_session_detail(session_id)

        handle = self._auth_session_handles.get(session_id)
        if handle is None:
            raise ApiError(
                409,
                "AUTH_SESSION_NOT_ACTIVE",
                "The visible browser session is no longer active. Create a new auth session.",
                {"session_id": session_id, "status": record.get("status")},
            )

        try:
            current_url = await complete_manual_auth_session(handle)
        except Exception as exc:  # noqa: BLE001
            error_text = self._safe_error_text(str(exc))
            await self._close_auth_session(session_id)
            self._set_auth_session_failed(session_id, exc, status="failed")
            if run_id:
                self._upsert_agent(run_id, "AuthSession", "failed", completed_at=utc_now(), error=self._error_payload(exc))
                await self.append_event(
                    run_id,
                    "auth_session.failed",
                    "Manual auth session could not be confirmed",
                    level="error",
                    agent_id="agent_auth_session",
                    agent_type="auth_session",
                    status="failed",
                    payload={"session_id": session_id, "error": error_text, "note": note},
                )
                self._persist_auth_session_artifact(run_id, session_id)
            raise ApiError(
                400,
                "AUTH_SESSION_CONFIRM_FAILED",
                "Manual verification was not confirmed. Complete login or verification in the visible browser first.",
                {"session_id": session_id, "error": error_text},
            ) from exc
        finally:
            self._auth_session_handles.pop(session_id, None)
            self._cancel_auth_session_timeout(session_id)

        storage_state = Path(str(record["browser_storage_state"]))
        completed_at = utc_now()
        record.update(
            {
                "status": "succeeded",
                "updated_at": completed_at,
                "completed_at": completed_at,
                "storage_state_saved": storage_state.is_file(),
                "current_url": current_url,
                "error": None,
                "message": (
                    "Manual verification completed. Create a retry run to continue with the refreshed login state."
                    if run_id
                    else "Login state is ready. Start a browser-use run with this auth session."
                ),
            }
        )
        self._write_auth_session_record(record)
        if run_id:
            self._merge_run_metadata(
                run_id,
                {
                    "verification_session_id": session_id,
                    "verification_status": "succeeded",
                },
            )
            self._upsert_agent(run_id, "AuthSession", "succeeded", completed_at=completed_at)
            await self.append_event(
                run_id,
                "auth_session.completed",
                "Manual auth session completed and storage state was saved",
                agent_id="agent_auth_session",
                agent_type="auth_session",
                status="succeeded",
                payload={
                    "session_id": session_id,
                    "storage_state_saved": record["storage_state_saved"],
                    "current_url": self._safe_url_for_logs(current_url),
                    "note": note,
                },
            )
            self._persist_auth_session_artifact(run_id, session_id)
        return self._auth_session_detail(session_id)

    async def retry_after_verification(
        self,
        run_id: str,
        request: RetryAfterVerificationRequest,
    ) -> RetryAfterVerificationResponse:
        original = self._state_for_run(run_id)
        session_id = request.session_id or self._latest_succeeded_auth_session_id(run_id)
        if not session_id:
            raise ApiError(
                400,
                "AUTH_SESSION_REQUIRED",
                "A succeeded auth session is required before starting a verification retry run.",
                {"run_id": run_id},
            )
        session = self._auth_session_record(session_id)
        if session.get("run_id") != run_id:
            raise ApiError(
                400,
                "AUTH_SESSION_RUN_MISMATCH",
                "Auth session does not belong to this run.",
                {"run_id": run_id, "session_id": session_id},
            )
        if session.get("status") != "succeeded":
            raise ApiError(
                400,
                "AUTH_SESSION_NOT_COMPLETE",
                "Complete the visible browser auth session before starting a retry run.",
                {"session_id": session_id, "status": session.get("status")},
            )
        if session.get("retry_run_id"):
            retry_id = str(session["retry_run_id"])
            retry_record = self._record_for_run(retry_id)
            return RetryAfterVerificationResponse(
                run_id=run_id,
                retry_run_id=retry_id,
                parent_run_id=run_id,
                retry_of_run_id=run_id,
                status=str(retry_record.get("status") or "queued"),
                accepted=True,
                session=self._auth_session_detail(session_id),
                message="Retry run was already started for this auth session.",
            )

        retry_request = self._retry_request_from_run(original["run"], original["run_dir"], session)
        response = await self.start_run(retry_request)
        retry_run_id = response.run_id
        now = utc_now()
        session["retry_run_id"] = retry_run_id
        session["updated_at"] = now
        self._write_auth_session_record(session)
        self._merge_run_metadata(
            run_id,
            {
                "verification_session_id": session_id,
                "verification_status": "retry_started",
                "retry_run_id": retry_run_id,
            },
        )
        self._merge_run_metadata(
            retry_run_id,
            {
                "parent_run_id": run_id,
                "retry_of_run_id": run_id,
                "verification_session_id": session_id,
                "retry_reason": "manual_verification_completed",
            },
        )
        await self.append_event(
            run_id,
            "run.retry_started",
            "Verification retry run started with refreshed login state",
            agent_id="agent_auth_session",
            agent_type="auth_session",
            status=str(original["run"].get("status") or "awaiting_verification"),
            payload={"session_id": session_id, "retry_run_id": retry_run_id, "note": request.note},
        )
        await self.append_event(
            retry_run_id,
            "run.retry_started",
            "Retry run created after manual verification",
            agent_id="agent_auth_session",
            agent_type="auth_session",
            status="queued",
            payload={"retry_of_run_id": run_id, "verification_session_id": session_id},
        )
        self._persist_auth_session_artifact(run_id, session_id)
        return RetryAfterVerificationResponse(
            run_id=run_id,
            retry_run_id=retry_run_id,
            parent_run_id=run_id,
            retry_of_run_id=run_id,
            status=response.status,
            accepted=True,
            session=self._auth_session_detail(session_id),
            message="Walkthrough continued with the refreshed login state.",
        )

    def list_agents(self, run_id: str) -> list[AgentExecution]:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "agents.json"
        if not path.exists():
            return [self._agent(run_id, "succeeded")]
        payload = self._read_json(path)
        if not isinstance(payload, list):
            return []
        items = [dict(item) for item in payload if isinstance(item, dict)]
        try:
            run_status = str(self._record_for_run(run_id).get("status") or "")
        except ApiError:
            run_status = ""
        if run_status == "awaiting_verification":
            has_waiting_agent = False
            for item in items:
                if item.get("type") == "director":
                    item["status"] = "waiting"
                    item["completed_at"] = None
                    has_waiting_agent = True
            if not has_waiting_agent:
                items.append(self._agent(run_id, "waiting"))
        return [AgentExecution(**item) for item in items]

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
        return status in RUN_TERMINAL_STATUSES or status == "awaiting_verification"

    def list_artifacts(self, run_id: str) -> list[Artifact]:
        run_dir = self._run_dir_for_id(run_id)
        self._ensure_walkthrough_map(run_id, run_dir)
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
        issues = None
        issues_path = run_dir / "issues.json"
        if issues_path.exists():
            issues = self._read_json(issues_path)
        return {
            "run_id": run_id,
            "language": self._record_for_run(run_id).get("params", {}).get("report_language"),
            "markdown_artifact_id": "art_report_md",
            "evaluation_artifact_id": "art_evaluation_json" if evaluation_path.exists() else None,
            "issues_artifact_id": "art_issues_json" if issues_path.exists() else None,
            "markdown": path.read_text(encoding="utf-8"),
            "evaluation": evaluation,
            "issues": issues,
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
        artifact_map = self._artifact_ref_map(run_dir, artifacts)
        raw_results = payload.get("results", [])
        raw_evidence = payload.get("evidence", [])
        evidence_context = self._evidence_context(raw_results)
        issues_path = run_dir / "issues.json"
        issues = self._read_json(issues_path) if issues_path.exists() else None
        return {
            "run_id": run_id,
            "artifact_id": "art_evidence_json",
            "created_at": payload.get("created_at"),
            "report_language": payload.get("report_language"),
            "results": self._normalize_results(raw_results, screenshot_map),
            "evidence": self._normalize_evidence_items(raw_evidence, evidence_context, screenshot_map, artifact_map),
            "issues": issues,
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

    def read_issues(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "issues.json"
        if not path.exists():
            raise ApiError(404, "ARTIFACT_NOT_FOUND", "issues.json is not available yet.", {"run_id": run_id})
        payload = self._read_json(path)
        return {"run_id": run_id, "artifact_id": "art_issues_json", **payload}

    def read_map(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir_for_id(run_id)
        payload = self._ensure_walkthrough_map(run_id, run_dir, raise_on_missing_evidence=True)
        if payload is None:
            raise ApiError(404, "ARTIFACT_NOT_FOUND", "walkthrough_map.json is not available yet.", {"run_id": run_id})
        return payload

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
        artifact_map: dict[str, str],
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
            if screenshot_artifact_id is None:
                page_evidence = data.get("page_evidence")
                if isinstance(page_evidence, dict):
                    for screenshot_path in (
                        page_evidence.get("viewport_screenshot_path"),
                        page_evidence.get("full_page_screenshot_path"),
                    ):
                        screenshot_artifact_id = self._screenshot_artifact_id(screenshot_path, screenshot_map)
                        if screenshot_artifact_id:
                            break
            screenshot_artifact_ids = self._screenshot_artifact_ids(item, data, screenshot_map)
            artifact_ids = self._linked_artifact_ids(item, data, artifact_map)

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
                    "screenshot_artifact_ids": screenshot_artifact_ids,
                    "artifact_ids": artifact_ids,
                    "confidence": item.get("confidence"),
                    "created_at": item.get("created_at"),
                    "errors": errors,
                    "final_output": data.get("final_output") if isinstance(data.get("final_output"), str) else None,
                    "data": self._sanitize_evidence_data(data),
                }
            )
        return items

    def _artifact_ref_map(self, run_dir: Path, artifacts: list[dict[str, Any]]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        root = run_dir.resolve()
        for artifact in artifacts:
            artifact_id = str(artifact.get("id") or "")
            rel_path = str(artifact.get("path") or "").replace("\\", "/")
            if not artifact_id or not rel_path:
                continue
            mapping[artifact_id] = artifact_id
            mapping[rel_path] = artifact_id
            abs_path = (root / rel_path).resolve()
            mapping[str(abs_path)] = artifact_id
            mapping[str(abs_path).replace("\\", "/")] = artifact_id
        return mapping

    def _linked_artifact_ids(
        self,
        item: dict[str, Any],
        data: dict[str, Any],
        artifact_map: dict[str, str],
    ) -> list[str]:
        refs: list[Any] = [item.get("screenshot"), data.get("screenshot_path"), data.get("browser_history_artifact_id")]

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, str):
                refs.append(value)

        visit(data)
        seen: set[str] = set()
        artifact_ids: list[str] = []
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                continue
            normalized = ref.strip().replace("\\", "/")
            artifact_id = artifact_map.get(normalized)
            if not artifact_id or artifact_id in seen:
                continue
            seen.add(artifact_id)
            artifact_ids.append(artifact_id)
        return artifact_ids

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

    def _screenshot_artifact_ids(
        self,
        item: dict[str, Any],
        data: dict[str, Any],
        screenshot_map: dict[str, str],
    ) -> list[str]:
        refs: list[Any] = [item.get("screenshot"), data.get("screenshot_path")]
        screenshot_paths = data.get("screenshot_paths")
        if isinstance(screenshot_paths, list):
            refs.extend(screenshot_paths)
        page_evidence = data.get("page_evidence")
        if isinstance(page_evidence, dict):
            for key in ("viewport_screenshot_path", "full_page_screenshot_path", "screenshot_path"):
                refs.append(page_evidence.get(key))
            page_evidence_screenshots = page_evidence.get("screenshot_paths")
            if isinstance(page_evidence_screenshots, list):
                refs.extend(page_evidence_screenshots)
        seen: set[str] = set()
        artifact_ids: list[str] = []
        for ref in refs:
            artifact_id = self._screenshot_artifact_id(ref, screenshot_map)
            if not artifact_id or artifact_id in seen:
                continue
            seen.add(artifact_id)
            artifact_ids.append(artifact_id)
        return artifact_ids

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

    async def _execute_run(
        self,
        run_id: str,
        plan: ResearchPlan,
        run_dir: Path,
        request: RunStartRequest,
        options: RunExecutionOptions,
    ) -> None:
        adapter = PipelineEventAdapter(self, run_id, run_dir)
        try:
            walker = self._walker_for_options(request, options)
            director = ResearchDirector(
                walker=walker,
                concurrency=options.concurrency,
                report_language=options.report_language,
                event_sink=adapter,
            )
            await director.run(plan, run_dir)
            if not adapter.terminal_emitted:
                self._postprocess_run_outputs(run_id, run_dir)
                progress = self._progress_from_evidence(run_dir / "evidence.json")
                artifacts = self._refresh_artifacts(run_id)
                artifact_ids = [artifact["id"] for artifact in artifacts]
                final_status, final_error = self._final_status_from_evidence(run_id, run_dir)
                completed_at = utc_now()
                if final_status == "awaiting_verification":
                    progress = self._progress_for_awaiting_verification(progress)
                progress = self._progress_with_runtime_context(
                    run_id,
                    base_progress=progress,
                    stage_key=final_status,
                    stage_label=self._terminal_message(final_status),
                    stage_started_at=completed_at,
                    event_time=completed_at,
                    status=final_status,
                )
                run_completed_at = None if final_status == "awaiting_verification" else completed_at
                self._update_run(
                    run_id,
                    status=final_status,
                    completed_at=run_completed_at,
                    progress=progress,
                    artifact_ids=artifact_ids,
                    error=final_error,
                )
                self._upsert_agent(
                    run_id,
                    "ResearchDirector",
                    "waiting" if final_status == "awaiting_verification" else "succeeded",
                    started_at=adapter.started_at,
                    completed_at=None if final_status == "awaiting_verification" else completed_at,
                    metrics=self._agent_progress_metrics(
                        run_id,
                        agent="ResearchDirector",
                        stage_started_at=adapter.started_at,
                        completed_at=completed_at,
                        status=final_status,
                    ),
                    error=final_error if final_status == "awaiting_verification" else None,
                )
                await self.append_event(
                    run_id,
                    self._terminal_event_type(final_status),
                    self._terminal_message(final_status),
                    level="info" if final_status == "succeeded" else ("error" if final_status == "failed" else "warn"),
                    status=final_status,
                    payload={
                        "final_status": final_status,
                        "error": final_error,
                        **self._event_progress_fields(
                            run_id,
                            agent="ResearchDirector",
                            stage_key=final_status,
                            base_progress=progress,
                            stage_label=self._terminal_message(final_status),
                            stage_started_at=completed_at,
                            event_time=completed_at,
                            status=final_status,
                        ),
                    },
                    artifact_ids=artifact_ids,
                )
        except Exception as exc:  # noqa: BLE001 - surfaced through run status and events.
            if not adapter.terminal_emitted:
                completed_at = utc_now()
                error = {"message": str(exc), "type": type(exc).__name__}
                progress = self._progress_with_runtime_context(
                    run_id,
                    stage_key="failed",
                    stage_label="Run failed",
                    stage_started_at=completed_at,
                    event_time=completed_at,
                    status="failed",
                )
                self._update_run(run_id, status="failed", completed_at=completed_at, progress=progress, error=error)
                self._upsert_agent(
                    run_id,
                    "ResearchDirector",
                    "failed",
                    completed_at=completed_at,
                    metrics=self._agent_progress_metrics(
                        run_id,
                        agent="ResearchDirector",
                        stage_started_at=adapter.started_at,
                        completed_at=completed_at,
                        status="failed",
                    ),
                    error=error,
                )
                await self.append_event(
                    run_id,
                    "run.failed",
                    f"Run failed: {exc}",
                    level="error",
                    status="failed",
                    payload={
                        **error,
                        **self._event_progress_fields(
                            run_id,
                            agent="ResearchDirector",
                            stage_key="failed",
                            base_progress=progress,
                            stage_label="Run failed",
                            stage_started_at=completed_at,
                            event_time=completed_at,
                            status="failed",
                        ),
                    },
                )
        finally:
            if self._active_browser_run_id == run_id:
                self._active_browser_run_id = None

    async def _execute_mock_run(
        self,
        run_id: str,
        plan: ResearchPlan,
        run_dir: Path,
        request: RunStartRequest,
    ) -> None:
        options = self._execution_options(
            request,
            mode="mock",
            report_language=normalize_report_language(request.report_language or plan.report_language),
        )
        await self._execute_run(run_id, plan, run_dir, request, options)

    def _walker_for_options(self, request: RunStartRequest, options: RunExecutionOptions) -> BrowserWalker:
        if options.mode in BROWSER_USE_MODES:
            return BrowserUseLocalWalker(
                model=request.browser_model,
                max_steps=request.browser_max_steps,
                run_timeout_sec=request.browser_timeout_sec,
                user_data_dir=options.browser_user_data_dir,
                storage_state=options.browser_storage_state,
                discover_all_pages=request.browser_discover_all_pages,
                discovery_max_pages=request.browser_discovery_max_pages,
                discovery_max_depth=request.browser_discovery_max_depth,
            )
        return MockBrowserWalker()

    def _normalize_run_mode(self, mode: str | None, *, target_url: str | None = None) -> str:
        default_mode = "browser-use" if target_url else "mock"
        normalized = (mode or default_mode).strip().lower()
        if normalized not in {"mock", *BROWSER_USE_MODES}:
            raise ApiError(
                400,
                "BAD_REQUEST",
                "mode must be one of: mock, browser-use, browser-use-local.",
                {"mode": mode},
            )
        return normalized

    def _normalize_verification_mode(self, mode: str | None) -> str:
        normalized = (mode or "off").strip().lower()
        if normalized == "manual":
            return "auto"
        if normalized not in {"auto", "off"}:
            raise ApiError(
                400,
                "BAD_REQUEST",
                "verification_mode must be auto, off, or manual.",
                {"verification_mode": mode},
            )
        return normalized

    def _execution_options(
        self,
        request: RunStartRequest,
        *,
        mode: str,
        report_language: str,
    ) -> RunExecutionOptions:
        if request.concurrency is not None and request.concurrency < 1:
            raise ApiError(400, "BAD_REQUEST", "concurrency must be greater than or equal to 1.")

        is_browser_use = mode in BROWSER_USE_MODES
        concurrency = request.concurrency if request.concurrency is not None else (1 if is_browser_use else 3)
        verification_mode = self._normalize_verification_mode(request.verification_mode)
        browser_user_data_dir = None
        browser_storage_state = None
        auth_session_id = None

        if is_browser_use:
            if concurrency != 1:
                raise ApiError(
                    400,
                    "BAD_REQUEST",
                    "browser-use runs must use concurrency 1 in the local backend.",
                    {"concurrency": concurrency},
                )
            if request.browser_max_steps < 1 or request.browser_max_steps > 200:
                raise ApiError(
                    400,
                    "BAD_REQUEST",
                    "browser_max_steps must be between 1 and 200.",
                    {"browser_max_steps": request.browser_max_steps},
                )
            if request.browser_timeout_sec < 0 or request.browser_timeout_sec > 7200:
                raise ApiError(
                    400,
                    "BAD_REQUEST",
                    "browser_timeout_sec must be between 0 and 7200.",
                    {"browser_timeout_sec": request.browser_timeout_sec},
                )
            if request.browser_discovery_max_pages is not None and not (1 <= request.browser_discovery_max_pages <= 1000):
                raise ApiError(
                    400,
                    "BAD_REQUEST",
                    "browser_discovery_max_pages must be between 1 and 1000.",
                    {"browser_discovery_max_pages": request.browser_discovery_max_pages},
                )
            if request.browser_discovery_max_depth is not None and not (0 <= request.browser_discovery_max_depth <= 10):
                raise ApiError(
                    400,
                    "BAD_REQUEST",
                    "browser_discovery_max_depth must be between 0 and 10.",
                    {"browser_discovery_max_depth": request.browser_discovery_max_depth},
                )
            if request.verification_timeout_sec <= 0 or request.verification_timeout_sec > 3600:
                raise ApiError(
                    400,
                    "BAD_REQUEST",
                    "verification_timeout_sec must be between 1 and 3600.",
                    {"verification_timeout_sec": request.verification_timeout_sec},
                )
            if request.auth_session_id:
                session = self._ready_auth_session_for_run(request.auth_session_id)
                auth_session_id = str(session["id"])
                browser_user_data_dir = str(session["browser_user_data_dir"])
                browser_storage_state = str(session["browser_storage_state"])
                verification_mode = "auto" if verification_mode == "off" else verification_mode
            else:
                browser_user_data_dir = self._resolve_browser_runtime_path(
                    request.browser_user_data_dir,
                    label="browser_user_data_dir",
                    expect_file=False,
                )
                browser_storage_state = self._resolve_browser_runtime_path(
                    request.browser_storage_state,
                    label="browser_storage_state",
                    expect_file=True,
                )

        return RunExecutionOptions(
            mode=mode,
            concurrency=concurrency,
            report_language=report_language,
            browser_user_data_dir=browser_user_data_dir,
            browser_storage_state=browser_storage_state,
            auth_session_id=auth_session_id,
            verification_mode=verification_mode,
        )

    def _resolve_browser_runtime_path(
        self,
        value: str | None,
        *,
        label: str,
        expect_file: bool,
    ) -> str | None:
        if not value:
            return None
        raw = Path(value).expanduser()
        if not raw.is_absolute():
            raw = self.workspace_root / raw
        resolved = raw.resolve()
        workspace = self.workspace_root.resolve()
        if not resolved.is_relative_to(workspace):
            raise ApiError(
                400,
                "BAD_REQUEST",
                f"{label} must stay inside the prodwalk workspace.",
                {label: value},
            )
        if expect_file and resolved.exists() and not resolved.is_file():
            raise ApiError(400, "BAD_REQUEST", f"{label} must be a JSON file path.", {label: value})
        if not expect_file and resolved.exists() and not resolved.is_dir():
            raise ApiError(400, "BAD_REQUEST", f"{label} must be a directory path.", {label: value})
        return str(resolved)

    def _ensure_no_active_browser_use_run(self) -> None:
        run_id = self._active_browser_run_id
        if not run_id:
            return
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            raise ApiError(
                409,
                "BROWSER_USE_RUN_ACTIVE",
                "Another local browser-use run is already active.",
                {"run_id": run_id},
            )
        self._active_browser_run_id = None

    def _ensure_run_is_deletable(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            raise ApiError(
                409,
                "RUN_DELETE_ACTIVE",
                "Stop the active run before deleting its record.",
                {"run_id": run_id},
            )
        if self._active_browser_run_id == run_id:
            self._active_browser_run_id = None

    def _remove_run_state(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
        self._tasks.pop(run_id, None)
        subscribers = self._subscribers.pop(run_id, set())
        for queue in subscribers:
            queue.put_nowait(
                {
                    "id": "evt_deleted",
                    "run_id": run_id,
                    "seq": 0,
                    "ts": utc_now(),
                    "type": "run.deleted",
                    "level": "warn",
                    "message": "Run record was deleted.",
                    "status": "deleted",
                    "payload": {},
                    "artifact_ids": [],
                }
            )

    def _delete_run_directory(self, run_dir: Path) -> None:
        resolved = run_dir.resolve()
        workspace = self.workspace_root.resolve()
        if not resolved.is_relative_to(workspace):
            raise ApiError(
                403,
                "RUN_DELETE_FORBIDDEN",
                "Run directory is outside the prodwalk workspace.",
                {"run_dir": str(run_dir)},
            )
        if not resolved.name.startswith("run-") or not resolved.parent.name.startswith("runs"):
            raise ApiError(
                403,
                "RUN_DELETE_FORBIDDEN",
                "Only prodwalk run directories can be deleted.",
                {"run_dir": self._relative_path(resolved)},
            )
        shutil.rmtree(resolved)

    def _browser_use_readiness_errors(
        self,
        request: RunStartRequest,
        *,
        user_data_dir: str | None,
        storage_state: str | None,
    ) -> list[str]:
        missing: list[str] = []
        if not self._module_available("browser_use"):
            missing.append('browser-use is not installed. Install with `pip install -e ".[browser-use-local]"`.')
        if not self._module_available("playwright.async_api"):
            missing.append('Playwright is not installed. Install with `pip install -e ".[browser-use-local]"`.')
        if missing:
            return missing

        try:
            walker = BrowserUseLocalWalker(
                model=request.browser_model,
                max_steps=request.browser_max_steps,
                run_timeout_sec=request.browser_timeout_sec,
                user_data_dir=user_data_dir,
                storage_state=storage_state,
                discover_all_pages=request.browser_discover_all_pages,
                discovery_max_pages=request.browser_discovery_max_pages,
                discovery_max_depth=request.browser_discovery_max_depth,
            )
        except Exception as exc:  # noqa: BLE001 - configuration errors are returned to the API caller.
            return [f"browser-use configuration failed: {exc}"]

        config_error = self._browser_use_llm_config_error(walker)
        return [config_error] if config_error else []

    def _module_available(self, module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ValueError):
            return False

    def _browser_use_llm_config_error(self, walker: BrowserUseLocalWalker) -> str | None:
        provider = str(getattr(walker, "provider", "openai") or "openai").lower()
        codex_config = getattr(walker, "codex_config", {})
        if not isinstance(codex_config, dict):
            codex_config = {}
        api_key = os.getenv("BROWSER_USE_LLM_API_KEY")
        if provider == "openai":
            key = api_key or os.getenv("OPENAI_API_KEY") or codex_config.get("api_key")
            if not key:
                return (
                    "OpenAI-compatible browser-use runs need OPENAI_API_KEY, "
                    "BROWSER_USE_LLM_API_KEY, or a Codex auth.json API key."
                )
            return None
        if provider == "anthropic" and not (api_key or os.getenv("ANTHROPIC_API_KEY")):
            return "Anthropic browser-use runs need ANTHROPIC_API_KEY or BROWSER_USE_LLM_API_KEY."
        if provider == "google" and not (api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
            return "Google browser-use runs need GOOGLE_API_KEY, GEMINI_API_KEY, or BROWSER_USE_LLM_API_KEY."
        if provider == "openrouter" and not (api_key or os.getenv("OPENROUTER_API_KEY")):
            return "OpenRouter browser-use runs need OPENROUTER_API_KEY or BROWSER_USE_LLM_API_KEY."
        if provider == "ollama":
            return None
        if provider not in {"openai", "anthropic", "google", "openrouter", "ollama"}:
            return f"Unsupported BROWSER_USE_LLM_PROVIDER: {provider}."
        return None

    def _ensure_no_active_auth_session(self) -> None:
        for session_id, handle in list(self._auth_session_handles.items()):
            record = self._auth_sessions.get(session_id) or self._read_auth_session_record(session_id)
            if record and record.get("status") in {"running", "awaiting_user"} and handle is not None:
                raise ApiError(
                    409,
                    "AUTH_SESSION_ACTIVE",
                    "Another visible auth session is already active.",
                    {"session_id": session_id, "run_id": record.get("run_id")},
                )

    def _ready_auth_session_for_run(self, session_id: str) -> dict[str, Any]:
        session = self._auth_session_record(session_id)
        if session.get("status") != "succeeded":
            raise ApiError(
                400,
                "AUTH_NOT_READY",
                "Manual login must be completed before this auth session can be used for a browser-use run.",
                {
                    "session_id": session_id,
                    "status": session.get("status"),
                    "auth_status": self._auth_status_for_session(session),
                },
            )
        user_data_dir = session.get("browser_user_data_dir")
        storage_state = session.get("browser_storage_state")
        if not isinstance(user_data_dir, str) or not user_data_dir:
            raise ApiError(
                400,
                "AUTH_SESSION_INVALID",
                "Auth session is missing a browser profile path.",
                {"session_id": session_id},
            )
        if not isinstance(storage_state, str) or not storage_state:
            raise ApiError(
                400,
                "AUTH_SESSION_INVALID",
                "Auth session is missing a storage state path.",
                {"session_id": session_id},
            )
        return session

    def _auth_session_url(self, request: AuthSessionCreateRequest, run_dir: Path | None) -> str:
        url = (request.url or "").strip()
        if not url and run_dir is not None:
            plan = self._read_run_plan(run_dir)
            products = plan.get("products") if isinstance(plan.get("products"), list) else []
            for product in products:
                if isinstance(product, dict) and isinstance(product.get("url"), str) and product["url"].strip():
                    url = product["url"].strip()
                    break
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ApiError(
                400,
                "BAD_REQUEST",
                "auth session url must be an http or https URL, or the run plan must contain one.",
                {"url": request.url},
            )
        return url

    def _auth_session_credentials_ref(self, run_dir: Path) -> str | None:
        plan = self._read_run_plan(run_dir)
        products = plan.get("products") if isinstance(plan.get("products"), list) else []
        for product in products:
            if isinstance(product, dict) and isinstance(product.get("credentials_ref"), str):
                value = product["credentials_ref"].strip()
                if value:
                    return value
        return None

    def _read_run_plan(self, run_dir: Path) -> dict[str, Any]:
        path = run_dir / "plan.json"
        if not path.exists():
            return {}
        try:
            payload = self._read_json(path)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _resolve_auth_user_data_dir(self, value: str | None, credentials_ref: str | None, url: str) -> Path:
        if value:
            resolved = self._resolve_browser_runtime_path(
                value,
                label="browser_user_data_dir",
                expect_file=False,
            )
            assert resolved is not None
            return Path(resolved)

        name = normalize_ref(credentials_ref) if credentials_ref else slugify(urlparse(url).netloc or url)
        path = (self.workspace_root / ".prodwalk" / "browser-profiles" / name).resolve()
        self._ensure_workspace_path(path, "browser_user_data_dir")
        return path

    def _resolve_auth_storage_state(self, value: str | None, user_data_dir: Path) -> Path:
        if value:
            resolved = self._resolve_browser_runtime_path(
                value,
                label="browser_storage_state",
                expect_file=True,
            )
            assert resolved is not None
            return Path(resolved)

        path = (user_data_dir / "prodwalk_storage_state.json").resolve()
        self._ensure_workspace_path(path, "browser_storage_state")
        if path.exists() and not path.is_file():
            raise ApiError(
                400,
                "BAD_REQUEST",
                "browser_storage_state must be a JSON file path.",
                {"browser_storage_state": str(path)},
            )
        return path

    def _ensure_workspace_path(self, path: Path, label: str) -> None:
        workspace = self.workspace_root.resolve()
        if not path.resolve().is_relative_to(workspace):
            raise ApiError(
                400,
                "BAD_REQUEST",
                f"{label} must stay inside the prodwalk workspace.",
                {label: str(path)},
            )

    def _new_auth_session_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"auth-{timestamp}-{uuid.uuid4().hex[:6]}"

    def _validate_auth_session_id(self, session_id: str) -> None:
        if not re.fullmatch(r"auth-[A-Za-z0-9_.-]+", session_id or ""):
            raise ApiError(
                404,
                "AUTH_SESSION_NOT_FOUND",
                f"Auth session not found: {session_id}",
                {"session_id": session_id},
            )

    def _auth_sessions_dir(self) -> Path:
        path = self.workspace_root / ".prodwalk" / "auth-sessions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _auth_session_path(self, session_id: str) -> Path:
        self._validate_auth_session_id(session_id)
        return self._auth_sessions_dir() / f"{session_id}.json"

    def _write_auth_session_record(self, record: dict[str, Any]) -> None:
        record["auth_status"] = self._auth_status_for_session(record)
        self._auth_sessions[str(record["id"])] = record
        self._write_json(self._auth_session_path(str(record["id"])), record)

    def _read_auth_session_record(self, session_id: str) -> dict[str, Any] | None:
        path = self._auth_session_path(session_id)
        if not path.exists():
            return None
        try:
            payload = self._read_json(path)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        self._auth_sessions[session_id] = dict(payload)
        return dict(payload)

    def _auth_session_record(self, session_id: str) -> dict[str, Any]:
        self._validate_auth_session_id(session_id)
        record = self._auth_sessions.get(session_id) or self._read_auth_session_record(session_id)
        if not record:
            raise ApiError(
                404,
                "AUTH_SESSION_NOT_FOUND",
                f"Auth session not found: {session_id}",
                {"session_id": session_id},
            )
        return record

    def _set_auth_session_status(
        self,
        session_id: str,
        status: str,
        *,
        completed_at: str | None = None,
        message: str | None = None,
    ) -> None:
        record = self._auth_session_record(session_id)
        record["status"] = status
        record["updated_at"] = utc_now()
        if completed_at:
            record["completed_at"] = completed_at
        if message:
            record["message"] = message
        self._write_auth_session_record(record)

    def _set_auth_session_failed(self, session_id: str, exc: Exception, *, status: str) -> None:
        record = self._auth_session_record(session_id)
        now = utc_now()
        record.update(
            {
                "status": status,
                "updated_at": now,
                "completed_at": now,
                "error": self._error_payload(exc),
                "message": self._safe_error_text(str(exc)),
            }
        )
        self._write_auth_session_record(record)

    def _auth_status_for_session(self, record: dict[str, Any]) -> str:
        status = str(record.get("status") or "")
        if status == "succeeded":
            return "auth_ready"
        if status in {"running", "awaiting_user"}:
            return "awaiting_manual_login"
        return "auth_not_ready"

    def _error_payload(self, exc: Exception) -> dict[str, Any]:
        return {"message": self._safe_error_text(str(exc)), "type": type(exc).__name__}

    def _safe_error_text(self, text: str) -> str:
        redacted = re.sub(
            r"https?://[^\s'\"<>]+",
            lambda match: self._safe_url_for_logs(match.group(0)),
            text,
        )
        patterns = [
            r"\b(?:sk|pk)_(?:live|test|prod|uat)?_?[A-Za-z0-9][A-Za-z0-9_\-]{12,}\b",
            r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b",
            r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}",
        ]
        for pattern in patterns:
            redacted = re.sub(pattern, "<redacted>", redacted)
        return redacted

    def _auth_session_detail(self, session_id: str) -> AuthSessionDetail:
        record = self._auth_session_record(session_id)
        return AuthSessionDetail(
            id=str(record["id"]),
            session_id=str(record["session_id"]),
            run_id=record.get("run_id") if isinstance(record.get("run_id"), str) else None,
            status=record.get("status", "failed"),
            auth_status=self._auth_status_for_session(record),
            url=self._safe_url_for_logs(str(record.get("url") or "")),
            credentials_ref=record.get("credentials_ref") if isinstance(record.get("credentials_ref"), str) else None,
            browser_user_data_dir_configured=bool(record.get("browser_user_data_dir_configured")),
            browser_storage_state_configured=bool(record.get("browser_storage_state_configured")),
            storage_state_saved=bool(record.get("storage_state_saved")),
            success_url_contains=[
                str(marker) for marker in record.get("success_url_contains", []) if str(marker).strip()
            ],
            login_url_contains=str(record.get("login_url_contains") or "/auth/login"),
            timeout_sec=float(record.get("timeout_sec") or 300),
            created_at=str(record.get("created_at") or ""),
            updated_at=str(record.get("updated_at") or ""),
            completed_at=record.get("completed_at") if isinstance(record.get("completed_at"), str) else None,
            retry_run_id=record.get("retry_run_id") if isinstance(record.get("retry_run_id"), str) else None,
            error=record.get("error") if isinstance(record.get("error"), dict) else None,
            message=record.get("message") if isinstance(record.get("message"), str) else None,
        )

    async def _close_auth_session(self, session_id: str, *, cancel_timeout: bool = True) -> None:
        handle = self._auth_session_handles.pop(session_id, None)
        if handle is not None:
            try:
                await close_manual_auth_session(handle)
            except Exception:
                pass
        if cancel_timeout:
            self._cancel_auth_session_timeout(session_id)

    def _cancel_auth_session_timeout(self, session_id: str) -> None:
        task = self._auth_session_timeout_tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def _auth_session_timeout(self, session_id: str, timeout_sec: float) -> None:
        try:
            await asyncio.sleep(timeout_sec)
            record = self._auth_session_record(session_id)
            if record.get("status") not in {"running", "awaiting_user"}:
                return
            run_id = record.get("run_id") if isinstance(record.get("run_id"), str) else None
            await self._close_auth_session(session_id, cancel_timeout=False)
            self._set_auth_session_status(
                session_id,
                "timeout",
                completed_at=utc_now(),
                message="Auth session timed out while waiting for manual verification.",
            )
            if run_id:
                self._upsert_agent(run_id, "AuthSession", "failed", completed_at=utc_now())
                await self.append_event(
                    run_id,
                    "auth_session.failed",
                    "Manual auth session timed out",
                    level="warn",
                    agent_id="agent_auth_session",
                    agent_type="auth_session",
                    status="timeout",
                    payload={"session_id": session_id, "timeout_sec": timeout_sec},
                )
                self._persist_auth_session_artifact(run_id, session_id)
        except asyncio.CancelledError:
            return

    def _latest_succeeded_auth_session_id(self, run_id: str) -> str | None:
        candidates: list[dict[str, Any]] = []
        candidates.extend(record for record in self._auth_sessions.values() if record.get("run_id") == run_id)
        for path in self._auth_sessions_dir().glob("auth-*.json"):
            record = self._read_auth_session_record(path.stem)
            if record and record.get("run_id") == run_id:
                candidates.append(record)
        succeeded = [record for record in candidates if record.get("status") == "succeeded"]
        if not succeeded:
            return None
        succeeded.sort(key=lambda record: str(record.get("updated_at") or record.get("created_at") or ""), reverse=True)
        return str(succeeded[0].get("id") or succeeded[0].get("session_id"))

    def _retry_request_from_run(
        self,
        record: dict[str, Any],
        run_dir: Path,
        session: dict[str, Any],
    ) -> RunStartRequest:
        params = record.get("params") if isinstance(record.get("params"), dict) else {}
        plan = self._read_run_plan(run_dir)
        mode = str(record.get("mode") or params.get("mode") or "browser-use")
        if mode not in BROWSER_USE_MODES:
            mode = "browser-use"
        out = self._relative_path(run_dir.parent)
        report_language = str(params.get("report_language") or plan.get("report_language") or "en")
        verification_mode = str(params.get("verification_mode") or "auto")
        return RunStartRequest(
            plan=plan,
            mode=mode,
            out=out,
            concurrency=1,
            report_language=report_language,
            browser_model=params.get("browser_model") if isinstance(params.get("browser_model"), str) else None,
            browser_max_steps=int(params.get("browser_max_steps") or 25),
            browser_timeout_sec=float(params.get("browser_timeout_sec") or 600),
            browser_user_data_dir=str(session["browser_user_data_dir"]),
            browser_storage_state=str(session["browser_storage_state"]),
            browser_discover_all_pages=(
                bool(params["browser_discover_all_pages"])
                if isinstance(params.get("browser_discover_all_pages"), bool)
                else None
            ),
            browser_discovery_max_pages=(
                int(params["browser_discovery_max_pages"])
                if params.get("browser_discovery_max_pages") is not None
                else None
            ),
            browser_discovery_max_depth=(
                int(params["browser_discovery_max_depth"])
                if params.get("browser_discovery_max_depth") is not None
                else None
            ),
            verification_mode=verification_mode if verification_mode in {"auto", "off", "manual"} else "auto",
            verification_timeout_sec=float(params.get("verification_timeout_sec") or session.get("timeout_sec") or 300),
            verification_success_url_contains=[
                str(marker)
                for marker in params.get("verification_success_url_contains", session.get("success_url_contains", []))
                if str(marker).strip()
            ],
            verification_login_url_contains=str(
                params.get("verification_login_url_contains") or session.get("login_url_contains") or "/auth/login"
            ),
        )

    def _merge_run_metadata(self, run_id: str, metadata: dict[str, Any]) -> None:
        state = self._state_for_run(run_id)
        current = state["run"].get("metadata")
        merged = dict(current) if isinstance(current, dict) else {}
        merged.update({key: value for key, value in metadata.items() if value is not None})
        self._update_run(run_id, metadata=merged)

    def _persist_auth_session_artifact(self, run_id: str, session_id: str) -> None:
        run_dir = self._run_dir_for_id(run_id)
        session_dir = run_dir / "auth-sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        rel_path = f"auth-sessions/{session_id}.json"
        detail = self._auth_session_detail(session_id)
        payload = detail.model_dump() if hasattr(detail, "model_dump") else detail.dict()
        payload["security_note"] = (
            "This auth-session artifact intentionally omits credentials and local profile paths. "
            "Login-page screenshots may still contain account identifiers; avoid sharing them externally."
        )
        self._write_json(session_dir / f"{session_id}.json", payload)
        artifact = {
            "id": self._artifact_id_for_path("art_auth_session", rel_path),
            "run_id": run_id,
            "type": "log_text",
            "title": f"{session_id}.json",
            "path": rel_path,
            "media_type": "application/json",
            "size_bytes": (session_dir / f"{session_id}.json").stat().st_size,
            "created_at": self._mtime_iso(session_dir / f"{session_id}.json"),
            "metadata": {
                "content_url": f"/api/runs/{run_id}/artifacts/{self._artifact_id_for_path('art_auth_session', rel_path)}/content",
                "path_url": f"/api/runs/{run_id}/artifacts/{quote(rel_path, safe='/')}",
            },
        }
        artifacts_path = run_dir / "artifacts.json"
        existing: list[dict[str, Any]] = []
        if artifacts_path.exists():
            try:
                payload_existing = self._read_json(artifacts_path)
                if isinstance(payload_existing, list):
                    existing = [item for item in payload_existing if isinstance(item, dict)]
            except Exception:
                existing = []
        merged = [item for item in existing if item.get("id") != artifact["id"]]
        merged.append(artifact)
        self._write_json(artifacts_path, merged)
        state = self._state_for_run(run_id)
        known_ids = [str(item.get("id")) for item in merged if item.get("id")]
        state["run"]["artifact_ids"] = known_ids
        self._write_json(run_dir / "run.json", state["run"])

    def _safe_url_for_logs(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    def _resolve_request_plan(self, request: RunStartRequest) -> PlanBundle:
        inline = request.plan or (request.config if isinstance(request.config, dict) else None)
        identifiers = [
            request.plan_name,
            request.config_path,
            request.config if isinstance(request.config, str) else None,
        ]
        provided = [item for item in identifiers if item]
        target_fields = [request.target_url, request.target_name, request.target_credentials_ref]
        target_requested = any(str(item or "").strip() for item in target_fields)
        if target_requested and (inline or provided):
            raise ApiError(400, "BAD_REQUEST", "Pass either target_url or a local/inline plan, not both.")
        if target_requested and not str(request.target_url or "").strip():
            raise ApiError(400, "BAD_REQUEST", "target_url is required when target fields are provided.")
        if target_requested:
            return self._build_target_url_plan(request)
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
            raise ApiError(400, "BAD_REQUEST", "config, config_path, plan_name, plan, or target_url is required.")
        return self._load_plan_from_name(str(provided[0]))

    def _build_target_url_plan(self, request: RunStartRequest) -> PlanBundle:
        target_url = self._normalize_target_url(request.target_url)
        target_name = self._target_name_for_url(target_url, request.target_name)
        credentials_ref = str(request.target_credentials_ref or "").strip() or None

        raw: dict[str, Any] = {
            "research_goal": f"对 {target_name} 进行一次全量产品走查，发现可复现问题并提出产品改进建议。",
            "report_language": "zh",
            "products": [
                {
                    "name": target_name,
                    "url": target_url,
                    "kind": "owned",
                    "credentials_ref": credentials_ref,
                    "notes": "由控制台 URL 一键走查自动生成。",
                    "tags": ["url-full-site", "auto-generated"],
                }
            ],
            "scenarios": [
                {
                    "id": "full-site-walkthrough",
                    "title": "全量只读产品走查",
                    "persona": "产品经理和真实用户",
                    "goal": (
                        "从入口 URL 出发，自动发现同站页面和核心路径，复核可访问性、信息架构、"
                        "关键操作、异常状态和转化阻塞。"
                    ),
                    "steps": [
                        "打开目标网站入口页，记录首屏、导航结构和核心入口。",
                        "自动发现并访问同域可达页面，优先覆盖主导航、页脚、列表、详情、登录注册、定价、设置和帮助区域。",
                        "检查每个页面的加载错误、空态/异常态、表单校验、按钮可用性、文案一致性和桌面/移动适配风险。",
                        "遇到登录、支付、删除、发送消息或修改数据等动作时，只记录入口、阻塞和风险，不提交破坏性或不可逆操作。",
                        "汇总问题、影响范围、优先级、复现步骤、证据截图和产品改进建议。",
                    ],
                    "success_criteria": [
                        "生成覆盖主要同站页面的地图、证据和报告。",
                        "报告按优先级给出问题、复现步骤、预期行为和验收标准。",
                        "全程保持只读，不执行破坏性或不可逆操作。",
                    ],
                    "observation_points": [
                        "页面是否可访问、可理解、可继续操作。",
                        "核心路径是否存在断点、误导、重复劳动或反馈缺失。",
                        "表单、导航、按钮、链接、空态、错误态和权限态是否符合真实用户预期。",
                        "报告中每个问题是否有页面、证据和可落地建议。",
                    ],
                    "risk_level": "high",
                }
            ],
            "evaluation": {"min_evidence_per_result": 1},
        }
        try:
            plan = parse_research_plan(raw)
        except ConfigError as exc:
            raise ApiError(400, "PLAN_INVALID", str(exc)) from exc

        request.target_url = target_url
        request.target_name = target_name
        request.target_credentials_ref = credentials_ref
        bundle_name = f"{slugify(target_name)}-full-site"
        return PlanBundle(id="target-url", name=bundle_name, path=None, plan=plan, raw=raw)

    def _normalize_target_url(self, value: str | None) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise ApiError(400, "BAD_REQUEST", "target_url is required.")
        if re.search(r"\s", raw):
            raise ApiError(400, "BAD_REQUEST", "target_url must not contain whitespace.", {"target_url": value})

        has_explicit_scheme = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw) is not None
        scheme_like = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(.*)$", raw)
        if scheme_like and not has_explicit_scheme and not re.match(r"^\d+(?:/|$)", scheme_like.group(2)):
            raise ApiError(400, "BAD_REQUEST", "target_url must use http or https.", {"target_url": value})
        candidate = raw if has_explicit_scheme else f"https://{raw}"
        parsed = urlparse(candidate)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ApiError(400, "BAD_REQUEST", "target_url must use http or https.", {"target_url": value})
        if not parsed.netloc or not parsed.hostname:
            raise ApiError(400, "BAD_REQUEST", "target_url must include a valid host.", {"target_url": value})
        try:
            parsed.port
        except ValueError as exc:
            raise ApiError(400, "BAD_REQUEST", "target_url must include a valid host.", {"target_url": value}) from exc
        if parsed.username or parsed.password:
            raise ApiError(
                400,
                "BAD_REQUEST",
                "target_url must not include username or password credentials.",
                {"target_url": self._safe_url_for_logs(candidate)},
            )

        return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

    def _target_name_for_url(self, target_url: str, override: str | None) -> str:
        explicit = str(override or "").strip()
        if explicit:
            return explicit
        host = urlparse(target_url).hostname or target_url
        if host.startswith("www."):
            host = host[4:]
        return host or "target-site"

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

    def _request_params(self, request: RunStartRequest, *, options: RunExecutionOptions) -> dict[str, Any]:
        is_browser_use = options.mode in BROWSER_USE_MODES
        return {
            "mode": options.mode,
            "concurrency": options.concurrency,
            "report_language": options.report_language,
            "plan_source": "target_url" if request.target_url else "plan",
            "target_url": request.target_url,
            "target_name": request.target_name,
            "target_credentials_ref": request.target_credentials_ref,
            "browser_model": request.browser_model,
            "browser_max_steps": request.browser_max_steps,
            "browser_timeout_sec": request.browser_timeout_sec,
            "browser_discover_all_pages": (
                request.browser_discover_all_pages
                if request.browser_discover_all_pages is not None
                else DEFAULT_DISCOVER_ALL_PAGES if is_browser_use else None
            ),
            "browser_discovery_max_pages": (
                request.browser_discovery_max_pages
                if request.browser_discovery_max_pages is not None
                else DEFAULT_DISCOVERY_MAX_PAGES if is_browser_use else None
            ),
            "browser_discovery_max_depth": (
                request.browser_discovery_max_depth
                if request.browser_discovery_max_depth is not None
                else DEFAULT_DISCOVERY_MAX_DEPTH if is_browser_use else None
            ),
            "browser_user_data_dir_configured": options.browser_user_data_dir is not None,
            "browser_storage_state_configured": options.browser_storage_state is not None,
            "auth_session_id": options.auth_session_id,
            "auth_status": "auth_ready" if options.auth_session_id else "auth_not_ready",
            "verification_mode": options.verification_mode,
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
            record = self._normalize_run_record(dict(state["run"]))
            return self._reconcile_browser_use_terminal_status(run_id, Path(state["run_dir"]), record)
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
                    record = self._normalize_run_record(payload)
                    return self._reconcile_browser_use_terminal_status(run_dir.name, run_dir, record)
            except Exception:
                return None
        return self._infer_run_record(run_dir)

    def _normalize_run_record(self, record: dict[str, Any]) -> dict[str, Any]:
        if record.get("status") != "awaiting_verification":
            return record
        normalized = dict(record)
        progress = normalized.get("progress") if isinstance(normalized.get("progress"), dict) else {}
        normalized["progress"] = self._progress_for_awaiting_verification(progress)
        normalized["completed_at"] = None
        return normalized

    def _reconcile_browser_use_terminal_status(
        self,
        run_id: str,
        run_dir: Path,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        if str(record.get("status") or "") != "timeout":
            return record
        mode = str(record.get("mode") or record.get("params", {}).get("mode") or "")
        if mode not in BROWSER_USE_MODES:
            return record
        final_status, _ = self._final_status_from_evidence(run_id, run_dir, record=record)
        if final_status != "succeeded":
            return record
        reconciled = dict(record)
        reconciled["status"] = "succeeded"
        reconciled["error"] = None
        return reconciled

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
                **self._issue_count_fields(run_dir / "issues.json"),
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
            metadata=record.get("metadata", {}) if isinstance(record.get("metadata"), dict) else {},
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
                    "metrics": self._merge_metrics(item.get("metrics"), metrics),
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

    def _merge_metrics(self, current: Any, updates: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(current) if isinstance(current, dict) else {}
        if updates:
            merged.update(updates)
        return merged

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

    def _stage_label(self, agent: str | None, run_id: str | None = None) -> str:
        if agent == "BrowserWalker" and run_id and self._is_browser_use_run(run_id):
            return "Browser-use walkthrough"
        return PIPELINE_STAGE_LABELS.get(agent or "", agent or "Run")

    def _stage_key(self, agent: str | None) -> str:
        return self._agent_type(agent) or "run"

    def _is_browser_use_run(self, run_id: str) -> bool:
        try:
            record = self._record_for_run(run_id)
        except ApiError:
            return False
        mode = str(record.get("mode") or record.get("params", {}).get("mode") or "")
        return mode in BROWSER_USE_MODES

    def _progress_with_runtime_context(
        self,
        run_id: str,
        *,
        base_progress: dict[str, Any] | None = None,
        stage_key: str | None = None,
        stage_label: str | None = None,
        stage_started_at: str | None = None,
        event_time: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        try:
            record = self._record_for_run(run_id)
        except ApiError:
            record = {}
        progress = dict(record.get("progress")) if isinstance(record.get("progress"), dict) else {}
        if base_progress:
            progress.update(base_progress)

        run_started_at = record.get("started_at") if isinstance(record.get("started_at"), str) else None
        run_created_at = record.get("created_at") if isinstance(record.get("created_at"), str) else None
        event_time = event_time or utc_now()
        stage_started_at = (
            stage_started_at
            or (progress.get("stage_started_at") if isinstance(progress.get("stage_started_at"), str) else None)
            or run_started_at
            or run_created_at
        )

        completed_stage_count = self._completed_stage_count(run_id)
        scenario_count = max(0, int(progress.get("total_scenarios") or 0))
        total_stage_count = max(
            int(progress.get("total_stage_count") or 0),
            scenario_count + PIPELINE_FIXED_STAGE_COUNT,
            completed_stage_count,
        )
        artifact_counts = self._artifact_count_fields(run_id)
        evidence_counts = self._evidence_count_fields(run_id)
        elapsed_ms = self._elapsed_ms(run_started_at or run_created_at, event_time)
        stage_elapsed_ms = self._elapsed_ms(stage_started_at, event_time)

        progress.update(
            {
                "current_stage": stage_key or progress.get("current_stage"),
                "current_stage_label": stage_label or progress.get("current_stage_label"),
                "current_stage_status": status or progress.get("current_stage_status"),
                "stage_started_at": stage_started_at,
                "elapsed_ms": elapsed_ms,
                "elapsed_sec": round(elapsed_ms / 1000, 3),
                "stage_elapsed_ms": stage_elapsed_ms,
                "stage_elapsed_sec": round(stage_elapsed_ms / 1000, 3),
                "completed_stage_count": completed_stage_count,
                "total_stage_count": total_stage_count,
                **evidence_counts,
                **artifact_counts,
            }
        )
        return progress

    def _event_progress_fields(
        self,
        run_id: str,
        *,
        agent: str | None = None,
        stage_key: str | None = None,
        base_progress: dict[str, Any] | None = None,
        stage_label: str | None = None,
        stage_started_at: str | None = None,
        event_time: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        progress = self._progress_with_runtime_context(
            run_id,
            base_progress=base_progress,
            stage_key=stage_key if stage_key is not None else self._stage_key(agent),
            stage_label=stage_label or self._stage_label(agent, run_id),
            stage_started_at=stage_started_at,
            event_time=event_time,
            status=status,
        )
        return {
            "stage": progress.get("current_stage"),
            "stage_label": progress.get("current_stage_label"),
            "started_at": progress.get("stage_started_at"),
            "stage_started_at": progress.get("stage_started_at"),
            "elapsed_ms": progress.get("elapsed_ms", 0),
            "elapsed_sec": progress.get("elapsed_sec", 0.0),
            "stage_elapsed_ms": progress.get("stage_elapsed_ms", 0),
            "stage_elapsed_sec": progress.get("stage_elapsed_sec", 0.0),
            "completed_stage_count": progress.get("completed_stage_count", 0),
            "total_stage_count": progress.get("total_stage_count", 0),
            "evidence_count": progress.get("evidence_count", 0),
            "issue_count": progress.get("issue_count", 0),
            "high_issue_count": progress.get("high_issue_count", 0),
            "artifact_count": progress.get("artifact_count", 0),
            "screenshot_count": progress.get("screenshot_count", 0),
            "browser_history_count": progress.get("browser_history_count", 0),
            "progress": progress,
        }

    def _agent_progress_metrics(
        self,
        run_id: str,
        *,
        agent: str | None = None,
        stage_started_at: str | None = None,
        completed_at: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        fields = self._event_progress_fields(
            run_id,
            agent=agent,
            stage_started_at=stage_started_at,
            event_time=completed_at,
            status=status,
        )
        metrics = {key: value for key, value in fields.items() if key != "progress"}
        if stage_started_at and completed_at:
            metrics["agent_elapsed_ms"] = self._elapsed_ms(stage_started_at, completed_at)
            metrics["agent_elapsed_sec"] = round(metrics["agent_elapsed_ms"] / 1000, 3)
        return metrics

    def _browser_use_start_fields(self, run_id: str, agent: str | None) -> dict[str, Any]:
        if agent != "BrowserWalker" or not self._is_browser_use_run(run_id):
            return {}
        try:
            record = self._record_for_run(run_id)
        except ApiError:
            record = {}
        params = record.get("params") if isinstance(record.get("params"), dict) else {}
        return {
            "stage_label": "Browser-use walkthrough",
            "action": "Starting browser-use walker",
            "max_steps": int(params.get("browser_max_steps") or 0),
            "timeout_sec": float(params.get("browser_timeout_sec") or 0),
        }

    def _browser_use_completion_fields(
        self,
        run_id: str,
        agent: str | None,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if agent != "BrowserWalker" or not self._is_browser_use_run(run_id):
            return {}
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        browser_steps = metrics.get("browser_steps", data.get("browser_steps"))
        if browser_steps is None:
            browser_steps = metrics.get("step_count", data.get("step_count"))
        timed_out = metrics.get("timed_out", data.get("timed_out"))
        fields: dict[str, Any] = {
            "action": "Browser-use walker finished",
            "browser_steps": int(browser_steps or 0),
            "timed_out": bool(timed_out),
            "result_status": data.get("result_status"),
            "error_count": len(data.get("errors") or []) if isinstance(data.get("errors"), list) else 0,
        }
        fields.update(self._artifact_count_fields(run_id))
        if "evidence_count" in data:
            fields["evidence_count"] = data["evidence_count"]
        return fields

    def _agent_started_at(
        self,
        run_id: str,
        agent: str | None,
        product: str | None = None,
        scenario_id: str | None = None,
    ) -> str | None:
        agent_id = self._agent_id(agent, product, scenario_id)
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "agents.json"
        if not path.exists():
            return None
        try:
            payload = self._read_json(path)
        except Exception:
            return None
        if not isinstance(payload, list):
            return None
        for item in payload:
            if isinstance(item, dict) and item.get("id") == agent_id and isinstance(item.get("started_at"), str):
                return item["started_at"]
        return None

    def _completed_stage_count(self, run_id: str) -> int:
        run_dir = self._run_dir_for_id(run_id)
        path = run_dir / "agents.json"
        if not path.exists():
            return 0
        try:
            payload = self._read_json(path)
        except Exception:
            return 0
        if not isinstance(payload, list):
            return 0
        return sum(
            1
            for item in payload
            if isinstance(item, dict)
            and item.get("type") != "director"
            and str(item.get("status") or "") in AGENT_TERMINAL_STATUSES
        )

    def _artifact_count_fields(self, run_id: str, artifacts: list[dict[str, Any]] | None = None) -> dict[str, int]:
        if artifacts is None:
            try:
                artifacts = self._build_artifacts(run_id, self._run_dir_for_id(run_id))
            except ApiError:
                artifacts = []
        return {
            "artifact_count": len(artifacts),
            "screenshot_count": sum(1 for artifact in artifacts if artifact.get("type") == "screenshot"),
            "browser_history_count": sum(1 for artifact in artifacts if artifact.get("type") == "browser_history"),
        }

    def _evidence_count_fields(self, run_id: str) -> dict[str, int]:
        try:
            path = self._run_dir_for_id(run_id) / "evidence.json"
        except ApiError:
            return {"evidence_count": 0, "result_count": 0, "issue_count": 0, "high_issue_count": 0}
        if not path.exists():
            return {"evidence_count": 0, "result_count": 0, "issue_count": 0, "high_issue_count": 0}
        try:
            payload = self._read_json(path)
        except Exception:
            return {"evidence_count": 0, "result_count": 0, "issue_count": 0, "high_issue_count": 0}
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        issue_counts = self._issue_count_fields(path.with_name("issues.json"))
        return {"evidence_count": len(evidence), "result_count": len(results), **issue_counts}

    def _issue_count_fields(self, path: Path) -> dict[str, int]:
        if not path.exists():
            return {"issue_count": 0, "high_issue_count": 0}
        try:
            payload = self._read_json(path)
        except Exception:
            return {"issue_count": 0, "high_issue_count": 0}
        issues = payload.get("issues") if isinstance(payload, dict) and isinstance(payload.get("issues"), list) else []
        return {
            "issue_count": len(issues),
            "high_issue_count": sum(
                1
                for issue in issues
                if isinstance(issue, dict)
                and (
                    str(issue.get("severity") or "").lower() == "high"
                    or str(issue.get("priority") or "").upper() in {"P0", "P1"}
                )
            ),
        }

    def _elapsed_ms(self, started_at: str | None, ended_at: str | None = None) -> int:
        start = self._parse_iso_datetime(started_at)
        if start is None:
            return 0
        end = self._parse_iso_datetime(ended_at) or datetime.now(timezone.utc)
        return max(0, int((end - start).total_seconds() * 1000))

    def _parse_iso_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
        return slug or "item"

    def _progress_from_evidence(self, path: Path) -> dict[str, int]:
        if not path.exists():
            return {
                "total_scenarios": 0,
                "completed_scenarios": 0,
                "failed_scenarios": 0,
                "issue_count": 0,
                "high_issue_count": 0,
            }
        try:
            payload = self._read_json(path)
        except Exception:
            return {
                "total_scenarios": 0,
                "completed_scenarios": 0,
                "failed_scenarios": 0,
                "issue_count": 0,
                "high_issue_count": 0,
            }
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        return {
            "total_scenarios": len(results),
            "completed_scenarios": sum(
                1 for result in results if isinstance(result, dict) and result.get("status") == "completed"
            ),
            "failed_scenarios": sum(
                1 for result in results if isinstance(result, dict) and result.get("status") != "completed"
            ),
            **self._issue_count_fields(path.with_name("issues.json")),
        }

    def _progress_for_awaiting_verification(self, progress: dict[str, Any]) -> dict[str, Any]:
        total = max(0, int(progress.get("total_scenarios") or 0))
        completed = max(0, int(progress.get("completed_scenarios") or 0))
        failed = max(0, int(progress.get("failed_scenarios") or 0))
        if total > 0 and completed >= total:
            completed = max(0, total - 1)
        adjusted = dict(progress)
        adjusted.update(
            {
                "total_scenarios": total,
                "completed_scenarios": completed,
                "failed_scenarios": failed,
            }
        )
        return adjusted

    def _postprocess_run_outputs(self, run_id: str, run_dir: Path) -> None:
        try:
            record = self._record_for_run(run_id)
        except ApiError:
            return
        mode = str(record.get("mode") or record.get("params", {}).get("mode") or "")
        if mode in BROWSER_USE_MODES:
            history_map = self._archive_browser_histories(run_dir)
            self._sanitize_browser_use_evidence_file(run_dir, history_map)
        self._ensure_walkthrough_map(run_id, run_dir)

    def _ensure_walkthrough_map(
        self,
        run_id: str,
        run_dir: Path,
        *,
        raise_on_missing_evidence: bool = False,
    ) -> dict[str, Any] | None:
        map_path = run_dir / "walkthrough_map.json"
        if map_path.exists():
            try:
                payload = self._read_json(map_path)
            except Exception:
                payload = None
            if isinstance(payload, dict) and payload.get("build_version") == WALKTHROUGH_MAP_BUILD_VERSION:
                return payload

        evidence_path = run_dir / "evidence.json"
        if not evidence_path.exists():
            if raise_on_missing_evidence:
                raise ApiError(
                    404,
                    "ARTIFACT_NOT_FOUND",
                    "walkthrough_map.json cannot be rebuilt because evidence.json is missing.",
                    {"run_id": run_id},
                )
            return None

        try:
            payload = self._build_walkthrough_map(run_id, run_dir)
        except ApiError:
            if raise_on_missing_evidence:
                raise
            return None
        except Exception as exc:  # noqa: BLE001 - map generation should not fail the run finalization path.
            if raise_on_missing_evidence:
                raise ApiError(
                    500,
                    "MAP_BUILD_FAILED",
                    f"walkthrough_map.json could not be generated: {exc}",
                    {"run_id": run_id},
                ) from exc
            return None
        self._write_json(map_path, payload)
        return payload

    def _build_walkthrough_map(self, run_id: str, run_dir: Path) -> dict[str, Any]:
        evidence_path = run_dir / "evidence.json"
        if not evidence_path.exists():
            raise ApiError(404, "ARTIFACT_NOT_FOUND", "evidence.json is not available yet.", {"run_id": run_id})
        evidence_payload = self._read_json(evidence_path)
        if not isinstance(evidence_payload, dict):
            raise ApiError(500, "MAP_BUILD_FAILED", "evidence.json is not a JSON object.", {"run_id": run_id})
        artifacts = self._map_artifacts_with_page_evidence_payloads(run_dir, self._build_artifacts(run_id, run_dir))
        browser_histories = self._browser_history_sources(run_id, run_dir, artifacts)
        return build_walkthrough_map(
            run_id=run_id,
            evidence_payload=evidence_payload,
            artifacts=artifacts,
            browser_histories=browser_histories,
        )

    def _map_artifacts_with_page_evidence_payloads(
        self,
        run_dir: Path,
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for artifact in artifacts:
            item = dict(artifact)
            payload = self._page_evidence_artifact_payload(run_dir, item)
            if payload is not None:
                item["payload"] = payload
            enriched.append(item)
        return enriched

    def _page_evidence_artifact_payload(self, run_dir: Path, artifact: dict[str, Any]) -> Any | None:
        artifact_type = artifact.get("type")
        if artifact_type not in {"page_evidence_manifest", "page_html", "page_text", "page_elements", "dom_snapshot", "accessibility_tree"}:
            return None
        rel_path = artifact.get("path")
        if not isinstance(rel_path, str) or not rel_path:
            return None
        try:
            path = self._resolve_run_relative_path(run_dir, rel_path)
        except ApiError:
            return None
        if not path.is_file() or path.stat().st_size > 512_000:
            return None
        try:
            if path.suffix.lower() == ".json":
                payload = self._read_json(path)
            else:
                payload = {"text": path.read_text(encoding="utf-8", errors="replace")[:4000]}
        except Exception:
            return None
        return self._sanitize_browser_use_value(payload, {})

    def _browser_history_sources(
        self,
        run_id: str,
        run_dir: Path,
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for artifact in artifacts:
            if artifact.get("type") != "browser_history":
                continue
            rel_path = artifact.get("path")
            if not isinstance(rel_path, str) or not rel_path:
                continue
            try:
                path = self._resolve_run_relative_path(run_dir, rel_path)
            except ApiError:
                continue
            if not path.exists() or not path.is_file():
                continue
            try:
                payload = self._read_json(path)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            sources.append(
                {
                    "artifact_id": str(artifact.get("id") or self._artifact_id_for_path("art_browser_history", rel_path)),
                    "path": rel_path,
                    "payload": payload,
                }
            )
        return sources

    def _archive_browser_histories(self, run_dir: Path) -> dict[str, str]:
        evidence_path = run_dir / "evidence.json"
        if not evidence_path.exists():
            return {}
        try:
            payload = self._read_json(evidence_path)
        except Exception:
            return {}

        refs = self._collect_history_refs(payload)
        if not refs:
            return {}

        history_dir = run_dir / "browser-history"
        history_map: dict[str, str] = {}
        for ref in refs:
            source = self._history_source_path(ref, run_dir)
            if source is None:
                continue
            history_dir.mkdir(parents=True, exist_ok=True)
            filename = self._unique_filename(source.name or "browser-use-history.json", history_dir)
            target = (history_dir / filename).resolve()
            try:
                if source.resolve() != target:
                    shutil.copy2(source, target)
                self._sanitize_json_file(target)
            except Exception:
                continue
            rel_path = target.relative_to(run_dir.resolve()).as_posix()
            for key in {ref, ref.replace("\\", "/"), str(source), str(source.resolve()), str(source.resolve()).replace("\\", "/")}:
                history_map[key] = rel_path
        return history_map

    def _collect_history_refs(self, value: Any) -> list[str]:
        refs: list[str] = []

        def visit(item: Any) -> None:
            if isinstance(item, dict):
                history_file = item.get("history_file")
                if isinstance(history_file, str) and history_file.strip():
                    refs.append(history_file)
                for child in item.values():
                    visit(child)
            elif isinstance(item, list):
                for child in item:
                    visit(child)

        visit(value)
        seen: set[str] = set()
        unique: list[str] = []
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            unique.append(ref)
        return unique

    def _history_source_path(self, ref: str, run_dir: Path) -> Path | None:
        candidate = Path(ref).expanduser()
        candidates = [candidate] if candidate.is_absolute() else [run_dir / candidate, self.workspace_root / candidate, Path.cwd() / candidate]
        for path in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved.is_file():
                return resolved
        return None

    def _sanitize_json_file(self, path: Path) -> None:
        try:
            payload = self._read_json(path)
        except Exception:
            return
        sanitized = self._sanitize_browser_use_value(payload, {})
        self._write_json(path, sanitized)

    def _sanitize_browser_use_evidence_file(self, run_dir: Path, history_map: dict[str, str]) -> None:
        evidence_path = run_dir / "evidence.json"
        if not evidence_path.exists():
            return
        try:
            payload = self._read_json(evidence_path)
        except Exception:
            return
        sanitized = self._sanitize_browser_use_value(payload, history_map)
        self._write_json(evidence_path, sanitized)

    def _sanitize_browser_use_value(self, value: Any, history_map: dict[str, str]) -> Any:
        if isinstance(value, list):
            return [self._sanitize_browser_use_value(item, history_map) for item in value]
        if not isinstance(value, dict):
            return value

        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered == "history_file":
                rel_path = self._history_artifact_ref(item, history_map)
                if rel_path:
                    sanitized["browser_history_path"] = rel_path
                    sanitized["browser_history_artifact_id"] = self._artifact_id_for_path("art_browser_history", rel_path)
                continue
            if lowered in {"screenshot", "screenshot_path"}:
                safe_ref = self._safe_run_artifact_ref(item, allowed_prefix="screenshots")
                if safe_ref:
                    sanitized[key_text] = safe_ref
                continue
            if lowered == "screenshot_paths":
                if isinstance(item, list):
                    safe_refs = [
                        safe_ref
                        for raw in item
                        if (safe_ref := self._safe_run_artifact_ref(raw, allowed_prefix="screenshots"))
                    ]
                    if safe_refs:
                        sanitized[key_text] = safe_refs
                continue
            if lowered in PAGE_EVIDENCE_PATH_KEYS:
                safe_ref = self._safe_run_artifact_ref(item, allowed_prefix="page-evidence")
                if safe_ref:
                    sanitized[key_text] = safe_ref
                continue
            if lowered in PAGE_EVIDENCE_PATH_LIST_KEYS:
                if isinstance(item, list):
                    safe_refs = [
                        safe_ref
                        for raw in item
                        if (safe_ref := self._safe_run_artifact_ref(raw, allowed_prefix="page-evidence"))
                    ]
                    if safe_refs:
                        sanitized[key_text] = safe_refs
                continue
            if lowered in SENSITIVE_DATA_KEYS:
                continue
            if any(marker in lowered for marker in ("secret", "token", "credential", "password", "api_key")):
                sanitized[key_text] = "<redacted>"
                continue
            sanitized[key_text] = self._sanitize_browser_use_value(item, history_map)
        return sanitized

    def _history_artifact_ref(self, value: Any, history_map: dict[str, str]) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        ref = value.strip()
        for key in (ref, ref.replace("\\", "/")):
            if key in history_map:
                return history_map[key]
        name = Path(ref).name
        for source, rel_path in history_map.items():
            if Path(source).name == name:
                return rel_path
        return self._safe_run_artifact_ref(ref, allowed_prefix="browser-history")

    def _safe_run_artifact_ref(self, value: Any, *, allowed_prefix: str) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip().replace("\\", "/")
        parsed = PurePosixPath(normalized)
        parts = parsed.parts
        if parsed.is_absolute() or not parts or parts[0] != allowed_prefix:
            return None
        if any(part in {"", ".", ".."} or ":" in part for part in parts):
            return None
        return parsed.as_posix()

    def _unique_filename(self, preferred: str, directory: Path) -> str:
        candidate = Path(preferred).name or "artifact.json"
        stem = Path(candidate).stem or "artifact"
        suffix = Path(candidate).suffix or ".json"
        index = 2
        while (directory / candidate).exists():
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        return candidate

    def _final_status_from_evidence(
        self,
        run_id: str,
        run_dir: Path,
        *,
        record: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        record = dict(record) if record is not None else self._record_for_run(run_id)
        mode = str(record.get("mode") or record.get("params", {}).get("mode") or "")
        if mode not in BROWSER_USE_MODES:
            return "succeeded", None
        evidence_path = run_dir / "evidence.json"
        if not evidence_path.exists():
            return "failed", {"message": "browser-use run did not produce evidence.json", "type": "failed"}
        try:
            payload = self._read_json(evidence_path)
        except Exception as exc:  # noqa: BLE001
            return "failed", {"message": f"browser-use evidence.json could not be read: {exc}", "type": "failed"}

        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        if not results:
            return "failed", {"message": "browser-use run produced no walkthrough results", "type": "failed"}

        text = self._browser_status_text(payload)
        lower_text = text.lower()
        if self._browser_results_timed_out(results) or self._browser_text_timeout_signal(lower_text):
            return "timeout", {"message": "One or more browser-use walkthroughs timed out.", "type": "timeout"}

        verification_mode = str(record.get("params", {}).get("verification_mode") or "off")
        verification_signal = self._browser_manual_verification_signal(payload, record.get("params", {}))
        if verification_mode != "off" and verification_signal is not None:
            return (
                "awaiting_verification",
                {
                    "message": "Browser-use reported that manual verification is required.",
                    "type": "awaiting_verification",
                    "details": verification_signal,
                },
            )

        if any(result.get("status") == "failed" for result in results if isinstance(result, dict)) or any(
            marker in lower_text
            for marker in (
                "browser-use run failed:",
                "browser-use is not installed",
                "required for local openai-compatible runs",
                "unsupported browser_use",
            )
        ):
            return "failed", {"message": "One or more browser-use walkthroughs failed.", "type": "failed"}

        if any(result.get("status") == "blocked" for result in results if isinstance(result, dict)):
            return "blocked", {"message": "One or more browser-use walkthroughs are blocked.", "type": "blocked"}
        return "succeeded", None

    def _browser_manual_verification_signal(
        self,
        payload: dict[str, Any],
        params: Any,
    ) -> dict[str, Any] | None:
        params = params if isinstance(params, dict) else {}
        text = self._browser_status_text(payload)
        lower_text = text.lower()

        manual_signal = self._manual_verification_text_signal(lower_text)
        if manual_signal:
            return manual_signal

        success_seen = self._verification_success_seen(payload, params, lower_text)
        login_url_signal = self._browser_login_url_signal(payload, params, lower_text)
        if login_url_signal and not success_seen:
            return login_url_signal

        login_text_signal = self._browser_login_text_signal(lower_text)
        if login_text_signal and not success_seen:
            return login_text_signal

        return None

    def _manual_verification_text_signal(self, lower_text: str) -> dict[str, Any] | None:
        key_pattern = r"['\"]?manual[_\s-]?verification[_\s-]?required['\"]?"
        true_pattern = rf"{key_pattern}\s*[:=]\s*(?:true|yes|1|required)\b"
        if re.search(true_pattern, lower_text):
            return {"signal": "manual_verification_required"}

        false_pattern = rf"{key_pattern}\s*[:=]\s*(?:false|no|0)\b"
        if re.search(false_pattern, lower_text):
            return None

        if "manual_verification_required" in lower_text or re.search(
            r"\bmanual\s+verification\s+(?:is\s+)?required\b",
            lower_text,
        ):
            return {"signal": "manual_verification_required"}
        return None

    def _browser_challenge_text_signal(self, lower_text: str) -> dict[str, Any] | None:
        challenge_patterns = {
            "captcha": r"\b(?:captcha|hcaptcha|recaptcha|altcha)\b",
            "mfa": r"\b(?:mfa|2fa|two[-\s]?factor|multi[-\s]?factor|one[-\s]?time\s+passcode|otp)\b",
        }
        for signal, pattern in challenge_patterns.items():
            if re.search(pattern, lower_text):
                return {"signal": signal}
        return None

    def _browser_login_url_signal(
        self,
        payload: dict[str, Any],
        params: dict[str, Any],
        lower_text: str,
    ) -> dict[str, Any] | None:
        marker = str(params.get("verification_login_url_contains") or "").strip().lower()
        if not marker:
            return None
        for url in self._browser_observed_urls(payload):
            if marker in url.lower():
                return {"signal": "login_url", "verification_login_url_contains": marker}
        if marker in lower_text:
            return {"signal": "login_url", "verification_login_url_contains": marker}
        return None

    def _browser_login_text_signal(self, lower_text: str) -> dict[str, Any] | None:
        login_patterns = (
            r"\b(?:login|log\s+in|sign\s+in|signin)\s+(?:is\s+)?(?:required|needed|blocked|failed)\b",
            r"\b(?:required|needed)\s+to\s+(?:login|log\s+in|sign\s+in)\b",
            r"\b(?:redirected|sent|returned)\s+(?:back\s+)?to\s+(?:the\s+)?(?:login|log\s+in|sign\s+in)(?:\s+page)?\b",
            r"\b(?:login|log\s+in|sign\s+in|signin)\s+(?:page|screen|form)\b",
            r"\blogin\s+did\s+not\s+complete\b",
        )
        for pattern in login_patterns:
            if re.search(pattern, lower_text):
                return {"signal": "login_required"}
        return None

    def _verification_success_seen(
        self,
        payload: dict[str, Any],
        params: dict[str, Any],
        lower_text: str,
    ) -> bool:
        raw_markers = params.get("verification_success_url_contains")
        if isinstance(raw_markers, str):
            markers = [raw_markers]
        elif isinstance(raw_markers, list):
            markers = [str(marker) for marker in raw_markers if str(marker).strip()]
        else:
            markers = []
        if not markers:
            return False

        observed_urls = [url.lower() for url in self._browser_observed_urls(payload)]
        for marker in markers:
            normalized = marker.strip().lower()
            if not normalized:
                continue
            if any(normalized in url for url in observed_urls) or normalized in lower_text:
                return True
        return False

    def _browser_observed_urls(self, payload: dict[str, Any]) -> list[str]:
        urls: list[str] = []

        def append(value: Any) -> None:
            if isinstance(value, str) and value.strip():
                urls.append(value.strip())

        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            for step in result.get("steps") or []:
                if isinstance(step, dict):
                    append(step.get("url"))
            for item in result.get("evidence") or []:
                self._append_browser_item_urls(urls, item)
        for item in payload.get("evidence") or []:
            self._append_browser_item_urls(urls, item)
        return urls

    def _append_browser_item_urls(self, urls: list[str], item: Any) -> None:
        if not isinstance(item, dict):
            return
        url = item.get("url")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        values = data.get("urls")
        if isinstance(values, list):
            urls.extend(str(value).strip() for value in values if str(value).strip())

    def _browser_results_timed_out(self, results: list[Any]) -> bool:
        for result in results:
            if not isinstance(result, dict):
                continue
            metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
            if metrics.get("timed_out"):
                return True
            evidence_items = result.get("evidence") if isinstance(result.get("evidence"), list) else []
            for item in evidence_items:
                if not isinstance(item, dict):
                    continue
                data = item.get("data") if isinstance(item.get("data"), dict) else {}
                if data.get("timed_out"):
                    return True
        return False

    def _browser_text_timeout_signal(self, lower_text: str) -> bool:
        timeout_patterns = (
            r"\b(?:browser[-\s]?use|walkthrough|run|task|agent)\s+(?:has\s+)?timed out\b",
            r"\brun\s+timeout\b",
            r"\btimeout\s+(?:reached|expired)\b",
        )
        return any(re.search(pattern, lower_text) for pattern in timeout_patterns)

    def _browser_status_text(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            parts.append(str(result.get("status") or ""))
            for error in result.get("errors") or []:
                parts.append(str(error))
            for step in result.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                parts.extend(str(step.get(key) or "") for key in ("status", "observation", "url"))
            for item in result.get("evidence") or []:
                self._append_browser_item_text(parts, item)
        for item in payload.get("evidence") or []:
            self._append_browser_item_text(parts, item)
        return " ".join(part for part in parts if part)

    def _append_browser_item_text(self, parts: list[str], item: Any) -> None:
        if not isinstance(item, dict):
            return
        parts.extend(str(item.get(key) or "") for key in ("kind", "summary", "url"))
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        for key in ("final_output", "status_reason"):
            if isinstance(data.get(key), str):
                parts.append(data[key])
        for key in ("errors", "urls"):
            values = data.get(key)
            if isinstance(values, list):
                parts.extend(str(value) for value in values)

    def _terminal_event_type(self, status: str) -> str:
        return {
            "succeeded": "run.completed",
            "blocked": "run.blocked",
            "timeout": "run.timeout",
            "failed": "run.failed",
            "awaiting_verification": "run.awaiting_verification",
            "canceled": "run.canceled",
        }.get(status, "run.completed")

    def _terminal_message(self, status: str) -> str:
        return {
            "succeeded": "Run completed",
            "blocked": "Run blocked",
            "timeout": "Run timed out",
            "failed": "Run failed",
            "awaiting_verification": "Run is awaiting manual verification",
            "canceled": "Run canceled",
        }.get(status, "Run completed")

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
            ("art_issues_json", "issues_json", "issues.json", "issues.json", "application/json"),
            ("art_report_md", "report_markdown", "report.md", "report.md", "text/markdown; charset=utf-8"),
            ("art_evaluation_json", "evaluation_json", "evaluation.json", "evaluation.json", "application/json"),
            (
                WALKTHROUGH_MAP_ARTIFACT_ID,
                "walkthrough_map",
                "walkthrough_map.json",
                "walkthrough_map.json",
                "application/json",
            ),
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
        history_dir = run_dir / "browser-history"
        if history_dir.exists():
            for path in sorted(history_dir.glob("*.json")):
                if not path.is_file():
                    continue
                resolved = path.resolve()
                run_root = run_dir.resolve()
                if not resolved.is_relative_to(run_root):
                    continue
                rel_path = resolved.relative_to(run_root).as_posix()
                artifact_id = self._artifact_id_for_path("art_browser_history", rel_path)
                artifacts.append(
                    {
                        "id": artifact_id,
                        "run_id": run_id,
                        "type": "browser_history",
                        "title": path.name,
                        "path": rel_path,
                        "media_type": "application/json",
                        "size_bytes": path.stat().st_size,
                        "created_at": self._mtime_iso(path),
                        "metadata": {
                            "content_url": f"/api/runs/{run_id}/artifacts/{artifact_id}/content",
                            "path_url": f"/api/runs/{run_id}/artifacts/{quote(rel_path, safe='/')}",
                        },
                    }
                )
        page_evidence_dir = run_dir / "page-evidence"
        if page_evidence_dir.exists():
            for path in sorted(page_evidence_dir.rglob("*")):
                if not path.is_file():
                    continue
                resolved = path.resolve()
                run_root = run_dir.resolve()
                if not resolved.is_relative_to(run_root):
                    continue
                rel_path = resolved.relative_to(run_root).as_posix()
                artifact_type = PAGE_EVIDENCE_ARTIFACT_TYPES.get(path.name, "log_text")
                artifact_id = self._artifact_id_for_path(f"art_{artifact_type}", rel_path)
                artifacts.append(
                    {
                        "id": artifact_id,
                        "run_id": run_id,
                        "type": artifact_type,
                        "title": path.name,
                        "path": rel_path,
                        "media_type": self._media_type_for_path(path),
                        "size_bytes": path.stat().st_size,
                        "created_at": self._mtime_iso(path),
                        "metadata": {
                            "content_url": f"/api/runs/{run_id}/artifacts/{artifact_id}/content",
                            "path_url": f"/api/runs/{run_id}/artifacts/{quote(rel_path, safe='/')}",
                            "capture_dir": resolved.parent.relative_to(run_root).as_posix(),
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
