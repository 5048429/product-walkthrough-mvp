from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from prodwalk.server import runtime as runtime_module
from prodwalk.server.app import create_app


def _write_plan(root: Path) -> None:
    examples = root / "examples"
    examples.mkdir()
    (examples / "smoke_plan.json").write_text(
        """
{
  "research_goal": "Verify the FastAPI mock backend path.",
  "report_language": "en",
  "products": [
    {
      "name": "Example Product",
      "url": "https://example.test",
      "kind": "owned"
    }
  ],
  "scenarios": [
    {
      "id": "smoke",
      "title": "Smoke flow",
      "persona": "Backend tester",
      "goal": "Confirm mock mode generates artifacts.",
      "steps": ["Open the entry page", "Record the primary action"],
      "success_criteria": ["Artifacts are generated"],
      "observation_points": ["Backend behavior"]
    }
  ],
  "evaluation": {
    "min_evidence_per_result": 1
  }
}
""".strip(),
        encoding="utf-8",
    )


def _client(root: Path) -> TestClient:
    return TestClient(create_app(workspace_root=root))


def _write_historical_run(root: Path) -> Path:
    run_dir = root / "runs" / "run-20260102-030405-history"
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(parents=True)
    evidence = {
        "created_at": "2026-01-02T03:04:05Z",
        "report_language": "en",
        "plan": {"research_goal": "Review historical artifacts."},
        "results": [{"status": "completed"}],
        "evidence": [],
    }
    (run_dir / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (run_dir / "report.md").write_text("# Historical Report\n\nReady.", encoding="utf-8")
    (run_dir / "evaluation.json").write_text('{"overall_score": 1.0, "notes": []}', encoding="utf-8")
    (screenshots_dir / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return run_dir


def _wait_for_terminal(client: TestClient, run_id: str) -> dict:
    deadline = time.time() + 5
    detail = {}
    while time.time() < deadline:
        detail_response = client.get(f"/api/runs/{run_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["run"]
        if detail["status"] in {"succeeded", "failed", "canceled"}:
            return detail
        time.sleep(0.05)
    return detail


def test_health_succeeds(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_cors_allows_vite_localhost(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_plans_returns_examples(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        response = client.get("/api/plans")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["name"] for item in items] == ["smoke_plan.json"]
    assert items[0]["path"] == "examples/smoke_plan.json"


def test_post_runs_starts_mock_run_and_artifacts_are_readable(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "mock", "out": "runs", "concurrency": 1},
        )
        assert response.status_code == 200
        payload = response.json()
        run_id = payload["run_id"]
        assert run_id.startswith("run-")

        detail = _wait_for_terminal(client, run_id)
        assert detail["status"] == "succeeded"

        report = client.get(f"/api/runs/{run_id}/report")
        evidence = client.get(f"/api/runs/{run_id}/evidence")
        evaluation = client.get(f"/api/runs/{run_id}/evaluation")
        events = client.get(f"/api/runs/{run_id}/events")
        agents = client.get(f"/api/runs/{run_id}/agents")
        report_artifact = client.get(f"/api/runs/{run_id}/artifacts/art_report_md/content")
        runs = client.get("/api/runs")

        assert report.status_code == 200
        assert "# Product Walkthrough Research Report" in report.json()["markdown"]
        assert evidence.status_code == 200
        evidence_items = evidence.json()["evidence"]
        assert evidence_items
        assert "screenshot" not in evidence_items[0]
        assert "screenshot_artifact_id" in evidence_items[0]
        assert evaluation.status_code == 200
        assert "overall_score" in evaluation.json()
        assert events.status_code == 200
        event_items = events.json()["items"]
        event_types = [event["type"] for event in event_items]
        assert "agent.started" in event_types
        assert "agent.completed" in event_types
        assert "artifact.created" in event_types
        assert "run.completed" in event_types
        assert not any("_" in event["type"] for event in event_items)
        assert agents.status_code == 200
        assert any(agent["type"] == "walker" for agent in agents.json()["items"])
        assert report_artifact.status_code == 200
        assert "# Product Walkthrough Research Report" in report_artifact.text
        assert runs.status_code == 200
        run_items = runs.json()["items"]
        listed = next(item for item in run_items if item["run_id"] == run_id)
        assert listed["status"] == "succeeded"
        assert listed["created_at"]
        assert listed["report_exists"] is True
        assert listed["evidence_exists"] is True
        assert listed["evaluation_exists"] is True
        assert listed["screenshot_count"] == 0


def test_plan_name_path_traversal_is_rejected(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    (tmp_path / "secret.json").write_text('{"research_goal":"nope"}', encoding="utf-8")
    with _client(tmp_path) as client:
        response = client.get("/api/plans/..%2Fsecret.json")
        post_response = client.post("/api/runs", json={"config_path": "../secret.json", "mode": "mock"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    assert post_response.status_code == 400
    assert post_response.json()["error"]["code"] == "BAD_REQUEST"


def test_runs_lists_historical_run_with_artifact_availability(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    run_dir = _write_historical_run(tmp_path)
    with _client(tmp_path) as client:
        response = client.get("/api/runs")

    assert response.status_code == 200
    items = response.json()["items"]
    historical = next(item for item in items if item["run_id"] == run_dir.name)
    assert historical["status"] == "succeeded"
    assert historical["mode"] == "unknown"
    assert historical["created_at"] == "2026-01-02T03:04:05Z"
    assert historical["report_exists"] is True
    assert historical["evidence_exists"] is True
    assert historical["evaluation_exists"] is True
    assert historical["screenshot_count"] == 1


def test_artifact_path_traversal_is_rejected(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    run_dir = _write_historical_run(tmp_path)
    (run_dir.parent / "secret.txt").write_text("outside", encoding="utf-8")
    with _client(tmp_path) as client:
        response = client.get(f"/api/runs/{run_dir.name}/artifacts/%2E%2E%2Fsecret.txt")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ARTIFACT_FORBIDDEN"


def test_missing_artifact_returns_404(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    run_dir = _write_historical_run(tmp_path)
    with _client(tmp_path) as client:
        response = client.get(f"/api/runs/{run_dir.name}/artifacts/missing.txt")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"


def test_text_artifact_and_screenshot_are_readable(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    run_dir = _write_historical_run(tmp_path)
    with _client(tmp_path) as client:
        text_response = client.get(f"/api/runs/{run_dir.name}/artifacts/report.md")
        screenshot_response = client.get(f"/api/runs/{run_dir.name}/screenshots/shot.png")
        screenshot_path_response = client.get(f"/api/runs/{run_dir.name}/artifacts/screenshots/shot.png")

    assert text_response.status_code == 200
    assert text_response.headers["content-type"].startswith("text/markdown")
    assert text_response.headers["x-content-type-options"] == "nosniff"
    assert "# Historical Report" in text_response.text
    assert screenshot_response.status_code == 200
    assert screenshot_response.headers["content-type"].startswith("image/png")
    assert screenshot_response.headers["x-content-type-options"] == "nosniff"
    assert screenshot_response.content.startswith(b"\x89PNG")
    assert screenshot_path_response.status_code == 200
    assert screenshot_path_response.headers["content-type"].startswith("image/png")


def test_sse_endpoints_output_run_event_frames(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "mock", "out": "runs", "concurrency": 1},
        )
        run_id = response.json()["run_id"]
        assert _wait_for_terminal(client, run_id)["status"] == "succeeded"

        stream_response = client.get(f"/api/runs/{run_id}/events/stream")
        eventsource_response = client.get(
            f"/api/runs/{run_id}/events",
            headers={"accept": "text/event-stream"},
        )

    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")
    assert "event: run.event" in stream_response.text
    assert "data: {" in stream_response.text
    assert eventsource_response.status_code == 200
    assert eventsource_response.headers["content-type"].startswith("text/event-stream")
    assert "event: run.event" in eventsource_response.text


def test_events_for_missing_run_return_clear_error(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        json_response = client.get("/api/runs/run-missing/events")
        sse_response = client.get("/api/runs/run-missing/events/stream")

    assert json_response.status_code == 404
    assert json_response.json()["error"]["code"] == "RUN_NOT_FOUND"
    assert sse_response.status_code == 404
    assert sse_response.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_background_run_failure_sets_failed_status(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)

    class FailingDirector:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def run(self, plan, run_dir) -> None:
            raise RuntimeError("simulated backend failure")

    monkeypatch.setattr(runtime_module, "ResearchDirector", FailingDirector)

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "mock", "out": "runs", "concurrency": 1},
        )
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        events = client.get(f"/api/runs/{run_id}/events")

    assert detail["status"] == "failed"
    assert detail["error"]["message"] == "simulated backend failure"
    assert events.status_code == 200
    assert "run.failed" in [event["type"] for event in events.json()["items"]]
