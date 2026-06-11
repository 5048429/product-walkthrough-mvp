from __future__ import annotations

from ..models import EvaluationResult, ProductAnalysis, ResearchPlan, WalkthroughResult


class Evaluator:
    def evaluate(
        self,
        plan: ResearchPlan,
        results: list[WalkthroughResult],
        analyses: list[ProductAnalysis],
    ) -> EvaluationResult:
        result_count = len(results)
        completed = sum(1 for result in results if result.status == "completed")
        evidence_count = sum(len(result.evidence) for result in results)
        min_evidence = int(plan.evaluation.get("min_evidence_per_result", 1))
        evidence_covered = sum(1 for result in results if len(result.evidence) >= min_evidence)

        findings = [finding for analysis in analyses for finding in analysis.findings]
        grounded = sum(1 for finding in findings if finding.evidence_ids)
        actionable = sum(1 for finding in findings if len(finding.recommendation.strip()) >= 20)

        scores = {
            "task_completion_rate": self._ratio(completed, result_count),
            "evidence_coverage_rate": self._ratio(evidence_covered, result_count),
            "finding_grounding_rate": self._ratio(grounded, len(findings)),
            "recommendation_actionability_rate": self._ratio(actionable, len(findings)),
            "evidence_items": evidence_count,
            "findings": len(findings),
        }
        weighted = (
            scores["task_completion_rate"] * 0.35
            + scores["evidence_coverage_rate"] * 0.25
            + scores["finding_grounding_rate"] * 0.25
            + scores["recommendation_actionability_rate"] * 0.15
        )
        notes = self._notes(plan, scores)
        return EvaluationResult(scores=scores, overall_score=round(weighted, 3), notes=notes)

    def _ratio(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 3)

    def _notes(self, plan: ResearchPlan, scores: dict[str, float | int]) -> list[str]:
        notes: list[str] = []
        target_completion = float(plan.evaluation.get("target_completion_rate", 0.9))
        target_grounding = float(plan.evaluation.get("target_grounded_finding_rate", 1.0))
        if float(scores["task_completion_rate"]) < target_completion:
            notes.append("Completion is below target; inspect blocked walkthroughs and browser credentials.")
        if float(scores["finding_grounding_rate"]) < target_grounding:
            notes.append("Some findings are not grounded in evidence.")
        if not notes:
            notes.append("MVP run meets the configured basic evaluation thresholds.")
        return notes

