from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from prodwalk import __version__ as prodwalk_version
from prodwalk.models import utc_now

from .models import (
    AgentListResponse,
    ArtifactListResponse,
    ArtifactResponse,
    AuthSessionConfirmRequest,
    AuthSessionCreateRequest,
    AuthSessionDetailResponse,
    EventListResponse,
    HealthResponse,
    RetryAfterVerificationRequest,
    RetryAfterVerificationResponse,
    RunActionResponse,
    RunClearResponse,
    RunCancelRequest,
    RunDetailResponse,
    RunStartRequest,
    VerificationConfirmRequest,
)
from .runtime import ApiError, RunRuntime


def create_app(workspace_root: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="prodwalk local console API", version=prodwalk_version)
    runtime = RunRuntime(workspace_root=workspace_root)
    app.state.runtime = runtime

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(400, "BAD_REQUEST", "Request validation failed.", {"errors": exc.errors()})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(500, "SERVER_ERROR", "Unexpected server error.", {"error": str(exc)})

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, service="prodwalk-server", version=prodwalk_version, time=utc_now())

    @app.get("/api/plans")
    async def list_plans() -> Any:
        return app.state.runtime.list_plans()

    @app.get("/api/plans/{name:path}")
    async def get_plan(name: str) -> Any:
        return app.state.runtime.get_plan(name)

    @app.post("/api/runs")
    async def start_run(request: RunStartRequest) -> Any:
        return await app.state.runtime.start_run(request)

    @app.get("/api/runs")
    async def list_runs(limit: int = 50) -> Any:
        return app.state.runtime.list_runs(limit=limit)

    @app.get("/api/runs/{run_id}", response_model=RunDetailResponse)
    async def get_run(run_id: str) -> RunDetailResponse:
        return RunDetailResponse(run=app.state.runtime.get_run(run_id))

    @app.post("/api/runs/{run_id}/cancel", response_model=RunActionResponse)
    async def cancel_run(run_id: str, request: RunCancelRequest | None = None) -> RunActionResponse:
        return await app.state.runtime.cancel_run(run_id, reason=request.reason if request else None)

    @app.delete("/api/runs/{run_id}", response_model=RunActionResponse)
    async def delete_run(run_id: str) -> RunActionResponse:
        return await app.state.runtime.delete_run(run_id)

    @app.delete("/api/runs", response_model=RunClearResponse)
    async def clear_runs() -> RunClearResponse:
        return await app.state.runtime.clear_runs()

    @app.post("/api/runs/{run_id}/verification/confirm", response_model=RunActionResponse)
    async def confirm_verification(
        run_id: str,
        request: VerificationConfirmRequest,
    ) -> RunActionResponse:
        return await app.state.runtime.confirm_verification(
            run_id,
            confirmed=request.confirmed,
            note=request.note,
        )

    @app.post("/api/auth-sessions", response_model=AuthSessionDetailResponse)
    async def create_auth_session(request: AuthSessionCreateRequest) -> AuthSessionDetailResponse:
        return AuthSessionDetailResponse(session=await app.state.runtime.create_auth_session(request))

    @app.get("/api/auth-sessions/{session_id}", response_model=AuthSessionDetailResponse)
    async def get_auth_session(session_id: str) -> AuthSessionDetailResponse:
        return AuthSessionDetailResponse(session=app.state.runtime.get_auth_session(session_id))

    @app.post("/api/auth-sessions/{session_id}/confirm", response_model=AuthSessionDetailResponse)
    async def confirm_auth_session(
        session_id: str,
        request: AuthSessionConfirmRequest,
    ) -> AuthSessionDetailResponse:
        return AuthSessionDetailResponse(
            session=await app.state.runtime.confirm_auth_session(
                session_id,
                confirmed=request.confirmed,
                note=request.note,
            )
        )

    @app.post("/api/runs/{run_id}/retry-after-verification", response_model=RetryAfterVerificationResponse)
    async def retry_after_verification(
        run_id: str,
        request: RetryAfterVerificationRequest | None = None,
    ) -> RetryAfterVerificationResponse:
        return await app.state.runtime.retry_after_verification(
            run_id,
            request or RetryAfterVerificationRequest(),
        )

    @app.get("/api/runs/{run_id}/agents", response_model=AgentListResponse)
    async def list_agents(run_id: str) -> AgentListResponse:
        return AgentListResponse(items=app.state.runtime.list_agents(run_id))

    @app.get("/api/runs/{run_id}/events/stream")
    async def stream_run_events(run_id: str, after_seq: int = 0) -> StreamingResponse:
        app.state.runtime.ensure_run_exists(run_id)
        return StreamingResponse(
            app.state.runtime.stream_events(run_id, after_seq=after_seq),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/events")
    async def list_run_events(request: Request, run_id: str, after_seq: int = 0, limit: int = 100) -> Any:
        if "text/event-stream" in request.headers.get("accept", ""):
            app.state.runtime.ensure_run_exists(run_id)
            return StreamingResponse(
                app.state.runtime.stream_events(run_id, after_seq=after_seq),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return EventListResponse(**app.state.runtime.list_events(run_id, after_seq=after_seq, limit=limit))

    @app.get("/api/runs/{run_id}/artifacts", response_model=ArtifactListResponse)
    async def list_artifacts(run_id: str) -> ArtifactListResponse:
        return ArtifactListResponse(items=app.state.runtime.list_artifacts(run_id))

    @app.get("/api/runs/{run_id}/artifacts/{artifact_id}/content")
    async def get_artifact_content(run_id: str, artifact_id: str) -> Response:
        artifact = app.state.runtime.get_artifact(run_id, artifact_id)
        path = app.state.runtime.artifact_path(run_id, artifact_id)
        return _artifact_file_response(path, artifact.media_type)

    @app.get("/api/runs/{run_id}/screenshots/{filename}")
    async def get_screenshot(run_id: str, filename: str) -> Response:
        path, media_type = app.state.runtime.screenshot_file(run_id, filename)
        return _artifact_file_response(path, media_type)

    @app.get("/api/runs/{run_id}/artifacts/{artifact_ref:path}")
    async def get_artifact_or_file(run_id: str, artifact_ref: str) -> Any:
        artifact = app.state.runtime.find_artifact(run_id, artifact_ref)
        if artifact is not None:
            return ArtifactResponse(artifact=artifact)
        path, media_type = app.state.runtime.artifact_file(run_id, artifact_ref)
        return _artifact_file_response(path, media_type)

    @app.get("/api/runs/{run_id}/report")
    async def get_report(run_id: str) -> Any:
        return app.state.runtime.read_report(run_id)

    @app.get("/api/runs/{run_id}/evidence")
    async def get_evidence(run_id: str) -> Any:
        return app.state.runtime.read_evidence(run_id)

    @app.get("/api/runs/{run_id}/evidence/{evidence_id}")
    async def get_evidence_item(run_id: str, evidence_id: str) -> Any:
        return app.state.runtime.read_evidence_item(run_id, evidence_id)

    @app.get("/api/runs/{run_id}/evaluation")
    async def get_evaluation(run_id: str) -> Any:
        return app.state.runtime.read_evaluation(run_id)

    @app.get("/api/runs/{run_id}/map")
    async def get_walkthrough_map(run_id: str) -> Any:
        return app.state.runtime.read_map(run_id)

    return app


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": f"req_{uuid.uuid4().hex}",
            }
        },
    )


def _artifact_file_response(path: Path, media_type: str) -> Response:
    headers = {"X-Content-Type-Options": "nosniff"}
    if media_type == "application/json":
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")), headers=headers)
    if media_type.startswith("text/") or media_type == "application/x-ndjson":
        return Response(path.read_text(encoding="utf-8"), media_type=media_type, headers=headers)
    return FileResponse(path, media_type=media_type, headers=headers)


app = create_app()
