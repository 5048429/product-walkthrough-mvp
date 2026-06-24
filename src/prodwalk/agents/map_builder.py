from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..models import slugify, utc_now


SCHEMA_VERSION = "1.0"
WALKTHROUGH_MAP_ARTIFACT_ID = "art_walkthrough_map"

TRACKING_QUERY_KEYS = {
    "_ga",
    "_gl",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "igshid",
    "ref",
    "referrer",
}
STATE_QUERY_KEYS = {
    "cursor",
    "date",
    "filter",
    "from",
    "limit",
    "offset",
    "order",
    "page",
    "per_page",
    "q",
    "search",
    "sort",
    "tab",
    "to",
}
SENSITIVE_QUERY_MARKERS = (
    "auth",
    "bearer",
    "credential",
    "jwt",
    "key",
    "password",
    "secret",
    "session",
    "token",
)
SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"<secret>.*?</secret>", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk)_(?:live|test|prod|uat)?_?[A-Za-z0-9][A-Za-z0-9_\-]{12,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),
)
GENERIC_TITLES = {"", "clink", "initial actions", "new tab"}


@dataclass(slots=True)
class CanonicalUrl:
    raw_url: str
    canonical_url: str
    route: str
    normalized_route: str
    dynamic_route_pattern: str | None
    host: str
    scheme: str


@dataclass(slots=True)
class StepRecord:
    product: str
    product_kind: str
    scenario_id: str
    result_order: int
    index: int | None
    action: str | None
    status: str | None
    observation: str
    url: str
    title: str | None = None
    screenshot_refs: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    history_artifact_ids: list[str] = field(default_factory=list)
    page_evidence: dict[str, Any] = field(default_factory=dict)
    captured_at: str | None = None


