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


def test_build_map_prefers_real_page_screenshot_over_browser_state_thumbnail() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/balances"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "screenshots",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Captured balances page.",
                        "url": "https://example.test/balances",
                        "evidence_ids": ["ev-balances"],
                    }
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-balances",
                "product": "Example",
                "scenario_id": "screenshots",
                "kind": "browser_step",
                "title": "Balances",
                "summary": "Captured balances page.",
                "url": "https://example.test/balances",
                "data": {
                    "page_evidence": {
                        "status": "completed",
                        "title": "Balances",
                        "screenshot_paths": [
                            "screenshots/ev-example-step-1-shot-1.png",
                            "screenshots/ev-example-step-1-full-page.png",
                            "screenshots/ev-example-step-1.png",
                        ],
                    }
                },
            }
        ],
    }
    artifacts = [
        {
            "id": "art_low_information_state",
            "run_id": "run-screenshot-choice",
            "type": "screenshot",
            "title": "ev-example-step-1-shot-1.png",
            "path": "screenshots/ev-example-step-1-shot-1.png",
            "media_type": "image/png",
            "size_bytes": 7200,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
        },
        {
            "id": "art_loading_full_page",
            "run_id": "run-screenshot-choice",
            "type": "screenshot",
            "title": "ev-example-step-1-full-page.png",
            "path": "screenshots/ev-example-step-1-full-page.png",
            "media_type": "image/png",
            "size_bytes": 98000,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
        },
        {
            "id": "art_real_page",
            "run_id": "run-screenshot-choice",
            "type": "screenshot",
            "title": "ev-example-step-1.png",
            "path": "screenshots/ev-example-step-1.png",
            "media_type": "image/png",
            "size_bytes": 76000,
            "created_at": "2026-06-24T00:00:02Z",
            "metadata": {},
        },
    ]

    walkthrough_map = build_walkthrough_map(
        run_id="run-screenshot-choice",
        evidence_payload=payload,
        artifacts=artifacts,
        browser_histories=[],
        generated_at="2026-06-24T00:00:03Z",
    )

    node = next(item for item in walkthrough_map["nodes"] if item["route"] == "/balances")
    assert len(node["screenshot_evidence"]) == 1
    assert node["screenshot_evidence"][0]["artifact_id"] == "art_real_page"
    assert node["primary_screenshot_artifact_id"] == "art_real_page"


