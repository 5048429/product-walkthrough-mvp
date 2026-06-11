from __future__ import annotations

from collections import defaultdict

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
            summary = (
                f"{product} completed {len(product_results)} scenarios with "
                f"{total_blockers} blockers and {total_friction} friction points."
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
                    },
                )
            )
        return analyses

    def _findings_for_result(self, result: WalkthroughResult) -> list[Finding]:
        findings: list[Finding] = []
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