def build_walkthrough_map(
    *,
    run_id: str,
    evidence_payload: dict[str, Any],
    artifacts: list[dict[str, Any]] | None = None,
    browser_histories: list[dict[str, Any]] | None = None,
    page_evidence_sources: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a safe page relationship map from run artifacts."""

    artifacts = [item for item in artifacts or [] if isinstance(item, dict)]
    browser_histories = [item for item in browser_histories or [] if isinstance(item, dict)]
    page_evidence_sources = [item for item in page_evidence_sources or [] if isinstance(item, dict)]
    if page_evidence_sources:
        artifacts = _merge_page_evidence_source_artifacts(artifacts, page_evidence_sources)
    evidence_payload = evidence_payload if isinstance(evidence_payload, dict) else {}

    warnings: list[dict[str, Any]] = []
    evidence_by_id = _evidence_by_id(evidence_payload.get("evidence"))
    screenshot_artifacts = _screenshot_artifact_lookup(artifacts)
    products = _products_from_payload(evidence_payload)
    product_hosts = {
        product["name"]: urlparse(str(product.get("start_url") or "")).netloc.lower()
        for product in products
        if product.get("start_url")
    }

    history_steps = _history_steps(browser_histories)
    if browser_histories and not history_steps:
        warnings.append(
            {
                "code": "BROWSER_HISTORY_EMPTY",
                "message": "Browser history artifacts were present but did not contain readable step states.",
            }
        )
    if not browser_histories:
        warnings.append(
            {
                "code": "MAP_NO_BROWSER_HISTORY",
                "message": "No browser history artifacts were available; the map was built from evidence steps only.",
            }
        )

    step_records = _step_records_from_evidence(evidence_payload, evidence_by_id, history_steps, artifacts)
    seen_step_keys = {
        (record.result_order, record.scenario_id, record.index)
        for record in step_records
        if record.index is not None
    }
    default_product = products[0] if products else {"name": "Product", "kind": "unknown", "start_url": ""}
    for record in history_steps:
        key = (0, "__browser_history__", record.index)
        if key in seen_step_keys:
            continue
        if any(existing.index == record.index and existing.url == record.url for existing in step_records):
            continue
        step_records.append(
            StepRecord(
                product=str(default_product["name"]),
                product_kind=str(default_product.get("kind") or "unknown"),
                scenario_id="__browser_history__",
                result_order=0,
                index=record.index,
                action=record.action,
                status="passed",
                observation=record.observation,
                url=record.url,
                title=record.title,
                screenshot_refs=list(record.screenshot_refs),
                history_artifact_ids=list(record.history_artifact_ids),
            )
        )

    if not step_records:
        warnings.append(
            {
                "code": "MAP_NO_WALKTHROUGH_STEPS",
                "message": "No walkthrough steps with URLs were found in evidence or browser history.",
            }
        )

    nodes_by_id: dict[str, dict[str, Any]] = {}
    step_nodes: list[tuple[StepRecord, str]] = []
    dynamic_normalized_count = 0
    missing_screenshot_refs = 0

    for record in sorted(step_records, key=_step_sort_key):
        canonical = canonicalize_url(record.url)
        if canonical is None:
            continue
        node_id = page_node_id(canonical.host, canonical.normalized_route)
        node = nodes_by_id.get(node_id)
        if node is None:
            node = _new_node(
                node_id=node_id,
                product=record.product,
                canonical=canonical,
                product_host=product_hosts.get(record.product),
            )
            nodes_by_id[node_id] = node
        _update_node_from_step(node, record, canonical)
        if canonical.dynamic_route_pattern:
            dynamic_normalized_count += 1
        missing_screenshot_refs += _attach_screenshots(
            node=node,
            refs=record.screenshot_refs,
            screenshot_artifacts=screenshot_artifacts,
            evidence_id=record.evidence_ids[0] if record.evidence_ids else None,
            step_index=record.index,
        )
        _apply_page_evidence(node, record, canonical)
        _attach_step_observation(node, record)
        step_nodes.append((record, node_id))

    _attach_finding_insights(nodes_by_id, evidence_payload.get("analyses"))
    for node in nodes_by_id.values():
        _finalize_node(node)
    _annotate_route_structure(nodes_by_id)

    edges = _with_structural_edges(_build_edges(step_nodes, nodes_by_id), nodes_by_id)
    if any(edge.get("kind") == "inferred" or edge.get("metadata", {}).get("inferred_reason") for edge in edges):
        warnings.append(
            {
                "code": "EDGE_INFERRED_FROM_ADJACENT_STEPS",
                "message": "Some edges are inferred from adjacent URL changes and may not represent exact click targets.",
            }
        )
    if dynamic_normalized_count:
        warnings.append(
            {
                "code": "URL_DYNAMIC_SEGMENTS_NORMALIZED",
                "message": "Some route segments that look like dynamic IDs were normalized before node grouping.",
                "details": {"occurrence_count": dynamic_normalized_count},
            }
        )
    if missing_screenshot_refs:
        warnings.append(
            {
                "code": "SCREENSHOT_ARTIFACT_MISSING",
                "message": "Some screenshot references could not be matched to registered screenshot artifacts.",
                "details": {"missing_count": missing_screenshot_refs},
            }
        )

    nodes = sorted(nodes_by_id.values(), key=lambda item: (item.get("first_seen_step") is None, item.get("first_seen_step") or 0, item["id"]))
    layout = _layout(nodes, edges)
    summary = _summary(nodes, edges)

    return {
        "run_id": run_id,
        "artifact_id": WALKTHROUGH_MAP_ARTIFACT_ID,
        "generated_at": generated_at or utc_now(),
        "schema_version": SCHEMA_VERSION,
        "source_artifact_ids": _source_artifact_ids(artifacts),
        "products": products,
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
        "layout": layout,
        "warnings": warnings,
    }


def canonicalize_url(url: str | None) -> CanonicalUrl | None:
    if not isinstance(url, str) or not url.strip():
        return None
    raw = url.strip()
    if _looks_like_local_path(raw):
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path, dynamic_path = _normalize_path(parsed.path or "/")
    query = _clean_query(parsed.query)
    fragment, dynamic_fragment = _normalize_fragment(parsed.fragment)
    dynamic_route = dynamic_path or dynamic_fragment

    canonical = urlunparse((scheme, host, path, "", query, fragment))
    route = path or "/"
    if fragment:
        route = f"{route}#{fragment}" if route != "/" else f"#{fragment}"
    normalized_route = route
    dynamic_route_pattern = normalized_route if dynamic_route else None
    safe_raw = urlunparse((scheme, host, parsed.path or "/", "", query, fragment))

    return CanonicalUrl(
        raw_url=safe_raw,
        canonical_url=canonical,
        route=route,
        normalized_route=normalized_route,
        dynamic_route_pattern=dynamic_route_pattern,
        host=host,
        scheme=scheme,
    )


def page_node_id(host: str, normalized_route: str) -> str:
    source = f"{host}|{normalized_route}"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    label = _identifier_slug(f"{host}_{normalized_route}")[:80].strip("_") or "page"
    return f"page_{label}_{digest}"


@dataclass(slots=True)
class _HistoryRecord:
    index: int
    action: str | None
    observation: str
    url: str
    title: str | None
    screenshot_refs: list[str]
    history_artifact_ids: list[str]


def _history_steps(browser_histories: list[dict[str, Any]]) -> list[_HistoryRecord]:
    records: list[_HistoryRecord] = []
    for source in browser_histories:
        payload = source.get("payload") if isinstance(source.get("payload"), dict) else source
        artifact_id = str(source.get("artifact_id") or source.get("id") or "")
        entries = payload.get("history") if isinstance(payload.get("history"), list) else []
        for ordinal, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                continue
            state = entry.get("state") if isinstance(entry.get("state"), dict) else {}
            url = str(state.get("url") or "").strip()
            if not url:
                continue
            title = _safe_text(state.get("title"), limit=160) or None
            records.append(
                _HistoryRecord(
                    index=ordinal,
                    action=", ".join(_action_names_from_history_entry(entry)) or None,
                    observation=_history_observation(entry),
                    url=url,
                    title=title,
                    screenshot_refs=_string_list([state.get("screenshot_path")]),
                    history_artifact_ids=[artifact_id] if artifact_id else [],
                )
            )
    return records


def _step_records_from_evidence(
    payload: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    history_steps: list[_HistoryRecord],
    artifacts: list[dict[str, Any]],
) -> list[StepRecord]:
    history_by_index = {record.index: record for record in history_steps}
    page_evidence_artifacts = _page_evidence_artifact_lookup(artifacts)
    records: list[StepRecord] = []
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    for result_order, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            continue
        product = str(result.get("product") or _first_product_name(payload) or "Product")
        product_kind = str(result.get("product_kind") or "unknown")
        scenario_id = str(result.get("scenario_id") or "scenario")
        steps = result.get("steps") if isinstance(result.get("steps"), list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            index = _int_or_none(step.get("index"))
            evidence_ids = [str(item) for item in step.get("evidence_ids") or [] if str(item)]
            evidence_items = [evidence_by_id[item] for item in evidence_ids if item in evidence_by_id]
            first_evidence = evidence_items[0] if evidence_items else {}
            data = first_evidence.get("data") if isinstance(first_evidence.get("data"), dict) else {}
            history = history_by_index.get(index or -1)
            url = str(step.get("url") or first_evidence.get("url") or data.get("url") or (history.url if history else "")).strip()
            if not url:
                continue
            title = (
                _safe_text(data.get("title"), limit=160)
                or _safe_text(first_evidence.get("title"), limit=160)
                or (history.title if history else None)
            )
            screenshot_refs = _step_screenshot_refs(step, evidence_items)
            if history:
                screenshot_refs.extend(history.screenshot_refs)
            page_evidence = _page_evidence_summary(evidence_items, page_evidence_artifacts)
            records.append(
                StepRecord(
                    product=product,
                    product_kind=product_kind,
                    scenario_id=scenario_id,
                    result_order=result_order,
                    index=index,
                    action=_safe_text(step.get("action") or data.get("action"), limit=240) or (history.action if history else None),
                    status=_safe_text(step.get("status"), limit=80),
                    observation=_safe_text(
                        step.get("observation") or first_evidence.get("summary") or data.get("summary") or (history.observation if history else ""),
                        limit=1200,
                    ),
                    url=url,
                    title=title,
                    screenshot_refs=screenshot_refs,
                    evidence_ids=evidence_ids,
                    history_artifact_ids=list(history.history_artifact_ids) if history else [],
                    page_evidence=page_evidence,
                )
            )
    return records


def _new_node(
    *,
    node_id: str,
    product: str,
    canonical: CanonicalUrl,
    product_host: str | None,
) -> dict[str, Any]:
    is_external = bool(product_host and canonical.host and canonical.host != product_host)
    status = "external" if is_external else "visited"
    return {
        "id": node_id,
        "product": product,
        "scenario_ids": [],
        "name": _name_from_route(canonical.normalized_route, canonical.host),
        "title": None,
        "url": canonical.raw_url,
        "route": canonical.route,
        "canonical_url": canonical.canonical_url,
        "page_type": "external" if is_external else _page_type(canonical.normalized_route, None, None),
        "status": status,
        "purpose": "",
        "key_functions": [],
        "key_controls": [],
        "issues": [],
        "observations": [],
        "page_evidence": [],
        "screenshot_evidence": [],
        "primary_screenshot_artifact_id": None,
        "evidence_ids": [],
        "event_ids": [],
        "first_seen_step": None,
        "last_seen_step": None,
        "visit_count": 0,
        "confidence": 0.65,
        "metadata": {
            "normalized_route": canonical.normalized_route,
            "dynamic_route_pattern": canonical.dynamic_route_pattern,
            "source_history_artifact_ids": [],
            "raw_titles": [],
            "raw_urls": [],
        },
    }


def _update_node_from_step(node: dict[str, Any], record: StepRecord, canonical: CanonicalUrl) -> None:
    node["visit_count"] = int(node.get("visit_count") or 0) + 1
    _append_unique(node["scenario_ids"], record.scenario_id)
    for evidence_id in record.evidence_ids:
        _append_unique(node["evidence_ids"], evidence_id)
    for event_id in record.event_ids:
        _append_unique(node["event_ids"], event_id)
    for artifact_id in record.history_artifact_ids:
        _append_unique(node["metadata"]["source_history_artifact_ids"], artifact_id)
    _append_unique(node["metadata"]["raw_urls"], canonical.raw_url)

    if record.index is not None:
        current_first = node.get("first_seen_step")
        current_last = node.get("last_seen_step")
        node["first_seen_step"] = record.index if current_first is None else min(int(current_first), record.index)
        node["last_seen_step"] = record.index if current_last is None else max(int(current_last), record.index)

    clean_title = _clean_title(record.title, canonical.host)
    if clean_title:
        _append_unique(node["metadata"]["raw_titles"], clean_title)
        if node.get("title") is None:
            node["title"] = clean_title
            if _is_better_name(clean_title, node.get("name"), canonical.normalized_route):
                node["name"] = clean_title

    status = str(record.status or "").lower()
    is_discovery_step = "discover_page" in str(record.action or "").lower()
    text = f"{record.observation} {record.title or ''} {canonical.normalized_route}".lower()
    if "404" in text or "not found" in text or "error" in text:
        node["status"] = "error"
        node["page_type"] = "error"
    elif status in {"blocked", "failed", "friction"} and node.get("status") not in {"error", "external"}:
        node["status"] = "blocked"
    elif is_discovery_step and node.get("status") not in {"error", "external", "blocked"} and int(node.get("visit_count") or 0) == 1:
        node["status"] = "discovered"
    elif not is_discovery_step and node.get("status") == "discovered":
        node["status"] = "visited"
    if node.get("page_type") not in {"error", "external"}:
        node["page_type"] = _page_type(canonical.normalized_route, clean_title, record.observation)

    controls = _extract_controls(f"{record.action or ''} {record.observation}")
    for control in controls:
        _append_unique(node["key_controls"], control, limit=12)


def _attach_screenshots(
    *,
    node: dict[str, Any],
    refs: list[str],
    screenshot_artifacts: dict[str, dict[str, Any]],
    evidence_id: str | None,
    step_index: int | None,
) -> int:
    missing = 0
    seen = {item.get("artifact_id") or item.get("path") for item in node["screenshot_evidence"]}
    for ref in refs:
        artifact = _artifact_for_ref(ref, screenshot_artifacts)
        if artifact is None:
            if ref:
                missing += 1
            continue
        path = _safe_run_relative_path(artifact.get("path"), allowed_prefix="screenshots")
        if not path:
            missing += 1
            continue
        key = artifact.get("id") or path
        if key in seen:
            continue
        seen.add(key)
        metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
        node["screenshot_evidence"].append(
            {
                "id": _screenshot_id(artifact, step_index),
                "artifact_id": artifact.get("id"),
                "title": _safe_text(artifact.get("title"), limit=160) or PurePosixPath(path).name,
                "path": path,
                "content_url": _safe_api_url(metadata.get("content_url")),
                "screenshot_url": _safe_api_url(metadata.get("screenshot_url")),
                "evidence_id": evidence_id,
                "step_index": step_index,
                "captured_at": artifact.get("created_at"),
                "is_primary": False,
            }
        )
    return missing


def _attach_step_observation(node: dict[str, Any], record: StepRecord) -> None:
    summary = _safe_text(record.observation, limit=600)
    if not summary or not _meaningful_observation(summary):
        return
    existing = {item["summary"] for item in node["observations"]}
    if summary in existing or len(node["observations"]) >= 5:
        return
    node["observations"].append(
        {
            "id": f"ins_{node['id']}_{len(node['observations']) + 1}",
            "kind": "observation",
            "title": f"Step {record.index} observation" if record.index is not None else "Browser observation",
            "summary": summary,
            "severity": "info",
            "confidence": 0.72,
            "evidence_ids": list(record.evidence_ids),
            "source": "browser_step",
        }
    )


def _apply_page_evidence(node: dict[str, Any], record: StepRecord, canonical: CanonicalUrl) -> None:
    evidence = record.page_evidence
    if not evidence:
        return

    metadata = node.setdefault("metadata", {})
    page_meta = metadata.setdefault("page_evidence", {})
    for artifact_id in evidence.get("artifact_ids") or []:
        _append_unique(metadata.setdefault("source_page_evidence_artifact_ids", []), artifact_id, limit=24)
        _append_unique(metadata.setdefault("page_evidence_artifact_ids", []), artifact_id, limit=24)
        _append_unique(page_meta.setdefault("artifact_ids", []), artifact_id, limit=24)
    page_meta["capture_count"] = int(page_meta.get("capture_count") or 0) + 1
    metadata["page_evidence_capture_count"] = int(metadata.get("page_evidence_capture_count") or 0) + 1

    title = _clean_title(evidence.get("title"), canonical.host)
    page_name = _safe_text(evidence.get("page_name"), limit=120)
    preferred_name = page_name or title
    if title:
        _append_unique(metadata.setdefault("raw_titles", []), title)
        if node.get("title") is None:
            node["title"] = title
    route_name = _name_from_route(canonical.normalized_route, canonical.host)
    if page_name and str(node.get("name") or "").lower() == route_name.lower():
        node["name"] = page_name
    elif preferred_name and _is_better_name(preferred_name, node.get("name"), canonical.normalized_route):
        node["name"] = preferred_name

    page_type = _safe_page_type(evidence.get("page_type"))
    if page_type and node.get("page_type") not in {"error", "external"}:
        node["page_type"] = page_type
    elif node.get("page_type") == "unknown":
        inferred = _page_type(canonical.normalized_route, title, evidence.get("text_excerpt"))
        if inferred != "unknown":
            node["page_type"] = inferred

    purpose = _safe_text(evidence.get("purpose"), limit=260)
    if purpose:
        page_meta["purpose"] = purpose
    for control in evidence.get("key_controls") or []:
        _append_unique(node["key_controls"], control, limit=12)
        _append_unique(page_meta.setdefault("controls", []), control, limit=12)

    for key in ("status", "captured_at"):
        value = _safe_text(evidence.get(key), limit=80)
        if value:
            page_meta[key] = value
    for key in ("network_event_count", "console_message_count", "page_error_count", "element_count"):
        if evidence.get(key) is not None:
            page_meta[key] = _int_or_none(evidence.get(key)) or 0
    if evidence.get("text_excerpt"):
        page_meta["text_excerpt"] = evidence["text_excerpt"]
    if evidence.get("dom_summary"):
        page_meta["dom_summary"] = evidence["dom_summary"]
    if evidence.get("artifacts"):
        page_meta["artifacts"] = evidence["artifacts"]
    if evidence.get("screenshot_paths"):
        page_meta["screenshot_paths"] = evidence["screenshot_paths"]

    _append_page_evidence_capture(node, record, evidence)

    summary_parts = []
    if evidence.get("text_excerpt"):
        summary_parts.append(f"Visible text: {evidence['text_excerpt']}")
    if evidence.get("key_controls"):
        summary_parts.append("Key controls: " + ", ".join(evidence["key_controls"][:6]))
    if not summary_parts:
        return

    summary = _safe_text(" ".join(summary_parts), limit=600)
    existing = {item["summary"] for item in node["observations"]}
    if summary in existing or len(node["observations"]) >= 5:
        return
    node["observations"].append(
        {
            "id": f"ins_{node['id']}_{len(node['observations']) + 1}",
            "kind": "observation",
            "title": f"Step {record.index} page evidence" if record.index is not None else "Page evidence",
            "summary": summary,
            "severity": "info",
            "confidence": 0.78,
            "evidence_ids": list(record.evidence_ids),
            "source": "page_evidence",
        }
    )


def _append_page_evidence_capture(node: dict[str, Any], record: StepRecord, evidence: dict[str, Any]) -> None:
    captures = node.setdefault("page_evidence", [])
    artifact_ids = _unique_list(_string_list(evidence.get("artifact_ids")))
    screenshot_paths = _unique_list(_string_list(evidence.get("screenshot_paths")))
    screenshot_artifact_ids = _page_evidence_screenshot_artifact_ids(node, record.evidence_ids, screenshot_paths)
    capture_key = record.evidence_ids[0] if record.evidence_ids else "|".join(artifact_ids + screenshot_paths)
    capture_id = f"pev_{slugify(capture_key or str(node.get('id') or 'page-evidence'))[:72]}"
    if capture_id == "pev_":
        capture_id = f"pev_{len(captures) + 1}"

    item = {
        "id": capture_id,
        "status": _safe_text(evidence.get("status"), limit=80) or "completed",
        "title": _safe_text(evidence.get("title") or evidence.get("page_name"), limit=160) or None,
        "url": _safe_text(evidence.get("url"), limit=260) or node.get("canonical_url"),
        "summary": _safe_text(evidence.get("purpose") or evidence.get("text_excerpt"), limit=420) or None,
        "captured_at": _safe_text(evidence.get("captured_at"), limit=80) or None,
        "controls": _unique_list(_string_list(evidence.get("key_controls")))[:12],
        "text_observations": [_safe_text(evidence.get("text_excerpt"), limit=420)] if evidence.get("text_excerpt") else [],
        "dom_observations": [_safe_text(evidence.get("dom_summary"), limit=260)] if evidence.get("dom_summary") else [],
        "screenshot_artifact_ids": screenshot_artifact_ids,
        "screenshot_paths": screenshot_paths,
        "artifact_ids": artifact_ids,
        "artifacts": _safe_page_evidence_artifact_refs(evidence.get("artifacts")),
        "network_event_count": _int_or_none(evidence.get("network_event_count")) or 0,
        "console_message_count": _int_or_none(evidence.get("console_message_count")) or 0,
        "page_error_count": _int_or_none(evidence.get("page_error_count")) or 0,
        "errors": _unique_list([_safe_text(error, limit=180) for error in evidence.get("errors") or [] if _safe_text(error, limit=180)])[:5],
    }

    existing = next((capture for capture in captures if capture.get("id") == capture_id), None)
    if existing is None:
        captures.append(item)
    else:
        _merge_page_evidence_capture(existing, item)

    if item["errors"]:
        _append_page_insight(
            node,
            kind="issue",
            title="Page evidence capture issue",
            summary="; ".join(item["errors"][:2]),
            evidence_ids=record.evidence_ids,
            source="page_evidence",
            severity="low",
            confidence=0.52,
        )


def _page_evidence_screenshot_artifact_ids(
    node: dict[str, Any],
    evidence_ids: list[str],
    screenshot_paths: list[str],
) -> list[str]:
    target_evidence_ids = set(evidence_ids)
    target_paths = set(screenshot_paths)
    artifact_ids: list[str] = []
    for screenshot in node.get("screenshot_evidence") or []:
        if not isinstance(screenshot, dict):
            continue
        matches_evidence = bool(target_evidence_ids and screenshot.get("evidence_id") in target_evidence_ids)
        matches_path = bool(target_paths and screenshot.get("path") in target_paths)
        if not matches_evidence and not matches_path:
            continue
        artifact_id = _safe_text(screenshot.get("artifact_id"), limit=120)
        if artifact_id:
            _append_unique(artifact_ids, artifact_id, limit=8)
    return artifact_ids


def _merge_page_evidence_capture(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("title", "url", "summary", "captured_at"):
        if not target.get(key) and source.get(key):
            target[key] = source[key]
    for key in ("network_event_count", "console_message_count", "page_error_count"):
        target[key] = max(int(target.get(key) or 0), int(source.get(key) or 0))
    for key in ("controls", "text_observations", "dom_observations", "screenshot_artifact_ids", "screenshot_paths", "artifact_ids", "errors"):
        for value in source.get(key) or []:
            _append_unique(target.setdefault(key, []), value, limit=24)
    for artifact in source.get("artifacts") or []:
        existing_keys = {item.get("artifact_id") or item.get("path") for item in target.setdefault("artifacts", []) if isinstance(item, dict)}
        artifact_key = artifact.get("artifact_id") or artifact.get("path")
        if artifact_key not in existing_keys:
            target["artifacts"].append(artifact)


def _append_page_insight(
    node: dict[str, Any],
    *,
    kind: str,
    title: str,
    summary: str,
    evidence_ids: list[str],
    source: str,
    confidence: float,
    severity: str = "info",
) -> None:
    target = node["issues"] if kind == "issue" else node["observations"]
    if any(item.get("summary") == summary and item.get("title") == title for item in target):
        return
    if len(target) >= 7:
        return
    target.append(
        {
            "id": f"ins_{node['id']}_{source}_{len(target) + 1}",
            "kind": kind,
            "title": title,
            "summary": summary,
            "severity": severity,
            "confidence": confidence,
            "evidence_ids": _unique_list(evidence_ids),
            "source": source,
        }
    )


def _attach_finding_insights(nodes_by_id: dict[str, dict[str, Any]], raw_analyses: Any) -> None:
    analyses = raw_analyses if isinstance(raw_analyses, list) else []
    for analysis in analyses:
        if not isinstance(analysis, dict):
            continue
        findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            evidence_ids = [str(item) for item in finding.get("evidence_ids") or [] if str(item)]
            summary = _safe_text(finding.get("claim"), limit=600)
            if not summary:
                continue
            for node in nodes_by_id.values():
                if not _finding_matches_node(finding, evidence_ids, node):
                    continue
                if len(node["issues"]) >= 5:
                    continue
                node["issues"].append(
                    {
                        "id": str(finding.get("id") or f"ins_{node['id']}_issue_{len(node['issues']) + 1}"),
                        "kind": "issue",
                        "title": _safe_text(finding.get("theme"), limit=160) or "Product finding",
                        "summary": summary,
                        "severity": _severity(finding.get("severity")),
                        "confidence": _float_between(finding.get("confidence"), default=0.72),
                        "evidence_ids": evidence_ids,
                        "source": "report",
                    }
                )


def _finalize_node(node: dict[str, Any]) -> None:
    screenshots = node["screenshot_evidence"]
    screenshots.sort(key=lambda item: (item.get("step_index") is None, item.get("step_index") or -1, item.get("path") or ""))
    if screenshots:
        for item in screenshots:
            item["is_primary"] = False
        screenshots[-1]["is_primary"] = True
        node["primary_screenshot_artifact_id"] = screenshots[-1].get("artifact_id")
    if not node["key_controls"]:
        route_control = _name_from_route(str(node.get("route") or ""), "")
        if route_control and route_control != "Home":
            node["key_controls"].append(route_control)
    node["key_functions"] = _key_functions(node)
    node["purpose"] = _purpose(node)
    confidence = 0.58
    if node.get("title"):
        confidence += 0.08
    if node["evidence_ids"]:
        confidence += 0.1
    if screenshots:
        confidence += 0.08
    if node.get("page_type") != "unknown":
        confidence += 0.06
    node["confidence"] = round(min(confidence, 0.92), 2)
    node["scenario_ids"] = [item for item in node["scenario_ids"] if item != "__browser_history__"]


def _annotate_route_structure(nodes_by_id: dict[str, dict[str, Any]]) -> None:
    nodes_by_route: dict[str, dict[str, Any]] = {}
    for node in nodes_by_id.values():
        route = str(node.get("metadata", {}).get("normalized_route") or node.get("route") or "")
        if route:
            nodes_by_route[route] = node

    for node in nodes_by_id.values():
        metadata = node.setdefault("metadata", {})
        route = str(metadata.get("normalized_route") or node.get("route") or "")
        segments = _route_segments(route)
        section = segments[0] if segments else "home"
        parent = _route_parent_node(route, nodes_by_route)
        parent_id = parent.get("id") if parent else None

        metadata["route_segments"] = segments
        metadata["route_section"] = section
        metadata["route_depth"] = len(segments)
        metadata["structural_parent_node_id"] = parent_id
        metadata["structural_parent_route"] = parent.get("route") if parent else None
        metadata["layout_group"] = _layout_group_for_node(node, section)
        metadata["layout_role"] = _layout_role_for_node(node, parent_id)

    for product, product_nodes in _nodes_by_product(nodes_by_id.values()).items():
        entry = _entry_node_for_product(product_nodes)
        if entry is None:
            continue
        entry_metadata = entry.setdefault("metadata", {})
        entry_metadata["layout_role"] = "entry"
        entry_metadata["layout_group"] = "entry"
        for node in product_nodes:
            metadata = node.setdefault("metadata", {})
            metadata["entry_node_id"] = entry["id"]
            if node is not entry and metadata.get("layout_role") == "primary":
                metadata["structural_parent_node_id"] = entry["id"]
                metadata["structural_parent_route"] = entry.get("route")
                metadata["layout_role"] = "main_section"


def _build_edges(step_nodes: list[tuple[StepRecord, str]], nodes_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str, str], list[tuple[StepRecord, str]]] = {}
    for record, node_id in step_nodes:
        grouped.setdefault((record.result_order, record.product, record.scenario_id), []).append((record, node_id))

    edges_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for records in grouped.values():
        records.sort(key=lambda item: _step_sort_key(item[0]))
        previous_record: StepRecord | None = None
        previous_node_id: str | None = None
        for record, node_id in records:
            if previous_node_id and previous_node_id != node_id:
                edge = _edge_from_transition(previous_record, record, previous_node_id, node_id, nodes_by_id)
                key = (edge["source"], edge["target"])
                existing = edges_by_key.get(key)
                if existing is None:
                    edges_by_key[key] = edge
                else:
                    existing["metadata"]["occurrence_count"] = int(existing["metadata"].get("occurrence_count") or 1) + 1
                    for evidence_id in edge["evidence_ids"]:
                        _append_unique(existing["evidence_ids"], evidence_id)
                    for event_id in edge["event_ids"]:
                        _append_unique(existing["event_ids"], event_id)
                    existing["confidence"] = round(max(float(existing["confidence"]), float(edge["confidence"])), 2)
            previous_record = record
            previous_node_id = node_id
    return sorted(edges_by_key.values(), key=lambda item: (item.get("from_step_index") is None, item.get("from_step_index") or 0, item["id"]))


def _with_structural_edges(edges: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    edges_by_pair = {(str(edge.get("source")), str(edge.get("target"))): edge for edge in edges}
    for node in nodes_by_id.values():
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        parent_id = str(metadata.get("structural_parent_node_id") or "")
        if not parent_id or parent_id == node.get("id") or parent_id not in nodes_by_id:
            continue
        source = nodes_by_id[parent_id]
        relation = _structural_relation_for_node(node, source)
        pair = (parent_id, str(node["id"]))
        existing = edges_by_pair.get(pair)
        if existing is not None:
            existing.setdefault("metadata", {})["structural_relation"] = relation
            existing["metadata"]["inferred_reason"] = (
                f"{existing['metadata'].get('inferred_reason', '').rstrip()} "
                f"Route hierarchy also groups this node under {source.get('name') or 'its parent'}."
            ).strip()
            existing["metadata"]["map_relation"] = relation
            existing["confidence"] = round(max(float(existing.get("confidence") or 0), 0.68), 2)
            continue
        edge = _structural_edge(source, node, relation)
        edges_by_pair[pair] = edge
        edges.append(edge)
    return sorted(
        edges,
        key=lambda item: (
            item.get("from_step_index") is None,
            item.get("from_step_index") if item.get("from_step_index") is not None else 10**9,
            item.get("metadata", {}).get("structural_relation") is not None,
            item["id"],
        ),
    )


def _structural_edge(source: dict[str, Any], target: dict[str, Any], relation: str) -> dict[str, Any]:
    source_id = str(source["id"])
    target_id = str(target["id"])
    if relation == "app_navigation":
        label = "Open from navigation"
        confidence = 0.62
        reason = "This page is a peer product surface reached from the shared navigation shell."
    elif relation == "detail_parent":
        label = str(target.get("name") or "Detail page")
        confidence = 0.64
        reason = "Route hierarchy groups this detail page under its nearest visited parent route."
    else:
        label = str(target.get("name") or "Child page")
        confidence = 0.58
        reason = "Route hierarchy groups this page under its nearest visited parent route."
    return {
        "id": f"edge_struct_{source_id}__{target_id}"[:180],
        "source": source_id,
        "target": target_id,
        "label": label,
        "kind": "inferred",
        "action": None,
        "from_step_index": None,
        "to_step_index": target.get("first_seen_step"),
        "evidence_ids": list(target.get("evidence_ids") or []),
        "event_ids": list(target.get("event_ids") or []),
        "confidence": confidence,
        "metadata": {
            "source_url": source.get("canonical_url"),
            "target_url": target.get("canonical_url"),
            "inferred_reason": reason,
            "occurrence_count": 0,
            "structural_relation": relation,
            "map_relation": relation,
        },
    }


def _edge_from_transition(
    previous: StepRecord | None,
    current: StepRecord,
    source_id: str,
    target_id: str,
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source = nodes_by_id[source_id]
    target = nodes_by_id[target_id]
    trigger_text = " ".join(
        part
        for part in [
            previous.action if previous else "",
            previous.observation if previous else "",
            current.action,
            current.observation,
        ]
        if part
    )
    action = current.action or (previous.action if previous else None)
    kind, confidence = _edge_kind_and_confidence(action, trigger_text)
    relation = _transition_relation(source, target, kind)
    inferred_reason = "Adjacent walkthrough steps changed URL"
    if action:
        inferred_reason += f" after action: {action}"
    inferred_reason += "."
    evidence_ids: list[str] = []
    if previous:
        evidence_ids.extend(previous.evidence_ids)
    evidence_ids.extend(current.evidence_ids)
    event_ids: list[str] = []
    if previous:
        event_ids.extend(previous.event_ids)
    event_ids.extend(current.event_ids)
    edge_id = f"edge_{source_id}__{target_id}"
    return {
        "id": edge_id[:180],
        "source": source_id,
        "target": target_id,
        "label": _edge_label(trigger_text, target),
        "kind": kind,
        "action": action,
        "from_step_index": previous.index if previous else None,
        "to_step_index": current.index,
        "evidence_ids": _unique_list(evidence_ids),
        "event_ids": _unique_list(event_ids),
        "confidence": confidence,
        "metadata": {
            "source_url": source.get("canonical_url"),
            "target_url": target.get("canonical_url"),
            "inferred_reason": inferred_reason,
            "occurrence_count": 1,
            "map_relation": relation,
        },
    }


def _edge_kind_and_confidence(action: str | None, text: str) -> tuple[str, float]:
    action_l = str(action or "").lower()
    text_l = text.lower()
    if "navigate" in action_l:
        return "navigation", 0.86
    if "submit" in action_l:
        return "form_submit", 0.74
    if "clicked" in text_l or "click" in action_l:
        if "role=menuitem" in text_l or "menuitem" in text_l:
            return "menu", 0.74
        if "role=button" in text_l or "button" in text_l:
            return "button", 0.7
        if "role=link" in text_l or " link" in text_l or "<a" in text_l:
            return "link", 0.7
        return "button", 0.66
    if "redirect" in text_l:
        return "redirect", 0.68
    return "inferred", 0.55


def _edge_label(text: str, target: dict[str, Any]) -> str:
    label = _extract_first_click_label(text)
    target_name = str(target.get("name") or "")
    if label and _roughly_matches(label, target_name):
        return label
    return target_name or "Open page"


def _summary(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    screenshot_count = sum(len(node.get("screenshot_evidence") or []) for node in nodes)
    node_conf = [float(node.get("confidence") or 0) for node in nodes]
    edge_conf = [float(edge.get("confidence") or 0) for edge in edges]
    confidence_values = node_conf + edge_conf
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "visited_count": sum(1 for node in nodes if node.get("status") == "visited"),
        "blocked_count": sum(1 for node in nodes if node.get("status") == "blocked"),
        "discovered_count": sum(1 for node in nodes if node.get("status") == "discovered"),
        "external_count": sum(1 for node in nodes if node.get("status") == "external"),
        "screenshot_count": screenshot_count,
        "confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0,
    }


def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    nodes_by_id = {str(node["id"]): node for node in nodes}
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        parent_id = str(node.get("metadata", {}).get("structural_parent_node_id") or "")
        if parent_id and parent_id in nodes_by_id and parent_id != node["id"]:
            children_by_parent.setdefault(parent_id, []).append(node)

    positions: dict[str, dict[str, int]] = {}
    x_gap = 430
    y_gap = 246
    child_y_gap = 220
    product_gap = 1500
    product_groups = _nodes_by_product(nodes)
    if not product_groups:
        product_groups = {"Product": nodes}

    for product_index, product_nodes in enumerate(product_groups.values()):
        product_y = product_index * product_gap
        entry_nodes = _sorted_layout_nodes([node for node in product_nodes if node.get("metadata", {}).get("layout_role") == "entry"])
        if not entry_nodes:
            fallback_entry = _entry_node_for_product(product_nodes)
            entry_nodes = [fallback_entry] if fallback_entry is not None else []
        main_nodes = _sorted_layout_nodes([node for node in product_nodes if node.get("metadata", {}).get("layout_role") == "main_section"])

        for row, node in enumerate(entry_nodes):
            positions[str(node["id"])] = {"x": 0, "y": product_y + row * y_gap, "depth": 0}

        if not entry_nodes and main_nodes:
            first = main_nodes.pop(0)
            positions[str(first["id"])] = {"x": 0, "y": product_y, "depth": 0}

        main_midpoint = (len(main_nodes) - 1) / 2
        for row, node in enumerate(main_nodes):
            positions[str(node["id"])] = {
                "x": x_gap,
                "y": product_y + int(round((row - main_midpoint) * y_gap)),
                "depth": 1,
            }

        for node in [*entry_nodes, *main_nodes]:
            _place_route_children(node, children_by_parent, positions, x_gap=x_gap, child_y_gap=child_y_gap, seen=set())

    unplaced_regular = [
        node
        for node in nodes
        if str(node["id"]) not in positions and node.get("metadata", {}).get("layout_role") in {"detail", "subroute", "primary"}
    ]
    regular_start_y = max((item["y"] for item in positions.values()), default=0) + y_gap
    for row, node in enumerate(_sorted_layout_nodes(unplaced_regular)):
        positions[str(node["id"])] = {"x": x_gap, "y": regular_start_y + row * y_gap, "depth": 1}

    max_depth = max((item["depth"] for item in positions.values()), default=0)
    partition_x = (max_depth + 2) * x_gap
    partition_nodes = [
        node
        for node in nodes
        if str(node["id"]) not in positions and node.get("metadata", {}).get("layout_role") in {"auth", "error", "external"}
    ]
    for row, node in enumerate(_sorted_layout_nodes(partition_nodes)):
        positions[str(node["id"])] = {"x": partition_x, "y": row * y_gap, "depth": max_depth + 2}

    remaining = [node for node in nodes if str(node["id"]) not in positions]
    remaining_start_y = max((item["y"] for item in positions.values()), default=0) + y_gap
    for row, node in enumerate(_sorted_layout_nodes(remaining)):
        positions[str(node["id"])] = {"x": 0, "y": remaining_start_y + row * y_gap, "depth": 0}
    return {"algorithm": "prototype_map", "nodes": positions}


def _place_route_children(
    node: dict[str, Any],
    children_by_parent: dict[str, list[dict[str, Any]]],
    positions: dict[str, dict[str, int]],
    *,
    x_gap: int,
    child_y_gap: int,
    seen: set[str],
) -> None:
    node_id = str(node["id"])
    if node_id in seen or node_id not in positions:
        return
    seen.add(node_id)
    children = _sorted_layout_nodes(children_by_parent.get(node_id, []))
    if not children:
        return
    parent_position = positions[node_id]
    midpoint = (len(children) - 1) / 2
    for index, child in enumerate(children):
        child_id = str(child["id"])
        if child_id in positions:
            continue
        y_offset = int(round((index - midpoint) * child_y_gap))
        depth = int(parent_position["depth"]) + 1
        positions[child_id] = {
            "x": depth * x_gap,
            "y": int(parent_position["y"]) + y_offset,
            "depth": depth,
        }
        _place_route_children(child, children_by_parent, positions, x_gap=x_gap, child_y_gap=child_y_gap, seen=seen)


def _sorted_layout_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        nodes,
        key=lambda node: (
            node.get("first_seen_step") is None,
            node.get("first_seen_step") if node.get("first_seen_step") is not None else 10**9,
            str(node.get("metadata", {}).get("route_section") or ""),
            str(node.get("route") or ""),
            str(node.get("id") or ""),
        ),
    )


def _nodes_by_product(nodes: Any) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        groups.setdefault(str(node.get("product") or "Product"), []).append(node)
    return groups


def _entry_node_for_product(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [node for node in nodes if str(node.get("status") or "") not in {"external", "error"}]
    if not candidates:
        candidates = list(nodes)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda node: (
            node.get("first_seen_step") is None,
            node.get("first_seen_step") if node.get("first_seen_step") is not None else 10**9,
            0 if node.get("page_type") == "dashboard" else 1,
            str(node.get("route") or ""),
        ),
    )[0]


def _structural_relation_for_node(node: dict[str, Any], source: dict[str, Any]) -> str:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    source_metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    if node.get("page_type") == "detail":
        return "detail_parent"
    if metadata.get("entry_node_id") == source.get("id") and source_metadata.get("layout_role") == "entry":
        return "app_navigation"
    return "route_parent"


def _transition_relation(source: dict[str, Any], target: dict[str, Any], kind: str) -> str:
    source_metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    target_metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
    if target.get("status") == "external" or target.get("page_type") == "external":
        return "external"
    if target.get("status") in {"blocked", "error"} or target.get("page_type") in {"auth", "error"}:
        return "blocked"
    if target_metadata.get("structural_parent_node_id") == source.get("id"):
        return _structural_relation_for_node(target, source)
    if source_metadata.get("layout_role") == "entry" and target_metadata.get("entry_node_id") == source.get("id"):
        return "app_navigation"
    return "walkthrough_path"


def _route_parent_node(route: str, nodes_by_route: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for candidate in _parent_route_candidates(route):
        parent = nodes_by_route.get(candidate)
        if parent is not None:
            return parent
    return None


def _parent_route_candidates(route: str) -> list[str]:
    segments = _route_segments(route)
    if len(segments) < 2:
        return []
    candidates: list[str] = []
    for length in range(len(segments) - 1, 0, -1):
        candidates.append(_route_from_segments(route, segments[:length]))
    return candidates


def _route_segments(route: str) -> list[str]:
    body = _route_body(route)
    if not body or body == "/":
        return []
    return [segment for segment in body.split("/") if segment]


def _route_body(route: str) -> str:
    body = str(route or "").split("?", 1)[0]
    if "#" in body:
        body = body.split("#", 1)[1]
    if body.startswith("!"):
        body = body[1:]
    return body if body.startswith("/") else f"/{body}" if body else "/"


def _route_from_segments(original_route: str, segments: list[str]) -> str:
    prefix = ""
    if str(original_route).startswith("#!/"):
        prefix = "#!"
    elif str(original_route).startswith("#/"):
        prefix = "#"
    return f"{prefix}/{'/'.join(segments)}" if segments else f"{prefix}/"


def _layout_group_for_node(node: dict[str, Any], section: str) -> str:
    status = str(node.get("status") or "")
    page_type = str(node.get("page_type") or "")
    if status == "external" or page_type == "external":
        return "external"
    if status == "error" or page_type == "error":
        return "error"
    if page_type == "auth":
        return "auth"
    if section == "settings":
        return "settings"
    return "primary"


def _layout_role_for_node(node: dict[str, Any], parent_id: str | None) -> str:
    status = str(node.get("status") or "")
    page_type = str(node.get("page_type") or "")
    if status == "external" or page_type == "external":
        return "external"
    if status == "error" or page_type == "error":
        return "error"
    if page_type == "auth" and not parent_id:
        return "auth"
    if parent_id:
        return "detail" if page_type == "detail" else "subroute"
    return "primary"


def _products_from_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    products: list[dict[str, str]] = []
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
    for item in plan.get("products") or []:
        if not isinstance(item, dict):
            continue
        products.append(
            {
                "name": str(item.get("name") or "Product"),
                "kind": str(item.get("kind") or "unknown"),
                "start_url": str(item.get("url") or ""),
            }
        )
    if products:
        return products
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        name = str(result.get("product") or "Product")
        if name in seen:
            continue
        seen.add(name)
        first_url = ""
        for step in result.get("steps") or []:
            if isinstance(step, dict) and step.get("url"):
                first_url = str(step["url"])
                break
        products.append({"name": name, "kind": str(result.get("product_kind") or "unknown"), "start_url": first_url})
    return products


def _source_artifact_ids(artifacts: list[dict[str, Any]]) -> list[str]:
    source_types = {
        "evidence_json",
        "report_markdown",
        "evaluation_json",
        "browser_history",
        "page_evidence_manifest",
        "page_html",
        "page_text",
        "page_elements",
        "dom_snapshot",
        "accessibility_tree",
        "network_log",
        "console_log",
    }
    ids = [
        str(item.get("id"))
        for item in artifacts
        if item.get("type") in source_types and item.get("id") and item.get("id") != WALKTHROUGH_MAP_ARTIFACT_ID
    ]
    return _unique_list(ids)


def _merge_page_evidence_source_artifacts(
    artifacts: list[dict[str, Any]],
    page_evidence_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(artifacts)
    seen = {
        str(item.get("id") or item.get("artifact_id") or item.get("path") or "")
        for item in merged
        if item.get("id") or item.get("artifact_id") or item.get("path")
    }
    for source in page_evidence_sources:
        item = dict(source)
        artifact_id = item.get("id") or item.get("artifact_id")
        if artifact_id:
            item["id"] = str(artifact_id)
        path = _safe_run_relative_path(item.get("path"), allowed_prefix="page-evidence")
        if not path:
            continue
        item["path"] = path
        key = str(item.get("id") or path)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _evidence_by_id(raw_evidence: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_evidence, list):
        return {}
    return {str(item.get("id")): item for item in raw_evidence if isinstance(item, dict) and item.get("id")}


def _screenshot_artifact_lookup(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if artifact.get("type") != "screenshot":
            continue
        artifact_id = str(artifact.get("id") or "")
        rel_path = _safe_run_relative_path(artifact.get("path"), allowed_prefix="screenshots")
        if not rel_path:
            continue
        for key in {artifact_id, rel_path, PurePosixPath(rel_path).name}:
            if key:
                lookup[key] = artifact
    return lookup


def _page_evidence_artifact_lookup(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        artifact_type = str(artifact.get("type") or "")
        if artifact_type not in {
            "page_evidence_manifest",
            "page_html",
            "page_text",
            "page_elements",
            "accessibility_tree",
            "dom_snapshot",
            "network_log",
            "console_log",
        }:
            continue
        artifact_id = str(artifact.get("id") or "")
        rel_path = _safe_run_relative_path(artifact.get("path"), allowed_prefix="page-evidence")
        if not rel_path:
            continue
        for key in {artifact_id, rel_path, PurePosixPath(rel_path).name}:
            if key:
                lookup[key] = artifact
    return lookup


def _artifact_for_ref(ref: str, lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(ref, str) or not ref.strip():
        return None
    normalized = ref.strip().replace("\\", "/")
    if normalized in lookup:
        return lookup[normalized]
    safe_rel = _safe_run_relative_path(normalized, allowed_prefix="screenshots")
    if safe_rel and safe_rel in lookup:
        return lookup[safe_rel]
    name = PurePosixPath(normalized).name
    if name in lookup:
        return lookup[name]
    return None


def _page_evidence_summary(
    evidence_items: list[dict[str, Any]],
    page_evidence_artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    for item in evidence_items:
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        page_evidence = data.get("page_evidence")
        if not isinstance(page_evidence, dict):
            continue
        summaries.append(_page_evidence_summary_from_data(page_evidence, page_evidence_artifacts))
    if not summaries:
        return {}

    merged: dict[str, Any] = {"artifact_ids": [], "key_controls": [], "artifacts": [], "screenshot_paths": [], "errors": []}
    for summary in summaries:
        for key in (
            "status",
            "captured_at",
            "url",
            "title",
            "page_name",
            "page_type",
            "purpose",
            "text_excerpt",
            "dom_summary",
        ):
            if summary.get(key) and not merged.get(key):
                merged[key] = summary[key]
        for key in ("network_event_count", "console_message_count", "page_error_count", "element_count"):
            if summary.get(key) is not None:
                merged[key] = max(int(merged.get(key) or 0), int(summary.get(key) or 0))
        for artifact_id in summary.get("artifact_ids") or []:
            _append_unique(merged["artifact_ids"], artifact_id, limit=24)
        for control in summary.get("key_controls") or []:
            _append_unique(merged["key_controls"], control, limit=12)
        for path in summary.get("screenshot_paths") or []:
            _append_unique(merged["screenshot_paths"], path, limit=8)
        for error in summary.get("errors") or []:
            _append_unique(merged["errors"], error, limit=5)
        for artifact in summary.get("artifacts") or []:
            if not isinstance(artifact, dict):
                continue
            existing_keys = {
                item.get("artifact_id") or item.get("path")
                for item in merged["artifacts"]
                if isinstance(item, dict)
            }
            artifact_key = artifact.get("artifact_id") or artifact.get("path")
            if artifact_key not in existing_keys:
                merged["artifacts"].append(artifact)
    return {key: value for key, value in merged.items() if value not in ("", [], None)}


def _page_evidence_summary_from_data(
    page_evidence: dict[str, Any],
    page_evidence_artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    artifact_refs = _page_evidence_artifact_refs(page_evidence)
    artifacts = [_artifact_for_ref(ref, page_evidence_artifacts) for ref in artifact_refs]
    artifacts = [artifact for artifact in artifacts if artifact is not None]
    payload_by_type: dict[str, list[Any]] = {}
    artifact_ids: list[str] = []
    for artifact in artifacts:
        artifact_id = str(artifact.get("id") or "")
        if artifact_id:
            _append_unique(artifact_ids, artifact_id, limit=24)
        artifact_type = str(artifact.get("type") or "")
        if "payload" in artifact:
            payload_by_type.setdefault(artifact_type, []).append(artifact.get("payload"))

    manifest_payload = _first_dict(payload_by_type.get("page_evidence_manifest"))
    text_payload = _first_dict(payload_by_type.get("page_text"))
    elements_payload = _first_dict(payload_by_type.get("page_elements"))
    dom_payload = _first_dict(payload_by_type.get("dom_snapshot"))
    accessibility_payload = _first_dict(payload_by_type.get("accessibility_tree"))
    errors = _string_list(page_evidence.get("errors") if isinstance(page_evidence.get("errors"), list) else [])
    if manifest_payload and isinstance(manifest_payload.get("errors"), list):
        errors.extend(_string_list(manifest_payload["errors"]))
    if manifest_payload and isinstance(manifest_payload.get("page_errors"), list):
        errors.extend(_string_list(manifest_payload["page_errors"]))

    title = (
        _safe_text(page_evidence.get("page_name"), limit=120)
        or _safe_text(page_evidence.get("name"), limit=120)
        or _safe_text(page_evidence.get("title"), limit=160)
        or _safe_text(manifest_payload.get("title") if manifest_payload else None, limit=160)
    )
    text_excerpt = _text_excerpt_from_page_evidence(page_evidence, text_payload)
    key_controls = _controls_from_page_evidence(page_evidence, elements_payload, accessibility_payload)
    dom_summary = _dom_summary(dom_payload, elements_payload, accessibility_payload)
    page_type = _safe_page_type(page_evidence.get("page_type") or page_evidence.get("type"))
    if page_type is None:
        page_type = _page_type(
            _safe_text(page_evidence.get("url") or (manifest_payload or {}).get("url"), limit=240),
            title,
            f"{text_excerpt} {' '.join(key_controls)}",
        )

    return {
        "status": _safe_text(page_evidence.get("status") or (manifest_payload or {}).get("status"), limit=80),
        "captured_at": _safe_text(page_evidence.get("captured_at") or (manifest_payload or {}).get("captured_at"), limit=80),
        "url": _safe_text(page_evidence.get("url") or (manifest_payload or {}).get("url"), limit=240),
        "title": title,
        "page_name": title,
        "page_type": page_type,
        "purpose": _safe_text(page_evidence.get("purpose"), limit=260),
        "text_excerpt": text_excerpt,
        "dom_summary": dom_summary,
        "key_controls": key_controls,
        "artifact_ids": artifact_ids,
        "artifacts": _page_evidence_artifact_ref_items(artifact_refs, page_evidence_artifacts),
        "screenshot_paths": _page_evidence_screenshot_paths(page_evidence),
        "network_event_count": _int_or_none(page_evidence.get("network_event_count")),
        "console_message_count": _int_or_none(page_evidence.get("console_message_count")),
        "page_error_count": _int_or_none(page_evidence.get("page_error_count")) or len(errors),
        "element_count": _element_count(elements_payload),
        "errors": _unique_list(errors)[:5],
    }


def _page_evidence_artifact_refs(page_evidence: dict[str, Any]) -> list[str]:
    refs: list[Any] = []
    for key in (
        "manifest_path",
        "html_path",
        "page_html_path",
        "text_path",
        "elements_path",
        "dom_snapshot_path",
        "accessibility_tree_path",
        "network_log_path",
        "console_log_path",
    ):
        refs.append(page_evidence.get(key))
    artifact_paths = page_evidence.get("artifact_paths")
    if isinstance(artifact_paths, list):
        refs.extend(artifact_paths)
    return _string_list(refs)


def _page_evidence_artifact_ref_items(
    refs: list[str],
    page_evidence_artifacts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        path = _safe_run_relative_path(ref, allowed_prefix="page-evidence")
        if not path:
            continue
        artifact = _artifact_for_ref(ref, page_evidence_artifacts)
        artifact_type = str(artifact.get("type") or "") if artifact else ""
        metadata = artifact.get("metadata") if artifact and isinstance(artifact.get("metadata"), dict) else {}
        artifact_id = _safe_text(artifact.get("id"), limit=120) if artifact else ""
        key = artifact_id or path
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "kind": _page_evidence_artifact_kind(artifact_type, path),
                "label": _page_evidence_artifact_label(artifact_type, path),
                "artifact_id": artifact_id or None,
                "path": path,
                "content_url": _safe_api_url(metadata.get("content_url")) or _safe_api_url(metadata.get("path_url")),
            }
        )
    return items


def _safe_page_evidence_artifact_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _safe_run_relative_path(item.get("path"), allowed_prefix="page-evidence")
        artifact_id = _safe_text(item.get("artifact_id"), limit=120) or None
        key = artifact_id or path
        if not key or key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "kind": _safe_text(item.get("kind"), limit=40) or _page_evidence_artifact_kind("", path or ""),
                "label": _safe_text(item.get("label"), limit=80) or _page_evidence_artifact_label("", path or ""),
                "artifact_id": artifact_id,
                "path": path,
                "content_url": _safe_api_url(item.get("content_url")),
            }
        )
    return refs


def _page_evidence_screenshot_paths(page_evidence: dict[str, Any]) -> list[str]:
    refs: list[Any] = [
        page_evidence.get("viewport_screenshot_path"),
        page_evidence.get("full_page_screenshot_path"),
        page_evidence.get("screenshot_path"),
    ]
    screenshot_paths = page_evidence.get("screenshot_paths")
    if isinstance(screenshot_paths, list):
        refs.extend(screenshot_paths)
    paths: list[str] = []
    for ref in refs:
        path = _safe_run_relative_path(ref, allowed_prefix="screenshots")
        if path:
            _append_unique(paths, path, limit=8)
    return paths


def _page_evidence_artifact_kind(artifact_type: str, path: str) -> str:
    by_type = {
        "page_evidence_manifest": "manifest",
        "page_html": "html",
        "page_text": "text",
        "page_elements": "elements",
        "dom_snapshot": "dom",
        "accessibility_tree": "accessibility",
        "network_log": "network",
        "console_log": "console",
    }
    if artifact_type in by_type:
        return by_type[artifact_type]
    name = PurePosixPath(path).name.lower()
    if name == "manifest.json":
        return "manifest"
    if name.endswith(".html"):
        return "html"
    return PurePosixPath(path).stem.replace("_", "-") or "artifact"


def _page_evidence_artifact_label(artifact_type: str, path: str) -> str:
    by_kind = {
        "manifest": "Page evidence manifest",
        "html": "Page HTML",
        "text": "Visible text",
        "elements": "Interactive elements",
        "dom": "DOM snapshot",
        "accessibility": "Accessibility tree",
        "network": "Network log",
        "console": "Console log",
    }
    return by_kind.get(_page_evidence_artifact_kind(artifact_type, path), PurePosixPath(path).name or "Page evidence artifact")


def _text_excerpt_from_page_evidence(page_evidence: dict[str, Any], text_payload: dict[str, Any] | None) -> str:
    candidates = [
        page_evidence.get("text"),
        page_evidence.get("text_excerpt"),
        page_evidence.get("summary"),
        text_payload.get("text") if text_payload else None,
    ]
    for candidate in candidates:
        text = _safe_text(candidate, limit=360)
        if text:
            return text
    return ""


def _controls_from_page_evidence(
    page_evidence: dict[str, Any],
    elements_payload: dict[str, Any] | None,
    accessibility_payload: dict[str, Any] | None,
) -> list[str]:
    controls: list[str] = []
    for key in ("key_controls", "controls"):
        values = page_evidence.get(key)
        if isinstance(values, list):
            for value in values:
                label = _safe_text(value, limit=80)
                if label:
                    _append_unique(controls, label, limit=12)

    items = elements_payload.get("items") if elements_payload else None
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict) or item.get("visible") is False or item.get("disabled") is True:
                continue
            tag = str(item.get("tag") or "").lower()
            role = str(item.get("role") or "").lower()
            input_type = str(item.get("type") or "").lower()
            if tag not in {"a", "button", "input", "select", "textarea", "summary"} and role not in {
                "button",
                "link",
                "menuitem",
                "tab",
                "checkbox",
                "combobox",
                "searchbox",
                "textbox",
            }:
                continue
            if input_type in {"hidden", "password"}:
                continue
            label = (
                _safe_text(item.get("text"), limit=80)
                or _safe_text(item.get("aria_label"), limit=80)
                or _safe_text(item.get("placeholder"), limit=80)
                or _safe_text(item.get("name"), limit=80)
            )
            if label:
                _append_unique(controls, label, limit=12)

    ax_nodes = accessibility_payload.get("nodes") if accessibility_payload else None
    if isinstance(ax_nodes, list):
        for node in ax_nodes:
            if not isinstance(node, dict):
                continue
            role = _ax_value(node.get("role")).lower()
            if role not in {"button", "link", "menuitem", "tab", "checkbox", "combobox", "searchbox", "textbox"}:
                continue
            label = _safe_text(_ax_value(node.get("name")), limit=80)
            if label:
                _append_unique(controls, label, limit=12)
    return controls[:12]


def _dom_summary(
    dom_payload: dict[str, Any] | None,
    elements_payload: dict[str, Any] | None,
    accessibility_payload: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    element_count = _element_count(elements_payload)
    if element_count:
        parts.append(f"{element_count} interactive elements captured")
    documents = dom_payload.get("documents") if dom_payload else None
    if isinstance(documents, list):
        parts.append(f"{len(documents)} DOM document snapshots")
    ax_nodes = accessibility_payload.get("nodes") if accessibility_payload else None
    if isinstance(ax_nodes, list):
        parts.append(f"{len(ax_nodes)} accessibility nodes")
    return _safe_text("; ".join(parts), limit=220)


def _element_count(elements_payload: dict[str, Any] | None) -> int | None:
    items = elements_payload.get("items") if elements_payload else None
    return len(items) if isinstance(items, list) else None


def _first_dict(values: list[Any] | None) -> dict[str, Any] | None:
    for value in values or []:
        if isinstance(value, dict):
            return value
    return None


def _ax_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or "")
    return str(value or "")


def _safe_page_type(value: Any) -> str | None:
    text = _safe_text(value, limit=40).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "login": "auth",
        "signin": "auth",
        "sign_in": "auth",
        "home": "dashboard",
        "overview": "dashboard",
        "table": "list",
        "record_list": "list",
        "record_detail": "detail",
        "details": "detail",
        "configuration": "settings",
        "edit": "form",
        "create": "form",
    }
    text = aliases.get(text, text)
    return text if text in {"dashboard", "list", "detail", "settings", "form", "auth", "error", "external", "unknown"} else None



def _normalize_path(path: str) -> tuple[str, bool]:
    raw_segments = [segment for segment in path.split("/") if segment]
    segments: list[str] = []
    dynamic = False
    for segment in raw_segments:
        normalized_segment, is_dynamic = _normalize_segment(segment)
        dynamic = dynamic or is_dynamic
        segments.append(normalized_segment)
    return "/" + "/".join(segments), dynamic


def _normalize_fragment(fragment: str) -> tuple[str, bool]:
    if not fragment:
        return "", False
    body, _, query = fragment.partition("?")
    prefix = ""
    route_body = body
    if body.startswith("!/"):
        prefix = "!"
        route_body = body[1:]
    if route_body.startswith("/"):
        normalized_body, dynamic = _normalize_path(route_body)
    else:
        normalized_body = _safe_fragment_text(route_body)
        dynamic = False
    cleaned_query = _clean_query(query)
    result = f"{prefix}{normalized_body}" if prefix else normalized_body
    if cleaned_query:
        result = f"{result}?{cleaned_query}"
    return result, dynamic


def _normalize_segment(segment: str) -> tuple[str, bool]:
    cleaned = segment.strip()
    if _looks_dynamic_segment(cleaned):
        return ":id", True
    return cleaned.lower(), False


def _looks_dynamic_segment(segment: str) -> bool:
    value = segment.strip()
    if not value:
        return False
    if re.fullmatch(r"\d+", value):
        return True
    if re.fullmatch(r"[0-9a-fA-F]{8,}", value):
        return True
    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{13,}", value):
        return True
    if re.fullmatch(r"[a-zA-Z]{2,12}_[A-Za-z0-9]{6,}", value):
        return True
    if re.fullmatch(r"[A-Za-z]+[-_][A-Za-z0-9]{8,}", value) and any(ch.isdigit() for ch in value):
        return True
    if len(value) >= 12 and re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
        return True
    return False


def _clean_query(query: str) -> str:
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=False):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS or lowered in STATE_QUERY_KEYS:
            continue
        if any(marker in lowered for marker in SENSITIVE_QUERY_MARKERS):
            continue
        kept.append((key, _safe_text(value, limit=160)))
    return urlencode(sorted(kept), doseq=True)


def _step_screenshot_refs(step: dict[str, Any], evidence_items: list[dict[str, Any]]) -> list[str]:
    refs: list[Any] = [step.get("screenshot")]
    for item in evidence_items:
        refs.append(item.get("screenshot"))
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        refs.append(data.get("screenshot_path"))
        screenshot_paths = data.get("screenshot_paths")
        if isinstance(screenshot_paths, list):
            refs.extend(screenshot_paths)
        page_evidence = data.get("page_evidence")
        if isinstance(page_evidence, dict):
            for key in ("viewport_screenshot_path", "full_page_screenshot_path", "screenshot_path"):
                refs.append(page_evidence.get(key))
            nested_screenshots = page_evidence.get("screenshot_paths")
            if isinstance(nested_screenshots, list):
                refs.extend(nested_screenshots)
    return _string_list(refs)


def _action_names_from_history_entry(entry: dict[str, Any]) -> list[str]:
    model_output = entry.get("model_output") if isinstance(entry.get("model_output"), dict) else {}
    actions = model_output.get("action") if isinstance(model_output.get("action"), list) else []
    names: list[str] = []
    for action in actions:
        if isinstance(action, dict):
            names.extend(str(key) for key in action.keys())
    return names


def _history_observation(entry: dict[str, Any]) -> str:
    parts: list[str] = []
    results = entry.get("result") if isinstance(entry.get("result"), list) else []
    for result in results:
        if not isinstance(result, dict):
            continue
        for key in ("extracted_content", "long_term_memory", "error"):
            value = result.get(key)
            if value:
                parts.append(str(value))
    return _safe_text(" | ".join(parts), limit=1200)


def _safe_text(value: Any, *, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ").strip()
    for pattern in SENSITIVE_TEXT_PATTERNS:
        text = pattern.sub("<redacted>", text)
    text = re.sub(r"(?i)(password|token|secret|credential|api[_ -]?key)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)(storage_state|user_data_dir|profile_dir)\s*[:=]\s*[^\s\"'<>;,]+", "<redacted-path>", text)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"'<>]+", "<redacted-path>", text)
    text = re.sub(r"(?<!http:)(?<!https:)(?:/Users|/home|/tmp|/private/tmp|/var/folders)/[^\s\"'<>]+", "<redacted-path>", text)
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "..."
    return text


def _clean_title(title: Any, host: str) -> str | None:
    text = _safe_text(title, limit=160)
    if not text:
        return None
    lowered = text.lower().strip()
    if lowered in GENERIC_TITLES or lowered == host or lowered.startswith(f"{host}/"):
        return None
    text = re.sub(r"\s*[-|]\s*Clink\s*$", "", text).strip()
    return text or None


def _safe_run_relative_path(value: Any, *, allowed_prefix: str) -> str | None:
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


def _safe_api_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("/api/runs/"):
        return None
    if "\\" in value or ".." in value:
        return None
    return value


def _safe_fragment_text(value: str) -> str:
    text = _safe_text(value, limit=200)
    return re.sub(r"[^A-Za-z0-9._~!$&'()*+,;=:@/-]", "", text)


def _looks_like_local_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("/", "\\", "~")))


def _name_from_route(route: str, host: str) -> str:
    route_without_hash = route.split("#")[-1] if "#" in route else route
    parts = [part for part in route_without_hash.split("/") if part and part != ":id"]
    if not parts:
        return host.split(":")[0] if host else "Home"
    if len(parts) >= 2 and parts[-2] == "settings":
        return f"{_titleize(parts[-1])} Settings"
    return _titleize(parts[-1])


def _titleize(value: str) -> str:
    text = value.replace("_", "-").replace("%20", "-")
    return " ".join(part.capitalize() for part in text.split("-") if part) or "Page"


def _page_type(route: str, title: str | None, observation: str | None) -> str:
    text = f"{route} {title or ''} {observation or ''}".lower()
    route_l = route.lower()
    if any(marker in route_l for marker in ("login", "signin", "sign-in", "/auth")):
        return "auth"
    if any(marker in text for marker in ("404", "not found", " error")):
        return "error"
    if any(marker in route for marker in (":id", "/detail", "/details")):
        return "detail"
    if "settings" in text or "merchant setting" in text:
        return "settings"
    if any(marker in text for marker in ("login", "signin", "sign-in")):
        return "auth"
    if any(marker in text for marker in ("form", "create", "edit", "new ")):
        return "form"
    if any(marker in text for marker in ("analytics", "dashboard", "overview", "home")):
        return "dashboard"
    if any(marker in text for marker in ("transactions", "balances", "customers", "subscriptions", "products", "table", "list")):
        return "list"
    return "unknown"


def _extract_controls(text: str) -> list[str]:
    controls: list[str] = []
    for match in re.finditer(r'Clicked(?:\s+a)?(?:\s+role=[\w-]+)?\s+"([^"]+)"', text):
        label = _safe_text(match.group(1), limit=80)
        if label:
            controls.append(label)
    for match in re.finditer(r"\b(?:controls?|filters?|tabs?) (?:included|include|visible) ([^.]+)", text, re.IGNORECASE):
        for label in re.split(r",|\band\b", match.group(1)):
            label = _safe_text(label, limit=80).strip(" .")
            if label and len(label.split()) <= 5:
                controls.append(label)
    return _unique_list(controls)[:12]


def _extract_first_click_label(text: str) -> str | None:
    match = re.search(r'Clicked(?:\s+a)?(?:\s+role=[\w-]+)?\s+"([^"]+)"', text)
    if not match:
        return None
    return _safe_text(match.group(1), limit=80) or None


def _key_functions(node: dict[str, Any]) -> list[str]:
    page_type = node.get("page_type")
    name = str(node.get("name") or "Page")
    defaults = {
        "dashboard": [f"{name} overview", "Metric review"],
        "list": [f"{name} list review", "Search and filter"],
        "detail": [f"{name} detail review"],
        "settings": [f"{name} configuration review"],
        "form": [f"{name} form review"],
        "auth": ["Authentication"],
        "error": ["Error state"],
        "external": ["External destination"],
    }
    functions = defaults.get(str(page_type), [f"{name} review"])
    return _unique_list(functions)[:8]


def _purpose(node: dict[str, Any]) -> str:
    name = str(node.get("name") or "This page")
    page_type = str(node.get("page_type") or "unknown")
    page_evidence = node.get("metadata", {}).get("page_evidence")
    if isinstance(page_evidence, dict):
        purpose = _safe_text(page_evidence.get("purpose"), limit=260)
        if purpose:
            return purpose
    if page_type == "dashboard":
        return f"{name} provides an overview surface observed during the walkthrough."
    if page_type == "list":
        return f"{name} appears to support reviewing records, filters, and table state."
    if page_type == "settings":
        return f"{name} exposes configuration or account settings observed read-only."
    if page_type == "detail":
        return f"{name} is a detail route grouped by its dynamic URL pattern."
    if page_type == "external":
        return f"{name} is outside the product host and was treated as an external node."
    if page_type == "error":
        return f"{name} represents an error or blocked surface observed by the walker."
    return f"{name} was observed during the product walkthrough."


def _meaningful_observation(summary: str) -> bool:
    lowered = summary.lower().strip()
    if not lowered:
        return False
    low_value_prefixes = ("waited for", "data written to file", "successfully replaced all occurrences")
    return not any(lowered.startswith(prefix) for prefix in low_value_prefixes)


def _finding_matches_node(finding: dict[str, Any], evidence_ids: list[str], node: dict[str, Any]) -> bool:
    node_evidence = set(node.get("evidence_ids") or [])
    if node_evidence.intersection(evidence_ids):
        return True
    text = f"{finding.get('theme') or ''} {finding.get('claim') or ''}".lower()
    name = str(node.get("name") or "").lower()
    route = str(node.get("route") or "").lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", f"{name} {route}") if len(token) >= 4 and token != "page"}
    return any(token in text for token in tokens)


def _severity(value: Any) -> str:
    lowered = str(value or "info").lower()
    return lowered if lowered in {"info", "low", "medium", "high"} else "info"


def _screenshot_id(artifact: dict[str, Any], step_index: int | None) -> str:
    source = str(artifact.get("id") or artifact.get("path") or "screenshot")
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    step = "unknown" if step_index is None else str(step_index)
    return f"shot_step_{step}_{digest}"


def _is_better_name(title: str, current_name: Any, route: str | None = None) -> bool:
    current = str(current_name or "")
    lowered = title.lower()
    if len(title) > 40 or lowered in GENERIC_TITLES:
        return False
    if not current:
        return True
    if lowered == current.lower():
        return False
    if _roughly_matches(title, current):
        return True
    if route and _roughly_matches(title, _name_from_route(route, "")):
        return True
    return "." in current or ":" in current or current.lower() in {"page", "product"}


def _roughly_matches(label: str, target_name: str) -> bool:
    left = set(re.split(r"[^a-z0-9]+", label.lower()))
    right = set(re.split(r"[^a-z0-9]+", target_name.lower()))
    left.discard("")
    right.discard("")
    return bool(left and right and left.intersection(right))


def _string_list(values: list[Any]) -> list[str]:
    return [str(value).strip() for value in values if isinstance(value, str) and value.strip()]


def _unique_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _append_unique(values: list[Any], value: Any, *, limit: int | None = None) -> None:
    if value is None or value == "":
        return
    if value in values:
        return
    if limit is not None and len(values) >= limit:
        return
    values.append(value)


def _float_between(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return round(min(max(number, 0.0), 1.0), 2)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _identifier_slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    text = re.sub(r"_+", "_", text)
    return text.strip("_") or "item"


def _step_sort_key(record: StepRecord) -> tuple[int, str, int]:
    return (record.result_order, record.scenario_id, record.index if record.index is not None else 10**9)


def _first_product_name(payload: dict[str, Any]) -> str | None:
    products = _products_from_payload(payload)
    return products[0]["name"] if products else None


def parse_jsonish_summary(text: str | None) -> dict[str, Any] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = text.strip()
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
