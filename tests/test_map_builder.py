from __future__ import annotations

import json
from pathlib import Path

from prodwalk.agents.map_builder import build_walkthrough_map, canonicalize_url


def test_canonicalize_url_drops_tracking_and_preserves_hash_route() -> None:
    canonical = canonicalize_url(
        "https://app.example.test/?utm_source=newsletter&token=secret#/customers/123?utm_campaign=x&view=summary"
    )

    assert canonical is not None
    assert canonical.normalized_route == "#/customers/:id?view=summary"
    assert canonical.dynamic_route_pattern == "#/customers/:id?view=summary"
    assert "utm_" not in canonical.canonical_url
    assert "token" not in canonical.canonical_url
    assert canonical.canonical_url == "https://app.example.test/#/customers/:id?view=summary"


def test_build_map_merges_dynamic_routes_and_links_screenshots_without_local_paths() -> None:
    payload = {
        "created_at": "2026-06-24T00:00:00Z",
        "plan": {
            "products": [
                {
                    "name": "Example Console",
                    "kind": "owned",
                    "url": "https://app.example.test/dashboard",
                }
            ]
        },
        "results": [
            {
                "product": "Example Console",
                "product_kind": "owned",
                "scenario_id": "smoke",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Loaded the first customer detail.",
                        "url": "https://app.example.test/customers/123?utm_source=ad&token=secret",
                        "screenshot": r"C:\Users\agent\AppData\Local\Temp\customer-123.png",
                        "evidence_ids": ["ev-step-1"],
                    },
                    {
                        "index": 2,
                        "action": "click",
                        "status": "passed",
                        "observation": 'Clicked a role=menuitem "Customers"',
                        "url": "https://app.example.test/customers/456?page=2&utm_campaign=ad",
                        "evidence_ids": ["ev-step-2"],
                    },
                    {
                        "index": 3,
                        "action": "click",
                        "status": "passed",
                        "observation": 'Clicked a role=menuitem "Orders"',
                        "url": "https://app.example.test/orders",
                        "evidence_ids": ["ev-step-3"],
                    },
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-step-1",
                "product": "Example Console",
                "scenario_id": "smoke",
                "kind": "browser_step",
                "title": "Customer Detail",
                "summary": "Loaded the first customer detail.",
                "url": "https://app.example.test/customers/123?token=secret",
                "screenshot": r"C:\Users\agent\AppData\Local\Temp\customer-123.png",
                "data": {"title": "Customer - Example", "screenshot_path": r"C:\Users\agent\AppData\Local\Temp\customer-123.png"},
            },
            {
                "id": "ev-step-2",
                "product": "Example Console",
                "scenario_id": "smoke",
                "kind": "browser_step",
                "title": "Customer Detail",
                "summary": "Loaded another customer detail.",
                "url": "https://app.example.test/customers/456",
                "data": {"title": "Customer - Example"},
            },
            {
                "id": "ev-step-3",
                "product": "Example Console",
                "scenario_id": "smoke",
                "kind": "browser_step",
                "title": "Orders",
                "summary": "Opened orders.",
                "url": "https://app.example.test/orders",
                "data": {"title": "Orders - Example"},
            },
        ],
    }
    artifacts = [
        {
            "id": "art_evidence_json",
            "run_id": "run-test",
            "type": "evidence_json",
            "title": "evidence.json",
            "path": "evidence.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:00Z",
            "metadata": {"content_url": "/api/runs/run-test/artifacts/art_evidence_json/content"},
        },
        {
            "id": "art_screenshot_customer",
            "run_id": "run-test",
            "type": "screenshot",
            "title": "customer-123.png",
            "path": "screenshots/customer-123.png",
            "media_type": "image/png",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {
                "content_url": "/api/runs/run-test/artifacts/art_screenshot_customer/content",
                "screenshot_url": "/api/runs/run-test/screenshots/customer-123.png",
            },
        },
    ]

    walkthrough_map = build_walkthrough_map(
        run_id="run-test",
        evidence_payload=payload,
        artifacts=artifacts,
        browser_histories=[],
        generated_at="2026-06-24T00:00:02Z",
    )

    assert walkthrough_map["schema_version"] == "1.0"
    customer_nodes = [node for node in walkthrough_map["nodes"] if node["route"] == "/customers/:id"]
    assert len(customer_nodes) == 1
    customer = customer_nodes[0]
    assert customer["visit_count"] == 2
    assert customer["metadata"]["dynamic_route_pattern"] == "/customers/:id"
    assert customer["screenshot_evidence"][0]["artifact_id"] == "art_screenshot_customer"
    assert customer["screenshot_evidence"][0]["path"] == "screenshots/customer-123.png"
    assert walkthrough_map["summary"]["edge_count"] == 1

    serialized = json.dumps(walkthrough_map)
    assert "C:" not in serialized
    assert "AppData" not in serialized
    assert "token=secret" not in serialized
    assert "utm_" not in serialized