def test_build_map_uses_page_evidence_for_node_insights_controls_and_screenshots() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/payment-links"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "page-evidence",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Captured page evidence.",
                        "url": "https://example.test/payment-links?token=secret&utm_source=test",
                        "evidence_ids": ["ev-payment-links"],
                    }
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-payment-links",
                "product": "Example",
                "scenario_id": "page-evidence",
                "kind": "browser_step",
                "title": "Browser step 1",
                "summary": "Captured page evidence.",
                "url": "https://example.test/payment-links?token=secret",
                "data": {
                    "page_evidence": {
                        "status": "completed",
                        "title": "Payment Links",
                        "page_type": "list",
                        "purpose": "Manage payment links and checkout URLs.",
                        "manifest_path": "page-evidence/payment/manifest.json",
                        "artifact_paths": [
                            "page-evidence/payment/text.json",
                            "page-evidence/payment/elements.json",
                            "page-evidence/payment/accessibility_tree.json",
                            "page-evidence/payment/manifest.json",
                        ],
                        "full_page_screenshot_path": "screenshots/payment-full.png",
                        "screenshot_paths": ["screenshots/payment-full.png"],
                        "network_event_count": 3,
                    }
                },
            }
        ],
    }
    artifacts = [
        {
            "id": "art_screenshot_payment_full",
            "run_id": "run-page-evidence",
            "type": "screenshot",
            "title": "payment-full.png",
            "path": "screenshots/payment-full.png",
            "media_type": "image/png",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {"content_url": "/api/runs/run-page-evidence/artifacts/art_screenshot_payment_full/content"},
        },
        {
            "id": "art_page_text_payment",
            "run_id": "run-page-evidence",
            "type": "page_text",
            "title": "text.json",
            "path": "page-evidence/payment/text.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
            "payload": {
                "text": "Payment Links Search Create link C:/Users/agent/profile /tmp/playwright-profile storage_state=/home/agent/state.json token=secret"
            },
        },
        {
            "id": "art_page_elements_payment",
            "run_id": "run-page-evidence",
            "type": "page_elements",
            "title": "elements.json",
            "path": "page-evidence/payment/elements.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
            "payload": {
                "items": [
                    {"tag": "button", "text": "Create link", "visible": True, "disabled": False},
                    {"tag": "a", "text": "Create payment link", "href": "https://example.test/payment-links/new", "visible": True, "disabled": False},
                    {"tag": "button", "text": "Open filters", "visible": True, "disabled": False},
                    {"tag": "input", "placeholder": "Search links", "type": "search", "visible": True, "disabled": False},
                    {"tag": "input", "placeholder": "Password", "type": "password", "visible": True, "disabled": False},
                ]
            },
        },
        {
            "id": "art_accessibility_payment",
            "run_id": "run-page-evidence",
            "type": "accessibility_tree",
            "title": "accessibility_tree.json",
            "path": "page-evidence/payment/accessibility_tree.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
            "payload": {"nodes": [{"role": {"value": "button"}, "name": {"value": "Copy link"}}]},
        },
        {
            "id": "art_manifest_payment",
            "run_id": "run-page-evidence",
            "type": "page_evidence_manifest",
            "title": "manifest.json",
            "path": "page-evidence/payment/manifest.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
            "payload": {"title": "Payment Links", "url": "https://example.test/payment-links?token=secret"},
        },
    ]

    walkthrough_map = build_walkthrough_map(
        run_id="run-page-evidence",
        evidence_payload=payload,
        artifacts=artifacts,
        browser_histories=[],
        generated_at="2026-06-24T00:00:02Z",
    )

    node = next(item for item in walkthrough_map["nodes"] if item["route"] == "/payment-links")
    assert node["name"] == "Payment Links"
    assert node["page_type"] == "list"
    assert node["purpose"] == "Manage payment links and checkout URLs."
    assert "Create link" in node["key_controls"]
    assert "Search links" in node["key_controls"]
    assert "Copy link" in node["key_controls"]
    assert any(entry["label"] == "Create payment link" and entry["target_url"] == "https://example.test/payment-links/new" for entry in node["entries"])
    assert any(entry["label"] == "Open filters" and entry["status"] == "unvisited" for entry in node["entries"])
    assert node["page_evidence"][0]["entries"]
    assert walkthrough_map["summary"]["entry_count"] >= 3
    assert node["screenshot_evidence"][0]["artifact_id"] == "art_screenshot_payment_full"
    assert node["page_evidence"][0]["artifact_ids"] == [
        "art_manifest_payment",
        "art_page_text_payment",
        "art_page_elements_payment",
        "art_accessibility_payment",
    ]
    assert node["page_evidence"][0]["screenshot_artifact_ids"] == ["art_screenshot_payment_full"]
    assert any(ref["artifact_id"] == "art_page_elements_payment" for ref in node["page_evidence"][0]["artifacts"])
    assert node["metadata"]["page_evidence"]["network_event_count"] == 3
    assert node["metadata"]["page_evidence"]["element_count"] == 5
    assert any(insight["source"] == "page_evidence" for insight in node["observations"])

    serialized = json.dumps(walkthrough_map)
    assert "C:/Users" not in serialized
    assert "/tmp/playwright-profile" not in serialized
    assert "storage_state=/home/agent/state.json" not in serialized
    assert "token=secret" not in serialized
    assert "storage_state" not in serialized


