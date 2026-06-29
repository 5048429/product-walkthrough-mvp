from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ChecklistItem, ProductTarget, ResearchPlan, Scenario, normalize_report_language, slugify


class ConfigError(ValueError):
    pass


def load_research_plan(path: str | Path) -> ResearchPlan:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    return parse_research_plan(data)


def parse_research_plan(data: dict[str, Any]) -> ResearchPlan:
    research_goal = str(data.get("research_goal") or "").strip()
    if not research_goal:
        raise ConfigError("research_goal is required")

    products_data = data.get("products")
    if not isinstance(products_data, list) or not products_data:
        raise ConfigError("products must be a non-empty list")

    products = [_parse_product(item) for item in products_data]
    scenarios = [_parse_scenario(item) for item in data.get("scenarios", [])]
    checklist = _parse_checklist(data.get("checklist"))
    evaluation = data.get("evaluation") if isinstance(data.get("evaluation"), dict) else {}
    try:
        report_language = normalize_report_language(data.get("report_language") or data.get("language"))
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    return ResearchPlan(
        research_goal=research_goal,
        products=products,
        scenarios=scenarios,
        checklist=checklist,
        evaluation=evaluation,
        report_language=report_language,
    )


def _parse_product(item: dict[str, Any]) -> ProductTarget:
    name = str(item.get("name") or "").strip()
    url = str(item.get("url") or "").strip()
    if not name or not url:
        raise ConfigError("Each product requires name and url")
    return ProductTarget(
        name=name,
        url=url,
        kind=str(item.get("kind") or "competitor"),
        credentials_ref=item.get("credentials_ref"),
        notes=str(item.get("notes") or ""),
        tags=list(item.get("tags") or []),
    )


def _parse_scenario(item: dict[str, Any]) -> Scenario:
    title = str(item.get("title") or "").strip()
    goal = str(item.get("goal") or "").strip()
    if not title or not goal:
        raise ConfigError("Each scenario requires title and goal")

    scenario_id = str(item.get("id") or slugify(title))
    return Scenario(
        id=scenario_id,
        title=title,
        persona=str(item.get("persona") or "Target user"),
        goal=goal,
        steps=[str(step) for step in item.get("steps", [])],
        success_criteria=[str(rule) for rule in item.get("success_criteria", [])],
        observation_points=[str(point) for point in item.get("observation_points", [])],
        risk_level=str(item.get("risk_level") or "normal"),
    )


def _parse_checklist(value: Any) -> list[ChecklistItem]:
    raw_items = value if isinstance(value, list) else []
    checklist: list[ChecklistItem] = []
    for index, item in enumerate(raw_items, start=1):
        if isinstance(item, str):
            title = item.strip()
            raw: dict[str, Any] = {}
        elif isinstance(item, dict):
            raw = item
            title = str(item.get("title") or item.get("expected") or item.get("check") or "").strip()
        else:
            continue
        if not title:
            continue
        check_id = str(raw.get("id") or raw.get("check_id") or f"check-{index}-{slugify(title)[:32]}")
        checklist.append(
            ChecklistItem(
                id=check_id,
                title=title,
                status=str(raw.get("status") or "untested"),
                source=str(raw.get("source") or "plan"),
                severity=str(raw.get("severity") or "medium"),
                evidence_ids=[str(item) for item in raw.get("evidence_ids", []) if str(item)] if isinstance(raw.get("evidence_ids"), list) else [],
                notes=str(raw.get("notes") or ""),
            )
        )
    return checklist
