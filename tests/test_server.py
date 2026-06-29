from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from prodwalk.models import EvidenceItem, ProductTarget, Scenario, WalkStep, WalkthroughResult, utc_now
from prodwalk.agents.map_builder import BUILD_VERSION as WALKTHROUGH_MAP_BUILD_VERSION
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


def _write_historical_map_run(root: Path) -> Path:
    run_dir = root / "runs" / "run-20260102-030405-map"
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(parents=True)
    (screenshots_dir / "customer.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    page_evidence_dir = run_dir / "page-evidence" / "customer"
    page_evidence_dir.mkdir(parents=True)
    (page_evidence_dir / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0", "title": "Customer Profile", "url": "https://example.test/customers/123?token=secret"}),
        encoding="utf-8",
    )
    (page_evidence_dir / "text.json").write_text(
        json.dumps({"text": "Customer Profile Activity Timeline C:/secret/profile token=secret"}),
        encoding="utf-8",
    )
    (page_evidence_dir / "elements.json").write_text(
        json.dumps(
            {
                "items": [
                    {"tag": "button", "text": "Edit customer", "visible": True, "disabled": False},
                    {"tag": "input", "placeholder": "Search activity", "type": "search", "visible": True, "disabled": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    evidence = {
        "created_at": "2026-01-02T03:04:05Z",
        "report_language": "en",
        "plan": {
            "research_goal": "Map historical artifacts.",
            "products": [{"name": "Example Product", "url": "https://example.test/home", "kind": "owned"}],
        },
        "results": [
            {
                "product": "Example Product",
                "product_kind": "owned",
                "scenario_id": "map",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Opened home.",
                        "url": "https://example.test/home?utm_source=test",
                        "evidence_ids": ["ev-home"],
                    },
                    {
                        "index": 2,
                        "action": "click",
                        "status": "passed",
                        "observation": 'Clicked a role=menuitem "Customer"',
                        "url": "https://example.test/customers/123?token=secret",
                        "screenshot": r"C:\temp\customer.png",
                        "evidence_ids": ["ev-customer"],
                    },
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-home",
                "product": "Example Product",
                "scenario_id": "map",
                "kind": "browser_step",
                "title": "Home",
                "summary": "Opened home.",
                "url": "https://example.test/home",
                "data": {"title": "Home"},
            },
            {
                "id": "ev-customer",
                "product": "Example Product",
                "scenario_id": "map",
                "kind": "browser_step",
                "title": "Customer",
                "summary": "Opened customer detail.",
                "url": "https://example.test/customers/123?token=secret",
                "screenshot": r"C:\temp\customer.png",
                "data": {
                    "title": "Customer",
                    "screenshot_path": r"C:\temp\customer.png",
                    "page_evidence": {
                        "status": "completed",
                        "title": "Customer Profile",
                        "page_type": "detail",
                        "purpose": "Review customer profile and activity.",
                        "manifest_path": "page-evidence/customer/manifest.json",
                        "artifact_paths": [
                            "page-evidence/customer/text.json",
                            "page-evidence/customer/elements.json",
                            "page-evidence/customer/manifest.json",
                        ],
                        "full_page_screenshot_path": "screenshots/customer.png",
                        "screenshot_paths": ["screenshots/customer.png"],
                    },
                },
            },
        ],
    }
    (run_dir / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (run_dir / "report.md").write_text("# Historical Map Report\n\nReady.", encoding="utf-8")
    (run_dir / "evaluation.json").write_text('{"overall_score": 1.0, "notes": []}', encoding="utf-8")
    return run_dir


def _wait_for_terminal(client: TestClient, run_id: str) -> dict:
    deadline = time.time() + 5
    detail = {}
    while time.time() < deadline:
        detail_response = client.get(f"/api/runs/{run_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["run"]
        if detail["status"] in {"succeeded", "blocked", "timeout", "failed", "awaiting_verification", "canceled"}:
            return detail
        time.sleep(0.05)
    return detail


class _FakeBrowserUseWalker:
    result_status = "completed"
    final_output = '{"completed": true}'
    errors: list[str] = []
    timed_out = False
    screenshot_path: str | None = None
    history_path: str | None = None
    page_evidence: dict | None = None
    init_args: dict | None = None

    def __init__(
        self,
        model: str | None = None,
        max_steps: int = 25,
        run_timeout_sec: float | None = None,
        user_data_dir: str | None = None,
        storage_state: str | None = None,
        discover_all_pages: bool | None = None,
        discovery_max_pages: int | None = None,
        discovery_max_depth: int | None = None,
    ) -> None:
        self.page_evidence = self.__class__.page_evidence
        self.__class__.page_evidence = None
        self.__class__.init_args = {
            "model": model,
            "max_steps": max_steps,
            "run_timeout_sec": run_timeout_sec,
            "user_data_dir": user_data_dir,
            "storage_state": storage_state,
            "discover_all_pages": discover_all_pages,
            "discovery_max_pages": discovery_max_pages,
            "discovery_max_depth": discovery_max_depth,
        }

    async def walk(self, product: ProductTarget, scenario: Scenario) -> WalkthroughResult:
        evidence_id = f"ev-{scenario.id}-browser-use"
        data = {
            "mode": "browser-use-local",
            "final_output": self.final_output,
            "timed_out": self.timed_out,
            "errors": list(self.errors),
            "user_data_dir": "C:/secret/profile",
            "storage_state": "C:/secret/state.json",
        }
        if self.screenshot_path:
            data["screenshot_paths"] = [self.screenshot_path]
        if self.history_path:
            data["history_file"] = self.history_path
        if self.page_evidence:
            data["page_evidence"] = dict(self.page_evidence)

        step_status = "passed" if self.result_status == "completed" else "blocked"
        started_at = utc_now()
        return WalkthroughResult(
            product=product.name,
            product_kind=product.kind,
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            status=self.result_status,
            started_at=started_at,
            completed_at=utc_now(),
            steps=[
                WalkStep(
                    index=1,
                    action="Run browser-use task",
                    status=step_status,
                    observation=self.final_output,
                    url=product.url,
                    screenshot=self.screenshot_path,
                    evidence_ids=[evidence_id],
                )
            ],
            evidence=[
                EvidenceItem(
                    id=evidence_id,
                    product=product.name,
                    scenario_id=scenario.id,
                    kind="browser_run",
                    title="browser-use run",
                    summary=self.final_output,
                    url=product.url,
                    screenshot=self.screenshot_path,
                    data=data,
                    confidence=0.8,
                )
            ],
            metrics={"step_count": 1, "timed_out": self.timed_out},
            errors=list(self.errors),
        )


class _FakeManualAuthSession:
    def __init__(self, request) -> None:
        self.request = request
        self.closed = False
        self.storage_state = Path(request.storage_state) if request.storage_state else None


async def _fake_open_manual_auth_session(request) -> _FakeManualAuthSession:
    Path(request.user_data_dir).mkdir(parents=True, exist_ok=True)
    if request.storage_state:
        Path(request.storage_state).parent.mkdir(parents=True, exist_ok=True)
    return _FakeManualAuthSession(request)


async def _fake_complete_manual_auth_session(session: _FakeManualAuthSession) -> str:
    if session.storage_state:
        session.storage_state.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    session.closed = True
    return "https://example.test/dashboard?step=manual"


async def _fake_close_manual_auth_session(session: _FakeManualAuthSession) -> None:
    session.closed = True


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
        alternate_port_response = client.options(
            "/api/health",
            headers={
                "Origin": "http://127.0.0.1:5175",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert alternate_port_response.status_code == 200
    assert alternate_port_response.headers["access-control-allow-origin"] == "http://127.0.0.1:5175"


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
        issues = client.get(f"/api/runs/{run_id}/issues")
        evaluation = client.get(f"/api/runs/{run_id}/evaluation")
        walkthrough_map = client.get(f"/api/runs/{run_id}/map")
        events = client.get(f"/api/runs/{run_id}/events")
        agents = client.get(f"/api/runs/{run_id}/agents")
        report_artifact = client.get(f"/api/runs/{run_id}/artifacts/art_report_md/content")
        artifacts = client.get(f"/api/runs/{run_id}/artifacts")
        runs = client.get("/api/runs")

        assert report.status_code == 200
        assert "# Product Walkthrough Issue Report" in report.json()["markdown"]
        assert report.json()["issues"]["summary"]["issue_count"] >= 0
        assert evidence.status_code == 200
        evidence_items = evidence.json()["evidence"]
        assert evidence_items
        assert "screenshot" not in evidence_items[0]
        assert "screenshot_artifact_id" in evidence_items[0]
        assert issues.status_code == 200
        assert issues.json()["artifact_id"] == "art_issues_json"
        assert "issues" in issues.json()
        assert evaluation.status_code == 200
        assert "overall_score" in evaluation.json()
        assert walkthrough_map.status_code == 200
        assert walkthrough_map.json()["schema_version"] == "1.0"
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
        assert "# Product Walkthrough Issue Report" in report_artifact.text
        assert artifacts.status_code == 200
        artifact_types = {item["type"] for item in artifacts.json()["items"]}
        assert "issues_json" in artifact_types
        assert "walkthrough_map" in artifact_types
        assert runs.status_code == 200
        run_items = runs.json()["items"]
        listed = next(item for item in run_items if item["run_id"] == run_id)
        assert listed["status"] == "succeeded"
        assert listed["created_at"]
        assert listed["report_exists"] is True
        assert listed["evidence_exists"] is True
        assert listed["evaluation_exists"] is True
        assert listed["screenshot_count"] == 0


def test_post_runs_accepts_target_url_without_local_plan(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"target_url": "example.test/app", "mode": "mock", "out": "runs", "concurrency": 1},
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        detail = _wait_for_terminal(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["research_goal"] == "对 example.test 进行一次全量产品走查，发现可复现问题并提出产品改进建议。"
    assert detail["params"]["plan_source"] == "target_url"
    assert detail["params"]["target_url"] == "https://example.test/app"
    assert detail["params"]["target_name"] == "example.test"
    assert detail["params"]["target_credentials_ref"] is None

    plan_path = tmp_path / detail["run_dir"] / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["report_language"] == "zh"
    assert plan["products"][0]["url"] == "https://example.test/app"
    assert plan["products"][0]["kind"] == "owned"
    assert plan["scenarios"][0]["id"] == "full-site-walkthrough"
    assert "只读" in plan["scenarios"][0]["title"]


def test_target_url_defaults_to_browser_use_full_site_walkthrough(tmp_path: Path, monkeypatch) -> None:
    _FakeBrowserUseWalker.init_args = None
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    storage_state = tmp_path / ".prodwalk" / "browser-profiles" / "target-url" / "state.json"
    storage_state.parent.mkdir(parents=True)
    storage_state.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

    with _client(tmp_path) as client:
        blocked_response = client.post("/api/runs", json={"target_url": "https://example.test", "out": "runs"})
        response = client.post(
            "/api/runs",
            json={
                "target_url": "https://example.test",
                "out": "runs",
                "browser_storage_state": ".prodwalk/browser-profiles/target-url/state.json",
            },
        )
        assert blocked_response.status_code == 400
        assert blocked_response.json()["error"]["code"] == "AUTH_SESSION_REQUIRED"
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        detail = _wait_for_terminal(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["mode"] == "browser-use"
    assert detail["params"]["mode"] == "browser-use"
    assert detail["params"]["concurrency"] == 1
    assert detail["params"]["browser_discover_all_pages"] is True
    assert detail["params"]["browser_discovery_max_pages"] == 120
    assert detail["params"]["browser_discovery_max_depth"] == 4
    assert detail["params"]["target_url"] == "https://example.test"
    assert _FakeBrowserUseWalker.init_args is not None


def test_target_url_validation_is_clear(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        invalid_scheme = client.post("/api/runs", json={"target_url": "javascript:alert(1)", "mode": "mock"})
        embedded_credentials = client.post("/api/runs", json={"target_url": "https://user:pass@example.test", "mode": "mock"})
        mixed_plan = client.post(
            "/api/runs",
            json={"target_url": "https://example.test", "plan_name": "smoke_plan.json", "mode": "mock"},
        )

    assert invalid_scheme.status_code == 400
    assert "target_url" in invalid_scheme.json()["error"]["message"]
    assert embedded_credentials.status_code == 400
    assert "username or password" in embedded_credentials.json()["error"]["message"]
    assert mixed_plan.status_code == 400
    assert "target_url" in mixed_plan.json()["error"]["message"]


def test_browser_use_mode_unavailable_returns_clear_error(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: ["browser-use is not installed"],
    )

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "browser-use", "out": "runs"},
        )

    assert response.status_code == 503
    payload = response.json()["error"]
    assert payload["code"] == "BROWSER_USE_UNAVAILABLE"
    assert "browser-use mode is not ready" in payload["message"]
    assert payload["details"]["errors"] == ["browser-use is not installed"]


def test_browser_use_parameter_validation_rejects_bad_values(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        concurrency_response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "browser-use", "concurrency": 2},
        )
        steps_response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "browser-use", "browser_max_steps": 0},
        )
        path_response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "browser_user_data_dir": str(tmp_path.parent / "outside-profile"),
            },
        )
        verification_response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "browser-use", "verification_mode": "sometimes"},
        )
        discovery_pages_response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "browser-use", "browser_discovery_max_pages": 0},
        )
        discovery_depth_response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "browser-use", "browser_discovery_max_depth": 11},
        )

    assert concurrency_response.status_code == 400
    assert "concurrency 1" in concurrency_response.json()["error"]["message"]
    assert steps_response.status_code == 400
    assert "browser_max_steps" in steps_response.json()["error"]["message"]
    assert path_response.status_code == 400
    assert "browser_user_data_dir" in path_response.json()["error"]["message"]
    assert verification_response.status_code == 400
    assert "verification_mode" in verification_response.json()["error"]["message"]
    assert discovery_pages_response.status_code == 400
    assert "browser_discovery_max_pages" in discovery_pages_response.json()["error"]["message"]
    assert discovery_depth_response.status_code == 400
    assert "browser_discovery_max_depth" in discovery_depth_response.json()["error"]["message"]