def test_build_map_accepts_page_evidence_without_control_list() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/analytics"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "page-evidence-empty-controls",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Navigated to https://example.test/analytics and captured analytics page evidence.",
                        "url": "https://example.test/analytics",
                        "evidence_ids": ["ev-analytics"],
                    }
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-analytics",
                "product": "Example",
                "scenario_id": "page-evidence-empty-controls",
                "kind": "browser_step",
                "title": "Browser step 1",
                "summary": "Captured analytics page evidence.",
                "url": "https://example.test/analytics",
                "data": {
                    "page_evidence": {
                        "status": "partial",
                        "title": "Clink",
                        "manifest_path": "page-evidence/analytics/manifest.json",
                        "artifact_paths": ["page-evidence/analytics/manifest.json"],
                        "screenshot_paths": ["screenshots/analytics.png"],
                        "errors": ["Navigation/capture load issue"],
                    }
                },
            }
        ],
    }
    artifacts = [
        {
            "id": "art_screenshot_analytics",
            "run_id": "run-page-evidence-no-controls",
            "type": "screenshot",
            "title": "analytics.png",
            "path": "screenshots/analytics.png",
            "media_type": "image/png",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
        },
        {
            "id": "art_manifest_analytics",
            "run_id": "run-page-evidence-no-controls",
            "type": "page_evidence_manifest",
            "title": "manifest.json",
            "path": "page-evidence/analytics/manifest.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
            "payload": {"title": "Clink", "url": "https://example.test/analytics"},
        },
    ]

    walkthrough_map = build_walkthrough_map(
        run_id="run-page-evidence-no-controls",
        evidence_payload=payload,
        artifacts=artifacts,
        browser_histories=[],
        generated_at="2026-06-24T00:00:02Z",
    )

    node = next(item for item in walkthrough_map["nodes"] if item["route"] == "/analytics")
    assert node["page_evidence"][0]["controls"] == []
    assert node["page_evidence"][0]["artifact_ids"] == ["art_manifest_analytics"]
    assert node["page_evidence"][0]["screenshot_artifact_ids"] == ["art_screenshot_analytics"]
    assert any("https://example.test/analytics" in item["summary"] for item in node["observations"])


def test_llm_timeout_text_does_not_mark_page_error() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/transactions"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "timeout",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Error: LLM call timed out after 75 seconds",
                        "url": "https://example.test/transactions",
                    }
                ],
            }
        ],
        "evidence": [],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-timeout",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    node = next(item for item in walkthrough_map["nodes"] if item["route"] == "/transactions")
    assert node["status"] == "visited"
    assert node["page_type"] == "list"


def test_generic_title_does_not_override_route_name() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/balances"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "generic-title",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Captured balances.",
                        "url": "https://example.test/balances",
                        "evidence_ids": ["ev-balances"],
                    }
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-balances",
                "product": "Example",
                "scenario_id": "generic-title",
                "kind": "browser_step",
                "title": "Home",
                "summary": "Captured balances.",
                "url": "https://example.test/balances",
                "data": {"title": "Home", "page_evidence": {"status": "completed", "title": "Clink"}},
            }
        ],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-generic-title",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    node = next(item for item in walkthrough_map["nodes"] if item["route"] == "/balances")
    assert node["name"] == "Balances"


def test_entry_label_without_target_url_links_existing_route_node() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/analytics"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "label-link",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Captured analytics.",
                        "url": "https://example.test/analytics",
                        "evidence_ids": ["ev-analytics"],
                    },
                    {
                        "index": 2,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Transactions page exists.",
                        "url": "https://example.test/transactions",
                        "evidence_ids": ["ev-transactions"],
                    },
                    {
                        "index": 3,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Merchant settings page exists.",
                        "url": "https://example.test/settings/merchant",
                        "evidence_ids": ["ev-settings"],
                    },
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-analytics",
                "product": "Example",
                "scenario_id": "label-link",
                "kind": "browser_step",
                "title": "Analytics",
                "summary": "Captured analytics.",
                "url": "https://example.test/analytics",
                "data": {
                    "page_evidence": {
                        "status": "completed",
                        "title": "Analytics",
                        "entries": [
                            {"label": "Transactions", "role": "menuitem"},
                            {"label": "Merchant Settings", "role": "menuitem"},
                        ],
                    }
                },
            },
            {
                "id": "ev-transactions",
                "product": "Example",
                "scenario_id": "label-link",
                "kind": "browser_step",
                "title": "Transactions",
                "summary": "Transactions page exists.",
                "url": "https://example.test/transactions",
                "data": {},
            },
            {
                "id": "ev-settings",
                "product": "Example",
                "scenario_id": "label-link",
                "kind": "browser_step",
                "title": "Merchant Settings",
                "summary": "Merchant settings page exists.",
                "url": "https://example.test/settings/merchant",
                "data": {},
            },
        ],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-label-link",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    analytics = next(item for item in walkthrough_map["nodes"] if item["route"] == "/analytics")
    transactions = next(item for item in walkthrough_map["nodes"] if item["route"] == "/transactions")
    merchant_settings = next(item for item in walkthrough_map["nodes"] if item["route"] == "/settings/merchant")
    transactions_entry = next(item for item in analytics["entries"] if item["label"] == "Transactions")
    settings_entry = next(item for item in analytics["entries"] if item["label"] == "Merchant Settings")

    assert transactions_entry["target_node_id"] == transactions["id"]
    assert transactions_entry["status"] == "visited"
    assert settings_entry["target_node_id"] == merchant_settings["id"]
    assert settings_entry["status"] == "visited"
    assert any(edge["source"] == analytics["id"] and edge["target"] == transactions["id"] for edge in walkthrough_map["edges"])
    assert any(edge["source"] == analytics["id"] and edge["target"] == merchant_settings["id"] for edge in walkthrough_map["edges"])