def test_build_map_works_without_browser_history() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/a"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "smoke",
                "status": "completed",
                "steps": [
                    {"index": 1, "action": "navigate", "status": "passed", "observation": "A", "url": "https://example.test/a"},
                    {"index": 2, "action": "click", "status": "passed", "observation": "B", "url": "https://example.test/b"},
                ],
            }
        ],
        "evidence": [],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-no-history",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    assert walkthrough_map["summary"]["node_count"] == 2
    assert walkthrough_map["summary"]["edge_count"] == 1
    assert any(warning["code"] == "MAP_NO_BROWSER_HISTORY" for warning in walkthrough_map["warnings"])


def test_build_map_layout_handles_cyclic_navigation() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/a"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "cycle",
                "status": "completed",
                "steps": [
                    {"index": 1, "action": "navigate", "status": "passed", "observation": "A", "url": "https://example.test/a"},
                    {"index": 2, "action": "click", "status": "passed", "observation": "B", "url": "https://example.test/b"},
                    {"index": 3, "action": "click", "status": "passed", "observation": "A again", "url": "https://example.test/a"},
                ],
            }
        ],
        "evidence": [],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-cycle",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    assert walkthrough_map["summary"]["node_count"] == 2
    assert walkthrough_map["summary"]["edge_count"] == 2
    assert set(walkthrough_map["layout"]["nodes"]) == {node["id"] for node in walkthrough_map["nodes"]}


def test_real_sample_builds_clear_nodes_edges_and_safe_screenshots() -> None:
    run_dir = Path(__file__).resolve().parents[1] / "runs" / "run-20260623-190713-568156"
    payload = json.loads((run_dir / "evidence.json").read_text(encoding="utf-8"))
    artifacts = json.loads((run_dir / "artifacts.json").read_text(encoding="utf-8"))
    histories = []
    for artifact in artifacts:
        if artifact.get("type") != "browser_history":
            continue
        histories.append(
            {
                "artifact_id": artifact["id"],
                "path": artifact["path"],
                "payload": json.loads((run_dir / artifact["path"]).read_text(encoding="utf-8")),
            }
        )

    walkthrough_map = build_walkthrough_map(
        run_id=run_dir.name,
        evidence_payload=payload,
        artifacts=artifacts,
        browser_histories=histories,
        generated_at="2026-06-24T00:00:00Z",
    )

    assert walkthrough_map["schema_version"] == "1.0"
    assert walkthrough_map["summary"]["node_count"] >= 9
    assert walkthrough_map["summary"]["edge_count"] >= 8
    assert walkthrough_map["summary"]["screenshot_count"] >= 15
    assert any(node["route"] == "/analytics" for node in walkthrough_map["nodes"])
    assert any(node["route"] == "/settings/merchant/:id" for node in walkthrough_map["nodes"])
    names_by_route = {node["route"]: node["name"] for node in walkthrough_map["nodes"]}
    assert names_by_route["/data-insights/core-metrics"] == "Core Metrics"
    assert names_by_route["/transactions"] == "Transactions"
    assert names_by_route["/balances"] == "Balances"
    assert names_by_route["/settings/merchant"] == "Merchant Settings"
    assert all(
        screenshot["path"].startswith("screenshots/")
        for node in walkthrough_map["nodes"]
        for screenshot in node["screenshot_evidence"]
    )

    serialized = json.dumps(walkthrough_map)
    assert "C:/" not in serialized
    assert "user_data_dir" not in serialized
    assert "storage_state" not in serialized
    assert "clink_uat_account_password" not in serialized