def test_browser_use_local_run_uses_walker_and_exposes_artifacts(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    external_dir = tmp_path / "external-browser-use"
    external_dir.mkdir()
    screenshot_path = external_dir / "shot.png"
    screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    full_page_screenshot_path = external_dir / "full-page.png"
    full_page_screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\nfull")
    page_html_path = external_dir / "page.html"
    page_html_path.write_text("<html><body>Dashboard</body></html>", encoding="utf-8")
    dom_snapshot_path = external_dir / "dom_snapshot.json"
    dom_snapshot_path.write_text('{"documents":[]}', encoding="utf-8")
    ax_tree_path = external_dir / "accessibility_tree.json"
    ax_tree_path.write_text('{"nodes":[]}', encoding="utf-8")
    network_log_path = external_dir / "network_log.json"
    network_log_path.write_text('{"items":[]}', encoding="utf-8")
    console_log_path = external_dir / "console_log.json"
    console_log_path.write_text('{"items":[]}', encoding="utf-8")
    manifest_path = external_dir / "manifest.json"
    manifest_path.write_text('{"schema_version":"1.0"}', encoding="utf-8")
    history_path = external_dir / "browser_use_history_fake.json"
    history_path.write_text(
        json.dumps(
            {
                "history": [{"state": {"url": "https://example.test", "screenshot_path": str(screenshot_path)}}],
                "user_data_dir": "C:/secret/profile",
                "storage_state": "C:/secret/state.json",
            }
        ),
        encoding="utf-8",
    )
    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = '{"completed": true}'
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = str(screenshot_path)
    _FakeBrowserUseWalker.history_path = str(history_path)
    _FakeBrowserUseWalker.page_evidence = {
        "status": "completed",
        "manifest_path": str(manifest_path),
        "artifact_paths": [
            str(page_html_path),
            str(dom_snapshot_path),
            str(ax_tree_path),
            str(network_log_path),
            str(console_log_path),
            str(manifest_path),
        ],
        "screenshot_paths": [str(full_page_screenshot_path)],
        "full_page_screenshot_path": str(full_page_screenshot_path),
        "network_event_count": 0,
        "console_message_count": 0,
    }
    _FakeBrowserUseWalker.init_args = None
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use-local",
                "out": "runs",
                "browser_model": "gpt-test",
                "browser_max_steps": 7,
                "browser_timeout_sec": 12,
                "browser_discover_all_pages": True,
                "browser_discovery_max_pages": 33,
                "browser_discovery_max_depth": 4,
                "browser_user_data_dir": ".prodwalk/browser-profiles/test",
                "browser_storage_state": ".prodwalk/browser-profiles/test/state.json",
                "verification_mode": "manual",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        artifacts = client.get(f"/api/runs/{run_id}/artifacts")
        evidence = client.get(f"/api/runs/{run_id}/evidence")
        report = client.get(f"/api/runs/{run_id}/report")
        evaluation = client.get(f"/api/runs/{run_id}/evaluation")
        events = client.get(f"/api/runs/{run_id}/events")
        agents = client.get(f"/api/runs/{run_id}/agents")

        artifact_items = artifacts.json()["items"]
        history_artifact = next(item for item in artifact_items if item["type"] == "browser_history")
        history_content = client.get(f"/api/runs/{run_id}/artifacts/{history_artifact['id']}/content")

    assert detail["status"] == "succeeded"
    assert detail["params"]["mode"] == "browser-use-local"
    assert detail["params"]["concurrency"] == 1
    assert detail["params"]["verification_mode"] == "auto"
    assert detail["params"]["browser_user_data_dir_configured"] is True
    assert detail["params"]["browser_storage_state_configured"] is True
    assert _FakeBrowserUseWalker.init_args == {
        "model": "gpt-test",
        "max_steps": 7,
        "run_timeout_sec": 12.0,
        "user_data_dir": str((tmp_path / ".prodwalk/browser-profiles/test").resolve()),
        "storage_state": str((tmp_path / ".prodwalk/browser-profiles/test/state.json").resolve()),
        "discover_all_pages": True,
        "discovery_max_pages": 33,
        "discovery_max_depth": 4,
    }
    assert detail["params"]["browser_discover_all_pages"] is True
    assert detail["params"]["browser_discovery_max_pages"] == 33
    assert detail["params"]["browser_discovery_max_depth"] == 4
    assert artifacts.status_code == 200
    assert {item["type"] for item in artifact_items} >= {
        "report_markdown",
        "evidence_json",
        "evaluation_json",
        "screenshot",
        "browser_history",
        "page_html",
        "dom_snapshot",
        "accessibility_tree",
        "network_log",
        "console_log",
        "page_evidence_manifest",
    }
    page_html_artifact = next(item for item in artifact_items if item["type"] == "page_html")
    page_html_content = client.get(f"/api/runs/{run_id}/artifacts/{page_html_artifact['id']}/content")
    assert evidence.status_code == 200
    evidence_item = evidence.json()["evidence"][0]
    assert evidence_item["screenshot_artifact_id"]
    assert len(evidence_item["screenshot_artifact_ids"]) == 2
    assert evidence_item["screenshot_artifact_id"] in evidence_item["screenshot_artifact_ids"]
    linked_types = {item["type"] for item in artifact_items if item["id"] in evidence_item["artifact_ids"]}
    assert {"page_html", "dom_snapshot", "accessibility_tree", "network_log", "console_log"} <= linked_types
    assert "user_data_dir" not in evidence_item["data"]
    assert "storage_state" not in evidence_item["data"]
    assert "history_file" not in evidence_item["data"]
    assert evidence_item["data"]["browser_history_artifact_id"] == history_artifact["id"]
    assert "C:/secret" not in json.dumps(evidence_item["data"])
    assert report.status_code == 200
    assert evaluation.status_code == 200
    assert history_content.status_code == 200
    assert page_html_content.status_code == 200
    assert page_html_content.headers["x-content-type-options"] == "nosniff"
    assert "Dashboard" in page_html_content.text
    assert "C:/secret" not in history_content.text
    assert agents.status_code == 200
    event_items = events.json()["items"]
    event_types = [event["type"] for event in event_items]
    assert "artifact.created" in event_types
    assert "run.completed" in event_types
    browser_started = next(event for event in event_items if event["type"] == "agent.started" and event["agent_type"] == "walker")
    browser_completed = next(event for event in event_items if event["type"] == "agent.completed" and event["agent_type"] == "walker")
    assert "Browser-use walkthrough started" in browser_started["message"]
    assert browser_started["payload"]["stage_label"] == "Browser-use walkthrough"
    assert browser_started["payload"]["action"] == "Starting browser-use walker"
    assert browser_started["payload"]["started_at"]
    assert browser_started["payload"]["max_steps"] == 7
    assert browser_started["payload"]["timeout_sec"] == 12.0
    assert browser_started["payload"]["progress"]["current_stage_label"] == "Browser-use walkthrough"
    assert browser_started["payload"]["progress"]["completed_stage_count"] >= 1
    assert "Browser-use walkthrough completed" in browser_completed["message"]
    assert browser_completed["payload"]["browser_steps"] == 1
    assert browser_completed["payload"]["timed_out"] is False
    assert browser_completed["payload"]["artifact_count"] >= 1
    assert browser_completed["payload"]["evidence_count"] == 1
    assert browser_completed["payload"]["stage_elapsed_ms"] >= 0
    walker_agent = next(agent for agent in agents.json()["items"] if agent["type"] == "walker")
    assert walker_agent["metrics"]["stage_label"] == "Browser-use walkthrough"
    assert walker_agent["metrics"]["browser_steps"] == 1
    assert walker_agent["metrics"]["timed_out"] is False
    assert walker_agent["metrics"]["agent_elapsed_ms"] >= 0
    assert detail["progress"]["current_stage_label"] == "Run completed"
    assert detail["progress"]["completed_stage_count"] == detail["progress"]["total_stage_count"]
    assert detail["progress"]["artifact_count"] >= len(artifact_items)
    assert detail["progress"]["screenshot_count"] == 2
    assert detail["progress"]["browser_history_count"] == 1
    assert detail["progress"]["evidence_count"] >= 1


def test_browser_use_default_verification_off_does_not_await_verification(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = (
        '{"completed": true, "notable_copy": ["Login"], "manual_verification_required": true}'
    )
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "browser-use", "out": "runs"},
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        events = client.get(f"/api/runs/{run_id}/events")

    assert detail["params"]["verification_mode"] == "off"
    assert detail["status"] == "succeeded"
    assert "run.awaiting_verification" not in [event["type"] for event in events.json()["items"]]


def test_browser_use_auto_verification_ignores_incidental_login_copy(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = '{"completed": true, "notable_copy": ["Login", "Sign in"]}'
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        events = client.get(f"/api/runs/{run_id}/events")

    assert detail["status"] == "succeeded"
    assert "run.completed" in [event["type"] for event in events.json()["items"]]
    assert "run.awaiting_verification" not in [event["type"] for event in events.json()["items"]]


def test_browser_use_auto_verification_ignores_completed_login_recommendation(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = (
        '{"completed": true, "manual_verification_required": false, '
        '"recommendation": "Redirect unauthenticated sessions to a login page before showing dashboard content."}'
    )
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        events = client.get(f"/api/runs/{run_id}/events")

    assert detail["status"] == "succeeded"
    assert "run.completed" in [event["type"] for event in events.json()["items"]]
    assert "run.awaiting_verification" not in [event["type"] for event in events.json()["items"]]


def test_browser_use_auto_verification_ignores_completed_captcha_copy(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = (
        '{"completed": true, "manual_verification_required": false, '
        '"friction_points": ["ALTCHA captcha verified and did not block this run."]}'
    )
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        events = client.get(f"/api/runs/{run_id}/events")

    assert detail["status"] == "succeeded"
    assert detail["progress"]["completed_scenarios"] == detail["progress"]["total_scenarios"]
    assert "run.completed" in [event["type"] for event in events.json()["items"]]
    assert "run.awaiting_verification" not in [event["type"] for event in events.json()["items"]]


def test_browser_use_auto_verification_honors_explicit_false_flag(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = '{"completed": true, "manual_verification_required": false}'
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        events = client.get(f"/api/runs/{run_id}/events")

    assert detail["status"] == "succeeded"
    assert "run.completed" in [event["type"] for event in events.json()["items"]]
    assert "run.awaiting_verification" not in [event["type"] for event in events.json()["items"]]


def test_browser_use_run_status_reflects_blocked_timeout_failed_and_verification(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    cases = [
        ("succeeded", "completed", '{"completed": true}', False, [], "off", "run.completed"),
        ("blocked", "blocked", "A loading state blocked progress.", False, [], "off", "run.blocked"),
        ("timeout", "blocked", "The run timed out.", True, ["timed out"], "off", "run.timeout"),
        ("failed", "blocked", "browser-use run failed: missing model", False, ["missing model"], "off", "run.failed"),
        (
            "awaiting_verification",
            "blocked",
            "manual_verification_required: true",
            False,
            ["manual_verification_required"],
            "auto",
            "run.awaiting_verification",
        ),
    ]

    with _client(tmp_path) as client:
        for expected_status, result_status, final_output, timed_out, errors, verification_mode, event_type in cases:
            _FakeBrowserUseWalker.result_status = result_status
            _FakeBrowserUseWalker.final_output = final_output
            _FakeBrowserUseWalker.timed_out = timed_out
            _FakeBrowserUseWalker.errors = errors
            _FakeBrowserUseWalker.screenshot_path = None
            _FakeBrowserUseWalker.history_path = None
            response = client.post(
                "/api/runs",
                json={
                    "plan_name": "smoke_plan.json",
                    "mode": "browser-use",
                    "out": "runs",
                    "verification_mode": verification_mode,
                },
            )
            assert response.status_code == 200
            run_id = response.json()["run_id"]
            detail = _wait_for_terminal(client, run_id)
            events = client.get(f"/api/runs/{run_id}/events")

            assert detail["status"] == expected_status
            assert event_type in [event["type"] for event in events.json()["items"]]
            if expected_status == "awaiting_verification":
                agents = client.get(f"/api/runs/{run_id}/agents")
                assert agents.status_code == 200
                director = next(agent for agent in agents.json()["items"] if agent["type"] == "director")
                assert director["status"] == "waiting"
                assert detail["completed_at"] is None
                assert detail["progress"]["completed_scenarios"] < detail["progress"]["total_scenarios"]


def test_browser_use_completed_run_ignores_intermediate_llm_timeout_text(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = (
        '{"completed": true, "manual_verification_required": false, '
        '"notes": ["LLM call timed out after 75 seconds, then the walkthrough recovered."]}'
    )
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        events = client.get(f"/api/runs/{run_id}/events")

    assert detail["status"] == "succeeded"
    assert "run.completed" in [event["type"] for event in events.json()["items"]]
    assert "run.timeout" not in [event["type"] for event in events.json()["items"]]


def test_browser_use_historical_timeout_reconciles_from_completed_evidence(tmp_path: Path) -> None:
    run_id = "run-20260102-030405-browser"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    completed_at = "2026-01-02T03:05:05Z"
    run_record = {
        "id": run_id,
        "status": "timeout",
        "mode": "browser-use",
        "research_goal": "Historical browser-use walkthrough.",
        "run_dir": f"runs/{run_id}",
        "created_at": "2026-01-02T03:04:05Z",
        "started_at": "2026-01-02T03:04:06Z",
        "completed_at": completed_at,
        "progress": {"total_scenarios": 1, "completed_scenarios": 1, "failed_scenarios": 0},
        "params": {"mode": "browser-use", "verification_mode": "auto"},
        "artifact_ids": [],
        "error": {"message": "One or more browser-use walkthroughs timed out.", "type": "timeout"},
        "metadata": {},
    }
    evidence = {
        "created_at": completed_at,
        "report_language": "en",
        "plan": {"research_goal": "Historical browser-use walkthrough."},
        "results": [
            {
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "Run browser-use task",
                        "status": "passed",
                        "observation": "LLM call timed out after 75 seconds before the final answer recovered.",
                    }
                ],
                "evidence": [
                    {
                        "kind": "browser_run",
                        "summary": '{"completed": true, "manual_verification_required": false}',
                        "data": {
                            "final_output": '{"completed": true, "manual_verification_required": false}',
                            "timed_out": False,
                            "errors": [],
                        },
                    }
                ],
                "metrics": {"timed_out": False},
                "errors": [],
            }
        ],
        "evidence": [],
    }
    (run_dir / "run.json").write_text(json.dumps(run_record), encoding="utf-8")
    (run_dir / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (run_dir / "report.md").write_text("# Browser report\n\nReady.", encoding="utf-8")
    (run_dir / "evaluation.json").write_text('{"overall_score": 1.0, "notes": []}', encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")

    with _client(tmp_path) as client:
        detail = client.get(f"/api/runs/{run_id}")
        runs = client.get("/api/runs")

    assert detail.status_code == 200
    assert detail.json()["run"]["status"] == "succeeded"
    assert detail.json()["run"]["error"] is None
    assert runs.status_code == 200
    assert runs.json()["items"][0]["status"] == "succeeded"


def test_browser_use_historical_awaiting_verification_reconciles_from_completed_evidence(tmp_path: Path) -> None:
    run_id = "run-20260102-030405-browser-awaiting"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    run_record = {
        "id": run_id,
        "status": "awaiting_verification",
        "mode": "browser-use",
        "research_goal": "Historical browser-use walkthrough.",
        "run_dir": f"runs/{run_id}",
        "created_at": "2026-01-02T03:04:05Z",
        "started_at": "2026-01-02T03:04:06Z",
        "completed_at": None,
        "progress": {"total_scenarios": 1, "completed_scenarios": 0, "failed_scenarios": 0},
        "params": {"mode": "browser-use", "verification_mode": "auto"},
        "artifact_ids": [],
        "error": {"message": "Browser-use reported that manual verification is required.", "type": "awaiting_verification"},
        "metadata": {},
    }
    evidence = {
        "created_at": "2026-01-02T03:05:05Z",
        "report_language": "en",
        "plan": {"research_goal": "Historical browser-use walkthrough."},
        "results": [
            {
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "status": "passed",
                        "url": "https://example.test/dashboard",
                        "observation": "Recommend redirecting unauthenticated users to a login page.",
                        "evidence_ids": ["ev-browser"],
                    }
                ],
                "metrics": {"timed_out": False},
                "errors": [],
            }
        ],
        "evidence": [
            {
                "id": "ev-browser",
                "kind": "browser_run",
                "summary": "Recommend redirecting unauthenticated users to a login page.",
                "url": "https://example.test/dashboard",
                "data": {
                    "final_output": (
                        '{"completed": true, "manual_verification_required": false, '
                        '"recommendation": "Redirect unauthenticated sessions to a login page."}'
                    ),
                    "timed_out": False,
                    "errors": [],
                },
            }
        ],
    }
    (run_dir / "run.json").write_text(json.dumps(run_record), encoding="utf-8")
    (run_dir / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (run_dir / "report.md").write_text("# Browser report\n\nReady.", encoding="utf-8")
    (run_dir / "evaluation.json").write_text('{"overall_score": 1.0, "notes": []}', encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")

    with _client(tmp_path) as client:
        detail = client.get(f"/api/runs/{run_id}")

    persisted = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert detail.status_code == 200
    assert detail.json()["run"]["status"] == "succeeded"
    assert detail.json()["run"]["error"] is None
    assert detail.json()["run"]["progress"]["completed_scenarios"] == 1
    assert persisted["status"] == "succeeded"
    assert persisted["completed_at"] is not None


def test_orphaned_running_browser_use_run_is_marked_failed(tmp_path: Path) -> None:
    run_id = "run-20260102-030405-orphaned"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    run_record = {
        "id": run_id,
        "status": "running",
        "mode": "browser-use",
        "research_goal": "Interrupted run",
        "run_dir": f"runs/{run_id}",
        "created_at": "2026-01-02T03:04:05Z",
        "started_at": "2026-01-02T03:04:06Z",
        "completed_at": None,
        "params": {"mode": "browser-use"},
        "progress": {
            "total_scenarios": 1,
            "completed_scenarios": 0,
            "failed_scenarios": 0,
            "current_stage": "walker",
            "current_stage_label": "Browser-use walkthrough",
            "current_stage_status": "running",
            "completed_stage_count": 1,
            "total_stage_count": 8,
        },
        "artifact_ids": [],
        "error": None,
        "metadata": {},
    }
    (run_dir / "run.json").write_text(json.dumps(run_record), encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")

    with _client(tmp_path) as client:
        detail = client.get(f"/api/runs/{run_id}")
        runs = client.get("/api/runs")

    persisted = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert detail.status_code == 200
    assert detail.json()["run"]["status"] == "failed"
    assert detail.json()["run"]["error"]["type"] == "interrupted"
    assert persisted["status"] == "failed"
    assert runs.status_code == 200
    assert runs.json()["items"][0]["status"] == "failed"


def test_auth_session_create_validates_request_and_path_safety(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    monkeypatch.setattr(runtime_module, "open_manual_auth_session", _fake_open_manual_auth_session)

    _FakeBrowserUseWalker.result_status = "blocked"
    _FakeBrowserUseWalker.final_output = "manual_verification_required: true"
    _FakeBrowserUseWalker.errors = ["manual_verification_required"]
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        run_response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
            },
        )
        run_id = run_response.json()["run_id"]
        assert _wait_for_terminal(client, run_id)["status"] == "awaiting_verification"

        bad_timeout = client.post(
            "/api/auth-sessions",
            json={"run_id": run_id, "url": "https://example.test/login", "timeout_sec": 0},
        )
        outside_profile = client.post(
            "/api/auth-sessions",
            json={
                "run_id": run_id,
                "url": "https://example.test/login",
                "browser_user_data_dir": str(tmp_path.parent / "outside-profile"),
            },
        )

    assert bad_timeout.status_code == 400
    assert outside_profile.status_code == 400
    assert "browser_user_data_dir" in outside_profile.json()["error"]["message"]


def test_auth_session_requires_awaiting_verification_run(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "open_manual_auth_session", _fake_open_manual_auth_session)

    with _client(tmp_path) as client:
        run_response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "mock", "out": "runs", "concurrency": 1},
        )
        run_id = run_response.json()["run_id"]
        assert _wait_for_terminal(client, run_id)["status"] == "succeeded"

        response = client.post(
            "/api/auth-sessions",
            json={"run_id": run_id, "url": "https://example.test/login"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "RUN_NOT_AWAITING_VERIFICATION"


def test_manual_login_first_session_can_start_browser_use_run(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    monkeypatch.setattr(runtime_module, "open_manual_auth_session", _fake_open_manual_auth_session)
    monkeypatch.setattr(runtime_module, "complete_manual_auth_session", _fake_complete_manual_auth_session)
    monkeypatch.setattr(runtime_module, "close_manual_auth_session", _fake_close_manual_auth_session)

    _FakeBrowserUseWalker.result_status = "completed"
    _FakeBrowserUseWalker.final_output = '{"completed": true, "urls_seen": ["https://example.test/dashboard"]}'
    _FakeBrowserUseWalker.errors = []
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None
    _FakeBrowserUseWalker.init_args = None

    with _client(tmp_path) as client:
        create_response = client.post(
            "/api/auth-sessions",
            json={
                "url": "https://example.test/login",
                "credentials_ref": "CLINK_UAT_ACCOUNT",
                "success_url_contains": ["/dashboard"],
                "login_url_contains": "/login",
                "timeout_sec": 120,
            },
        )
        assert create_response.status_code == 200
        session = create_response.json()["session"]
        session_id = session["session_id"]
        assert session["run_id"] is None
        assert session["status"] == "awaiting_user"
        assert session["auth_status"] == "awaiting_manual_login"

        poll_response = client.get(f"/api/auth-sessions/{session_id}")
        assert poll_response.status_code == 200
        assert poll_response.json()["session"]["auth_status"] == "awaiting_manual_login"

        confirm_response = client.post(
            f"/api/auth-sessions/{session_id}/confirm",
            json={"confirmed": True, "note": "login complete"},
        )
        assert confirm_response.status_code == 200
        confirmed = confirm_response.json()["session"]
        assert confirmed["status"] == "succeeded"
        assert confirmed["auth_status"] == "auth_ready"
        assert confirmed["storage_state_saved"] is True

        run_response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "auth_session_id": session_id,
                "verification_mode": "off",
            },
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        session_record = json.loads((tmp_path / ".prodwalk" / "auth-sessions" / f"{session_id}.json").read_text())

    assert detail["status"] == "succeeded"
    assert detail["params"]["auth_session_id"] == session_id
    assert detail["params"]["auth_status"] == "auth_ready"
    assert detail["params"]["verification_mode"] == "auto"
    assert detail["metadata"]["auth_session_id"] == session_id
    assert detail["metadata"]["auth_status"] == "auth_ready"
    assert _FakeBrowserUseWalker.init_args["user_data_dir"] == session_record["browser_user_data_dir"]
    assert _FakeBrowserUseWalker.init_args["storage_state"] == session_record["browser_storage_state"]


def test_auth_session_confirm_then_retry_starts_new_browser_use_run(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    monkeypatch.setattr(runtime_module, "open_manual_auth_session", _fake_open_manual_auth_session)
    monkeypatch.setattr(runtime_module, "complete_manual_auth_session", _fake_complete_manual_auth_session)
    monkeypatch.setattr(runtime_module, "close_manual_auth_session", _fake_close_manual_auth_session)

    _FakeBrowserUseWalker.result_status = "blocked"
    _FakeBrowserUseWalker.final_output = "manual_verification_required: true"
    _FakeBrowserUseWalker.errors = ["manual_verification_required"]
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        run_response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
                "verification_success_url_contains": ["/dashboard"],
                "verification_login_url_contains": "/login",
            },
        )
        run_id = run_response.json()["run_id"]
        detail = _wait_for_terminal(client, run_id)
        assert detail["status"] == "awaiting_verification"

        create_response = client.post(
            "/api/auth-sessions",
            json={
                "run_id": run_id,
                "url": "https://example.test/login",
                "browser_user_data_dir": ".prodwalk/browser-profiles/web-auth-test",
                "browser_storage_state": ".prodwalk/browser-profiles/web-auth-test/state.json",
                "success_url_contains": ["/dashboard"],
                "login_url_contains": "/login",
                "timeout_sec": 120,
            },
        )
        assert create_response.status_code == 200
        session = create_response.json()["session"]
        session_id = session["session_id"]
        assert session["status"] == "awaiting_user"

        confirm_response = client.post(
            f"/api/auth-sessions/{session_id}/confirm",
            json={"confirmed": True, "note": "done in visible browser"},
        )
        assert confirm_response.status_code == 200
        confirmed_session = confirm_response.json()["session"]
        assert confirmed_session["status"] == "succeeded"
        assert confirmed_session["storage_state_saved"] is True

        _FakeBrowserUseWalker.result_status = "completed"
        _FakeBrowserUseWalker.final_output = '{"completed": true, "urls_seen": ["https://example.test/dashboard"]}'
        _FakeBrowserUseWalker.errors = []
        retry_response = client.post(
            f"/api/runs/{run_id}/retry-after-verification",
            json={"session_id": session_id, "note": "retry after manual auth"},
        )
        assert retry_response.status_code == 200
        retry_payload = retry_response.json()
        retry_run_id = retry_payload["retry_run_id"]
        assert retry_payload["parent_run_id"] == run_id
        assert retry_payload["retry_of_run_id"] == run_id
        retry_detail = _wait_for_terminal(client, retry_run_id)
        original_detail = client.get(f"/api/runs/{run_id}").json()["run"]
        events = client.get(f"/api/runs/{run_id}/events").json()["items"]
        auth_artifacts = client.get(f"/api/runs/{run_id}/artifacts").json()["items"]

    assert retry_detail["status"] == "succeeded"
    assert retry_detail["params"]["auth_session_id"] == session_id
    assert retry_detail["params"]["auth_status"] == "auth_ready"
    assert retry_detail["metadata"]["auth_session_id"] == session_id
    assert retry_detail["metadata"]["auth_status"] == "auth_ready"
    assert retry_detail["metadata"]["retry_of_run_id"] == run_id
    assert retry_detail["metadata"]["verification_session_id"] == session_id
    assert original_detail["metadata"]["retry_run_id"] == retry_run_id
    assert original_detail["metadata"]["verification_session_id"] == session_id
    assert _FakeBrowserUseWalker.init_args["user_data_dir"] == str(
        (tmp_path / ".prodwalk/browser-profiles/web-auth-test").resolve()
    )
    assert _FakeBrowserUseWalker.init_args["storage_state"] == str(
        (tmp_path / ".prodwalk/browser-profiles/web-auth-test/state.json").resolve()
    )
    event_types = [event["type"] for event in events]
    assert "auth_session.started" in event_types
    assert "auth_session.awaiting_user" in event_types
    assert "auth_session.completed" in event_types
    assert "run.retry_started" in event_types
    assert any(item["path"] == f"auth-sessions/{session_id}.json" for item in auth_artifacts)


def test_verification_confirm_records_without_faking_resume(tmp_path: Path, monkeypatch) -> None:
    _write_plan(tmp_path)
    monkeypatch.setattr(runtime_module, "BrowserUseLocalWalker", _FakeBrowserUseWalker)
    monkeypatch.setattr(
        runtime_module.RunRuntime,
        "_browser_use_readiness_errors",
        lambda self, request, *, user_data_dir, storage_state: [],
    )
    _FakeBrowserUseWalker.result_status = "blocked"
    _FakeBrowserUseWalker.final_output = "manual_verification_required: true"
    _FakeBrowserUseWalker.errors = ["manual_verification_required"]
    _FakeBrowserUseWalker.timed_out = False
    _FakeBrowserUseWalker.screenshot_path = None
    _FakeBrowserUseWalker.history_path = None

    with _client(tmp_path) as client:
        run_response = client.post(
            "/api/runs",
            json={
                "plan_name": "smoke_plan.json",
                "mode": "browser-use",
                "out": "runs",
                "verification_mode": "auto",
            },
        )
        run_id = run_response.json()["run_id"]
        assert _wait_for_terminal(client, run_id)["status"] == "awaiting_verification"

        response = client.post(
            f"/api/runs/{run_id}/verification/confirm",
            json={"confirmed": True, "note": "legacy confirm"},
        )
        detail = client.get(f"/api/runs/{run_id}").json()["run"]

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_verification"
    assert response.json()["retry_run_id"] is None
    assert "does not resume" in response.json()["message"]
    assert detail["status"] == "awaiting_verification"


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


def test_walkthrough_map_endpoint_rebuilds_historical_run_and_artifacts_include_map(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    run_dir = _write_historical_map_run(tmp_path)
    assert not (run_dir / "walkthrough_map.json").exists()

    with _client(tmp_path) as client:
        map_response = client.get(f"/api/runs/{run_dir.name}/map")
        artifacts_response = client.get(f"/api/runs/{run_dir.name}/artifacts")

    assert map_response.status_code == 200
    payload = map_response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["artifact_id"] == "art_walkthrough_map"
    assert (run_dir / "walkthrough_map.json").exists()
    customer_node = next(node for node in payload["nodes"] if node["route"] == "/customers/:id")
    assert customer_node["name"] == "Customer Profile"
    assert customer_node["page_type"] == "detail"
    assert customer_node["purpose"] == "Review customer profile and activity."
    assert "Edit customer" in customer_node["key_controls"]
    assert customer_node["page_evidence"][0]["artifact_ids"]
    assert customer_node["page_evidence"][0]["screenshot_artifact_ids"]
    assert any(insight["source"] == "page_evidence" for insight in customer_node["observations"])
    assert customer_node["screenshot_evidence"][0]["path"] == "screenshots/customer.png"
    serialized = json.dumps(payload)
    assert "C:" not in serialized
    assert "token=secret" not in serialized

    assert artifacts_response.status_code == 200
    map_artifact = next(item for item in artifacts_response.json()["items"] if item["type"] == "walkthrough_map")
    assert map_artifact["id"] == "art_walkthrough_map"
    assert map_artifact["metadata"]["content_url"] == f"/api/runs/{run_dir.name}/artifacts/art_walkthrough_map/content"


def test_walkthrough_map_endpoint_rebuilds_stale_existing_map(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    run_dir = _write_historical_map_run(tmp_path)
    stale_payload = {
        "run_id": run_dir.name,
        "artifact_id": "art_walkthrough_map",
        "schema_version": "1.0",
        "summary": {"node_count": 1, "edge_count": 0},
        "nodes": [{"id": "stale", "name": "Clink", "route": "/customers/123", "status": "error"}],
        "edges": [],
        "layout": {"algorithm": "stale", "nodes": {}},
        "warnings": [],
    }
    (run_dir / "walkthrough_map.json").write_text(json.dumps(stale_payload), encoding="utf-8")

    with _client(tmp_path) as client:
        response = client.get(f"/api/runs/{run_dir.name}/map")

    assert response.status_code == 200
    payload = response.json()
    assert payload["build_version"] == WALKTHROUGH_MAP_BUILD_VERSION
    assert payload["summary"]["node_count"] > 1
    assert all(node["id"] != "stale" for node in payload["nodes"])
    customer_node = next(node for node in payload["nodes"] if node["route"] == "/customers/:id")
    assert customer_node["name"] == "Customer Profile"


def test_walkthrough_map_endpoint_returns_404_without_evidence(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    run_dir = tmp_path / "runs" / "run-20260102-030405-no-evidence"
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text("# Missing evidence\n", encoding="utf-8")

    with _client(tmp_path) as client:
        response = client.get(f"/api/runs/{run_dir.name}/map")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"


def test_delete_run_removes_run_directory_and_record(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "mock", "out": "runs", "concurrency": 1},
        )
        run_id = response.json()["run_id"]
        assert _wait_for_terminal(client, run_id)["status"] == "succeeded"
        run_dir = tmp_path / "runs" / run_id
        assert run_dir.exists()

        delete_response = client.delete(f"/api/runs/{run_id}")
        missing_response = client.get(f"/api/runs/{run_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"
    assert not run_dir.exists()
    assert missing_response.status_code == 404


def test_clear_runs_removes_historical_and_completed_records(tmp_path: Path) -> None:
    _write_plan(tmp_path)
    historical_dir = _write_historical_run(tmp_path)
    with _client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            json={"plan_name": "smoke_plan.json", "mode": "mock", "out": "runs", "concurrency": 1},
        )
        run_id = response.json()["run_id"]
        assert _wait_for_terminal(client, run_id)["status"] == "succeeded"

        clear_response = client.delete("/api/runs")
        runs_response = client.get("/api/runs")

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert run_id in payload["deleted_run_ids"]
    assert historical_dir.name in payload["deleted_run_ids"]
    assert payload["skipped_run_ids"] == []
    assert runs_response.json()["items"] == []
    assert not historical_dir.exists()
    assert not (tmp_path / "runs" / run_id).exists()


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