def test_action_entry_without_route_match_stays_unvisited() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/settings/rules"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "action-entry",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Captured rules settings.",
                        "url": "https://example.test/settings/rules",
                        "evidence_ids": ["ev-rules"],
                    },
                    {
                        "index": 2,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Settings page exists.",
                        "url": "https://example.test/settings",
                    },
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-rules",
                "product": "Example",
                "scenario_id": "action-entry",
                "kind": "browser_step",
                "title": "Rules Settings",
                "summary": "Captured rules settings.",
                "url": "https://example.test/settings/rules",
                "data": {
                    "page_evidence": {
                        "status": "completed",
                        "title": "Rules Settings",
                        "entries": [
                            {"label": "Reset", "role": "button"},
                            {"label": "+ New rule", "role": "button"},
                            {"label": "OM", "role": "menuitem"},
                        ],
                    }
                },
            }
        ],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-action-entry",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    rules = next(item for item in walkthrough_map["nodes"] if item["route"] == "/settings/rules")
    entries = {entry["label"]: entry for entry in rules["entries"]}
    assert entries["Reset"]["target_node_id"] is None
    assert entries["Reset"]["status"] == "unvisited"
    assert entries["+ New rule"]["target_node_id"] is None
    assert entries["+ New rule"]["status"] == "unvisited"
    assert entries["OM"]["target_node_id"] is None
    assert entries["OM"]["status"] == "unvisited"


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


def test_build_map_marks_crawler_only_pages_as_discovered() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/dashboard"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "full-crawl",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Loaded dashboard.",
                        "url": "https://example.test/dashboard",
                        "evidence_ids": ["ev-dashboard"],
                    },
                    {
                        "index": 2,
                        "action": "discover_page",
                        "status": "passed",
                        "observation": "Discovered page during full same-origin crawl.",
                        "url": "https://example.test/settings/team",
                        "evidence_ids": ["ev-discovered-settings"],
                    }
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-dashboard",
                "product": "Example",
                "scenario_id": "full-crawl",
                "kind": "browser_step",
                "title": "Dashboard",
                "summary": "Loaded dashboard.",
                "url": "https://example.test/dashboard",
                "data": {},
            },
            {
                "id": "ev-discovered-settings",
                "product": "Example",
                "scenario_id": "full-crawl",
                "kind": "browser_step",
                "title": "Browser step 1",
                "summary": "Discovered page during full same-origin crawl.",
                "url": "https://example.test/settings/team",
                "data": {
                    "page_discovery": {
                        "depth": 1,
                        "source_url": "https://example.test/dashboard",
                        "source_label": "Team Settings",
                        "links": ["https://example.test/settings/team/members"],
                        "click_candidates": [{"label": "Invite member", "tag": "button", "role": "button"}],
                        "click_results": [
                            {
                                "label": "Invite member",
                                "tag": "button",
                                "role": "button",
                                "status": "visited",
                                "target_url": "https://example.test/settings/team",
                                "same_url": True,
                            }
                        ],
                    }
                },
            }
        ],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-discovered",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    node = next(item for item in walkthrough_map["nodes"] if item["route"] == "/settings/team")
    dashboard = next(item for item in walkthrough_map["nodes"] if item["route"] == "/dashboard")
    assert node["status"] == "discovered"
    assert node["metadata"]["discovered_from_node_id"] == dashboard["id"]
    assert any(entry["label"] == "Members" and entry["target_url"] == "https://example.test/settings/team/members" for entry in node["entries"])
    assert any(entry["label"] == "Invite member" and entry["status"] == "visited" for entry in node["entries"])
    assert any(
        edge["source"] == dashboard["id"]
        and edge["target"] == node["id"]
        and edge["metadata"]["map_relation"] == "discovered_from"
        and edge["label"] == "Team Settings"
        for edge in walkthrough_map["edges"]
    )
    assert walkthrough_map["summary"]["discovered_count"] == 1


