from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]
ReportLanguage = str


def normalize_report_language(value: str | None) -> ReportLanguage:
    if value is None or not str(value).strip():
        return "en"
    normalized = str(value).strip().lower().replace("_", "-")
    aliases = {
        "en": "en",
        "english": "en",
        "zh": "zh",
        "cn": "zh",
        "chinese": "zh",
        "zh-cn": "zh",
        "zh-hans": "zh",
        "simplified-chinese": "zh",
    }
    if normalized not in aliases:
        raise ValueError("report_language must be one of: en, zh")
    return aliases[normalized]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "item"


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class ProductTarget:
    name: str
    url: str
    kind: str = "competitor"
    credentials_ref: str | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Scenario:
    id: str
    title: str
    persona: str
    goal: str
    steps: list[str]
    success_criteria: list[str]
    observation_points: list[str]
    risk_level: str = "normal"


@dataclass(slots=True)
class ResearchPlan:
    research_goal: str
    products: list[ProductTarget]
    scenarios: list[Scenario]
    evaluation: JsonDict = field(default_factory=dict)
    report_language: ReportLanguage = "en"


@dataclass(slots=True)
class WalkStep:
    index: int
    action: str
    status: str
    observation: str
    url: str = ""
    screenshot: str | None = None
    elapsed_ms: int = 0
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceItem:
    id: str
    product: str
    scenario_id: str
    kind: str
    title: str
    summary: str
    url: str = ""
    screenshot: str | None = None
    data: JsonDict = field(default_factory=dict)
    confidence: float = 1.0
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class WalkthroughResult:
    product: str
    product_kind: str
    scenario_id: str
    scenario_title: str
    status: str
    started_at: str
    completed_at: str
    steps: list[WalkStep]
    evidence: list[EvidenceItem]
    metrics: JsonDict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Finding:
    id: str
    product: str
    scenario_id: str
    severity: str
    theme: str
    claim: str
    evidence_ids: list[str]
    recommendation: str
    confidence: float = 0.8


@dataclass(slots=True)
class ProductAnalysis:
    product: str
    summary: str
    findings: list[Finding]
    metrics: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class CompetitiveInsight:
    theme: str
    claim: str
    products: list[str]
    evidence_ids: list[str]
    recommendation: str
    confidence: float = 0.75


@dataclass(slots=True)
class ReviewNote:
    severity: str
    message: str
    target: str


@dataclass(slots=True)
class EvaluationResult:
    scores: JsonDict
    overall_score: float
    notes: list[str]
