from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RunStatus = Literal[
    "queued",
    "starting",
    "running",
    "awaiting_verification",
    "blocked",
    "finalizing",
    "succeeded",
    "failed",
    "canceling",
    "canceled",
]

AgentStatus = Literal["pending", "running", "waiting", "succeeded", "failed", "skipped", "canceled"]
AgentType = Literal[
    "director",
    "planner",
    "walker",
    "evidence_extractor",
    "product_analyst",
    "competitive_analyst",
    "reviewer",
    "report_writer",
    "evaluator",
    "auth_session",
]
ArtifactType = Literal[
    "run_manifest",
    "plan_json",
    "events_jsonl",
    "agents_json",
    "artifacts_json",
    "evidence_json",
    "report_markdown",
    "evaluation_json",
    "screenshot",
    "browser_history",
    "log_text",
]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str
    time: str


class PlanSummary(BaseModel):
    id: str
    name: str
    path: str
    title: str
    product_count: int
    scenario_count: int
    report_language: str


class PlanListResponse(BaseModel):
    items: list[PlanSummary]


class PlanDetailResponse(BaseModel):
    id: str
    name: str
    path: str
    plan: dict[str, Any]


class Progress(BaseModel):
    total_scenarios: int = 0
    completed_scenarios: int = 0
    failed_scenarios: int = 0


class RunSummary(BaseModel):
    id: str
    run_id: str
    status: str
    mode: str
    research_goal: str
    run_dir: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    progress: Progress = Field(default_factory=Progress)
    report_exists: bool = False
    evidence_exists: bool = False
    evaluation_exists: bool = False
    screenshot_count: int = 0


class RunDetail(RunSummary):
    params: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class RunStartRequest(BaseModel):
    config: dict[str, Any] | str | None = None
    config_path: str | None = None
    plan_name: str | None = None
    plan: dict[str, Any] | None = None
    mode: str = "mock"
    out: str = "runs"
    concurrency: int | None = None
    report_language: str | None = None
    browser_model: str | None = None
    browser_max_steps: int = 25
    browser_timeout_sec: float = 600.0
    browser_user_data_dir: str | None = None
    browser_storage_state: str | None = None
    verification_mode: str = "off"
    verification_timeout_sec: float = 300.0
    verification_success_url_contains: list[str] = Field(default_factory=list)
    verification_login_url_contains: str = "/auth/login"


class RunStartResponse(BaseModel):
    run_id: str
    status: str
    created_at: str
    events_url: str
    report_url: str
    evidence_url: str
    evaluation_url: str
    run: RunSummary


class RunListResponse(BaseModel):
    items: list[RunSummary]
    next_cursor: str | None = None


class RunDetailResponse(BaseModel):
    run: RunDetail


class RunCancelRequest(BaseModel):
    reason: str | None = None


class VerificationConfirmRequest(BaseModel):
    confirmed: bool = True
    note: str | None = None


class RunActionResponse(BaseModel):
    run_id: str
    status: str
    accepted: bool


class AgentExecution(BaseModel):
    id: str
    run_id: str
    type: str
    status: str
    label: str
    product: str | None = None
    scenario_id: str | None = None
    current_step: int | None = None
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class AgentListResponse(BaseModel):
    items: list[AgentExecution]


class Artifact(BaseModel):
    id: str
    run_id: str
    type: str
    title: str
    path: str
    media_type: str
    size_bytes: int
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactListResponse(BaseModel):
    items: list[Artifact]


class ArtifactResponse(BaseModel):
    artifact: Artifact


class RunEvent(BaseModel):
    id: str
    run_id: str
    seq: int
    ts: str
    type: str
    level: Literal["debug", "info", "warn", "error"] = "info"
    message: str
    agent_id: str | None = None
    agent_type: str | None = None
    product: str | None = None
    scenario_id: str | None = None
    step_index: int | None = None
    status: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)


class EventListResponse(BaseModel):
    items: list[RunEvent]
    last_seq: int