def test_build_map_does_not_create_fake_unvisited_entries_from_route_controls() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/analytics"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "visited-page",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Opened analytics page.",
                        "url": "https://example.test/analytics",
                    }
                ],
            }
        ],
        "evidence": [],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-no-fake-entry",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    analytics = next(item for item in walkthrough_map["nodes"] if item["route"] == "/analytics")
    assert analytics["status"] == "visited"
    assert analytics["entries"] == []
    assert walkthrough_map["summary"]["unvisited_entry_count"] == 0


def test_build_map_links_page_entries_to_existing_target_nodes() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/dashboard"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "entry-link",
                "status": "completed",
                "steps": [
                    {
                        "index": 1,
                        "action": "observe",
                        "status": "passed",
                        "observation": "Captured dashboard.",
                        "url": "https://example.test/dashboard",
                        "evidence_ids": ["ev-dashboard"],
                    },
                    {
                        "index": 2,
                        "action": "navigate",
                        "status": "passed",
                        "observation": "Transactions page exists.",
                        "url": "https://example.test/transactions",
                        "evidence_ids": ["ev-transactions"],
                    },
                ],
            }
        ],
        "evidence": [
            {
                "id": "ev-dashboard",
                "product": "Example",
                "scenario_id": "entry-link",
                "kind": "browser_step",
                "title": "Dashboard",
                "summary": "Captured dashboard.",
                "url": "https://example.test/dashboard",
                "data": {
                    "page_evidence": {
                        "status": "completed",
                        "title": "Dashboard",
                        "manifest_path": "page-evidence/dashboard/manifest.json",
                        "artifact_paths": ["page-evidence/dashboard/elements.json", "page-evidence/dashboard/manifest.json"],
                    }
                },
            },
            {
                "id": "ev-transactions",
                "product": "Example",
                "scenario_id": "entry-link",
                "kind": "browser_step",
                "title": "Transactions",
                "summary": "Transactions page exists.",
                "url": "https://example.test/transactions",
                "data": {},
            },
        ],
    }
    artifacts = [
        {
            "id": "art_dashboard_elements",
            "run_id": "run-entry-link",
            "type": "page_elements",
            "title": "elements.json",
            "path": "page-evidence/dashboard/elements.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
            "payload": {
                "items": [
                    {
                        "tag": "a",
                        "role": "menuitem",
                        "text": "Transactions",
                        "href": "https://example.test/transactions",
                        "visible": True,
                        "disabled": False,
                    }
                ]
            },
        },
        {
            "id": "art_dashboard_manifest",
            "run_id": "run-entry-link",
            "type": "page_evidence_manifest",
            "title": "manifest.json",
            "path": "page-evidence/dashboard/manifest.json",
            "media_type": "application/json",
            "size_bytes": 10,
            "created_at": "2026-06-24T00:00:01Z",
            "metadata": {},
            "payload": {"title": "Dashboard", "url": "https://example.test/dashboard"},
        },
    ]

    walkthrough_map = build_walkthrough_map(
        run_id="run-entry-link",
        evidence_payload=payload,
        artifacts=artifacts,
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    dashboard = next(item for item in walkthrough_map["nodes"] if item["route"] == "/dashboard")
    transactions = next(item for item in walkthrough_map["nodes"] if item["route"] == "/transactions")
    entry = next(item for item in dashboard["entries"] if item["label"] == "Transactions")

    assert entry["target_node_id"] == transactions["id"]
    assert entry["status"] == "visited"
    assert any(
        edge["source"] == dashboard["id"]
        and edge["target"] == transactions["id"]
        and "Transactions" in edge["metadata"].get("entry_labels", [])
        for edge in walkthrough_map["edges"]
    )


def test_top_level_routes_share_layout_depth_instead_of_visit_order_chain() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/analytics"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "sidebar",
                "status": "completed",
                "steps": [
                    {"index": 1, "action": "navigate", "status": "passed", "observation": "Home", "url": "https://example.test/analytics"},
                    {
                        "index": 2,
                        "action": "click",
                        "status": "passed",
                        "observation": 'Clicked a role=menuitem "Transactions"',
                        "url": "https://example.test/transactions",
                    },
                    {
                        "index": 3,
                        "action": "click",
                        "status": "passed",
                        "observation": 'Clicked a role=menuitem "Customers"',
                        "url": "https://example.test/customers",
                    },
                    {
                        "index": 4,
                        "action": "click",
                        "status": "passed",
                        "observation": 'Clicked a role=menuitem "Settings"',
                        "url": "https://example.test/settings/merchant",
                    },
                ],
            }
        ],
        "evidence": [],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-sidebar",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    nodes_by_route = {node["route"]: node for node in walkthrough_map["nodes"]}
    positions = walkthrough_map["layout"]["nodes"]

    entry_position = positions[nodes_by_route["/analytics"]["id"]]
    sibling_routes = ["/transactions", "/customers", "/settings/merchant"]
    sibling_positions = [positions[nodes_by_route[route]["id"]] for route in sibling_routes]

    assert walkthrough_map["layout"]["algorithm"] == "prototype_map"
    assert entry_position["depth"] == 0
    assert {position["depth"] for position in sibling_positions} == {1}
    assert {position["x"] for position in sibling_positions} == {sibling_positions[0]["x"]}
    assert sibling_positions[0]["x"] > entry_position["x"]
    assert len({position["y"] for position in sibling_positions}) == len(sibling_routes)


