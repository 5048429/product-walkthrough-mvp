from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any

from ..models import (
    CompetitiveInsight,
    EvidenceItem,
    Finding,
    ProductAnalysis,
    WalkthroughResult,
    slugify,
)


class ProductAnalyst:
    def analyze(self, results: list[WalkthroughResult]) -> list[ProductAnalysis]:
        by_product: dict[str, list[WalkthroughResult]] = defaultdict(list)
        for result in results:
            by_product[result.product].append(result)

        analyses: list[ProductAnalysis] = []
        for product, product_results in by_product.items():
            findings: list[Finding] = []
            for result in product_results:
                findings.extend(self._findings_for_result(result))
            avg_completion = self._avg(result.metrics.get("completion_score", 0) for result in product_results)
            total_blockers = sum(int(result.metrics.get("blocker_count", 0)) for result in product_results)
            total_friction = sum(int(result.metrics.get("friction_count", 0)) for result in product_results)
            structured_count = sum(
                1 for finding in findings if not finding.id.endswith("-positive")
            )
            summary = (
                f"{product} completed {len(product_results)} scenarios with "
                f"{total_blockers} blockers, {total_friction} runtime friction points, "
                f"and {structured_count} product findings."
            )
            analyses.append(
                ProductAnalysis(
                    product=product,
                    summary=summary,
                    findings=findings,
                    metrics={
                        "scenario_count": len(product_results),
                        "avg_completion_score": round(avg_completion, 2),
                        "total_blockers": total_blockers,
                        "total_friction": total_friction,
                        "structured_findings": structured_count,
                    },
                )
            )
        return analyses

    def _findings_for_result(self, result: WalkthroughResult) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._structured_findings_for_result(result))
        for step in result.steps:
            if step.status not in {"friction", "blocked"}:
                continue
            severity = "high" if step.status == "blocked" else "medium"
            theme = "Completion blocker" if step.status == "blocked" else "Experience friction"
            findings.append(
                Finding(
                    id=f"fn-{slugify(result.product)}-{result.scenario_id}-{step.index}",
                    product=result.product,
                    scenario_id=result.scenario_id,
                    severity=severity,
                    theme=theme,
                    claim=step.observation,
                    evidence_ids=step.evidence_ids,
                    recommendation=self._recommendation(step.status),
                    confidence=0.75 if step.status == "friction" else 0.85,
                )
            )
        if not findings and result.evidence:
            findings.append(
                Finding(
                    id=f"fn-{slugify(result.product)}-{result.scenario_id}-positive",
                    product=result.product,
                    scenario_id=result.scenario_id,
                    severity="low",
                    theme="Baseline pass",
                    claim="The configured journey produced enough evidence without obvious blockers.",
                    evidence_ids=[result.evidence[0].id],
                    recommendation="Replay this scenario with a real browser session before making release decisions.",
                    confidence=0.6,
                )
            )
        return findings

    def _recommendation(self, status: str) -> str:
        if status == "blocked":
            return "Run a real browser replay, capture the failing screen, and define the product owner for the blocker."
        return "Add clearer guidance, validation, or success feedback around this step."

    def _structured_findings_for_result(self, result: WalkthroughResult) -> list[Finding]:
        payload, evidence_id = self._final_summary_payload(result)
        if not payload or not evidence_id:
            return []

        recommendations = self._as_text_list(payload.get("top_recommendations"))
        raw_items: list[tuple[str, str]] = []
        for item in self._as_text_list(payload.get("blockers") or payload.get("blocked_sections")):
            raw_items.append(("blocker", item))
        for item in self._as_text_list(payload.get("friction_points")):
            raw_items.append(("friction", item))

        findings: list[Finding] = []
        seen_claims: set[str] = set()
        for index, (source, claim) in enumerate(raw_items, start=1):
            claim = self._clean_text(claim)
            if not claim or self._is_non_issue(claim):
                continue
            normalized = self._normalize_claim(claim)
            if normalized in seen_claims:
                continue
            seen_claims.add(normalized)

            severity, theme = self._classify_issue(claim, source)
            recommendation = self._best_recommendation(
                claim,
                recommendations,
                fallback=self._fallback_recommendation(theme, source),
            )
            findings.append(
                Finding(
                    id=f"fn-{slugify(result.product)}-{result.scenario_id}-summary-{index}",
                    product=result.product,
                    scenario_id=result.scenario_id,
                    severity=severity,
                    theme=theme,
                    claim=claim,
                    evidence_ids=[evidence_id],
                    recommendation=recommendation,
                    confidence=0.82 if source == "friction" else 0.86,
                )
            )
        return findings

    def _final_summary_payload(self, result: WalkthroughResult) -> tuple[dict[str, Any] | None, str | None]:
        candidates: list[tuple[str, str]] = []
        for item in result.evidence:
            if item.kind == "browser_run":
                final_output = item.data.get("final_output")
                if isinstance(final_output, str):
                    candidates.append((final_output, item.id))
                candidates.append((item.summary, item.id))
        for item in result.evidence:
            if item.kind == "browser_step":
                candidates.append((item.summary, item.id))

        for text, evidence_id in candidates:
            payload = self._parse_first_json_object(text)
            if payload and self._looks_like_walkthrough_summary(payload):
                return payload, evidence_id
        return None, None

    def _parse_first_json_object(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        payload = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        return None
                    return payload if isinstance(payload, dict) else None
        return None

    def _looks_like_walkthrough_summary(self, payload: dict[str, Any]) -> bool:
        keys = set(payload)
        return bool(keys & {"completed", "blockers", "friction_points", "top_recommendations", "evidence_needed"})

    def _as_text_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            parts: list[str] = []
            for key in ("area", "section", "title", "detail", "claim", "summary", "status"):
                item = value.get(key)
                if item:
                    parts.append(str(item))
            if parts:
                return [": ".join(parts)]
            return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                items.extend(self._as_text_list(item))
            return items
        return [str(value)]

    def _classify_issue(self, claim: str, source: str) -> tuple[str, str]:
        text = claim.lower()
        if any(keyword in text for keyword in ("secret", "api key", "token", "password", "credential", "private")):
            return "high", "Secret handling/admin safety"
        if any(
            keyword in text
            for keyword in (
                "destructive",
                "dangerous",
                "mutation",
                "disable",
                "save",
                "archive",
                "submit payout",
                "generate",
                "export",
                "add",
                "edit",
                "permission",
            )
        ):
            return "high", "Permission and destructive controls"
        if any(keyword in text for keyword in ("loading", "spinner", "old content", "navigation", "navigate", "submenu", "route")):
            return "medium", "Navigation and loading feedback"
        if any(keyword in text for keyword in ("empty", "no data", "no-data", "total 0")):
            return "medium", "Empty-state guidance"
        if any(keyword in text for keyword in ("external", "documentation", "help center", "support link", "leaving")):
            return "medium", "External-link clarity"
        if source == "blocker":
            return "high", "Completion blocker"
        return "medium", "Experience friction"

    def _fallback_recommendation(self, theme: str, source: str) -> str:
        fallbacks = {
            "Secret handling/admin safety": (
                "Mask sensitive values by default, require an explicit reveal action, and log/audit access."
            ),
            "Permission and destructive controls": (
                "Gate mutating controls by role and add clear confirmation before destructive or export actions."
            ),
            "Navigation and loading feedback": (
                "Use section-specific loading states and update navigation/content feedback promptly after clicks."
            ),
            "Empty-state guidance": (
                "Explain why the state is empty and provide safe next steps or filters users can try."
            ),
            "External-link clarity": (
                "Label external destinations clearly before opening documentation, help, or support links."
            ),
            "Completion blocker": (
                "Capture a replay and assign an owner to remove the blocker before relying on this flow."
            ),
        }
        if source == "blocker":
            return fallbacks.get(theme, fallbacks["Completion blocker"])
        return fallbacks.get(theme, "Add clearer guidance, validation, or success feedback around this area.")

    def _best_recommendation(self, claim: str, recommendations: list[str], fallback: str) -> str:
        if not recommendations:
            return fallback
        claim_tokens = self._tokens(claim)
        best = ""
        best_score = 0
        for recommendation in recommendations:
            score = len(claim_tokens & self._tokens(recommendation))
            if score > best_score:
                best = recommendation
                best_score = score
        return best if best_score > 0 else fallback

    def _tokens(self, text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) >= 4}

    def _is_non_issue(self, claim: str) -> bool:
        text = claim.lower()
        non_issue_markers = [
            "no hard access blocker",
            "no blocker",
            "without a login prompt",
            "authentication was already active",
            "intentionally not opened",
            "per instruction",
            "not verified",
        ]
        return any(marker in text for marker in non_issue_markers)

    def _clean_text(self, text: str) -> str:
        return " ".join(text.strip().split())

    def _normalize_claim(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _avg(self, values: object) -> float:
        items = [float(value) for value in values]
        return sum(items) / len(items) if items else 0.0


class CompetitiveAnalyst:
    def compare(
        self,
        results: list[WalkthroughResult],
        evidence: list[EvidenceItem],
    ) -> list[CompetitiveInsight]:
        by_scenario: dict[str, list[WalkthroughResult]] = defaultdict(list)
        for result in results:
            by_scenario[result.scenario_id].append(result)

        insights: list[CompetitiveInsight] = []
        for scenario_id, scenario_results in by_scenario.items():
            if len(scenario_results) < 2:
                continue
            sorted_by_completion = sorted(
                scenario_results,
                key=lambda item: float(item.metrics.get("completion_score", 0)),
                reverse=True,
            )
            leader = sorted_by_completion[0]
            laggard = sorted_by_completion[-1]
            if leader.product == laggard.product:
                continue
            evidence_ids = []
            if leader.evidence:
                evidence_ids.append(leader.evidence[0].id)
            if laggard.evidence:
                evidence_ids.append(laggard.evidence[0].id)
            insights.append(
                CompetitiveInsight(
                    theme=f"Scenario: {leader.scenario_title}",
                    claim=(
                        f"{leader.product} had the strongest completion signal for "
                        f"{scenario_id}, while {laggard.product} showed the weakest signal."
                    ),
                    products=[leader.product, laggard.product],
                    evidence_ids=evidence_ids,
                    recommendation=(
                        "Use the leader flow as a reference and inspect the weakest flow "
                        "for missing guidance, blockers, or excessive steps."
                    ),
                    confidence=0.7,
                )
            )
        return insights