def test_detail_route_hangs_from_nearest_parent_route_even_when_visit_order_differs() -> None:
    payload = {
        "plan": {"products": [{"name": "Example", "kind": "owned", "url": "https://example.test/customers"}]},
        "results": [
            {
                "product": "Example",
                "product_kind": "owned",
                "scenario_id": "detail",
                "status": "completed",
                "steps": [
                    {"index": 1, "action": "navigate", "status": "passed", "observation": "Customer list", "url": "https://example.test/customers"},
                    {"index": 2, "action": "click", "status": "passed", "observation": "Back home", "url": "https://example.test/dashboard"},
                    {"index": 3, "action": "click", "status": "passed", "observation": "Open customer record", "url": "https://example.test/customers/123"},
                ],
            }
        ],
        "evidence": [],
    }

    walkthrough_map = build_walkthrough_map(
        run_id="run-detail",
        evidence_payload=payload,
        artifacts=[],
        browser_histories=[],
        generated_at="2026-06-24T00:00:00Z",
    )

    nodes_by_route = {node["route"]: node for node in walkthrough_map["nodes"]}
    customer_list = nodes_by_route["/customers"]
    customer_detail = nodes_by_route["/customers/:id"]
    list_position = walkthrough_map["layout"]["nodes"][customer_list["id"]]
    detail_position = walkthrough_map["layout"]["nodes"][customer_detail["id"]]
    structural_edges = [
        edge
        for edge in walkthrough_map["edges"]
        if edge["source"] == customer_list["id"] and edge["target"] == customer_detail["id"]
    ]

    assert customer_detail["metadata"]["structural_parent_node_id"] == customer_list["id"]
    assert detail_position["depth"] == list_position["depth"] + 1
    assert detail_position["x"] > list_position["x"]
    assert any(edge["kind"] == "inferred" and edge["metadata"].get("structural_relation") == "detail_parent" for edge in structural_edges)


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
    assert all(isinstance(position["depth"], int) for position in walkthrough_map["layout"]["nodes"].values())


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
    nodes_by_route = {node["route"]: node for node in walkthrough_map["nodes"]}
    positions = walkthrough_map["layout"]["nodes"]
    assert names_by_route["/data-insights/core-metrics"] == "Core Metrics"
    assert names_by_route["/transactions"] == "Transactions"
    assert names_by_route["/balances"] == "Balances"
    assert names_by_route["/settings/merchant"] == "Merchant Settings"
    dashboard_sidebar_routes = [
        "/analytics",
        "/data-insights/core-metrics",
        "/transactions",
        "/balances",
        "/customers",
        "/subscriptions",
        "/products",
        "/developers",
        "/settings/merchant",
    ]
    entry_position = positions[nodes_by_route["/analytics"]["id"]]
    sidebar_routes = [route for route in dashboard_sidebar_routes if route != "/analytics"]
    sidebar_positions = [positions[nodes_by_route[route]["id"]] for route in sidebar_routes]
    assert walkthrough_map["layout"]["algorithm"] == "prototype_map"
    assert entry_position["depth"] == 0
    assert {position["depth"] for position in sidebar_positions} == {1}
    assert {position["x"] for position in sidebar_positions} == {sidebar_positions[0]["x"]}
    assert sidebar_positions[0]["x"] > entry_position["x"]
    assert len({position["y"] for position in sidebar_positions}) == len(sidebar_routes)
    assert positions[nodes_by_route["/settings/merchant/:id"]["id"]]["x"] > positions[nodes_by_route["/settings/merchant"]["id"]]["x"]
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
