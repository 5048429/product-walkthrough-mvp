from __future__ import annotations

from typing import Any

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
        issues = [finding for finding in findings if getattr(finding, "issue_type", "product") != "positive"]
        product_issues = [finding for finding in issues if finding.issue_type == "product"]
        coverage_gaps = [finding for finding in issues if finding.issue_type == "coverage"]
        reliability_issues = [finding for finding in issues if finding.issue_type == "system_reliability"]
        critical_issues = [
            finding
            for finding in product_issues
            if finding.severity == "high" or finding.priority in {"P0", "P1"}
        ]

        grounded = sum(1 for finding in issues if finding.evidence_ids)
        actionable = sum(1 for finding in issues if self._actionable(finding))
        schema_complete = sum(1 for finding in issues if self._schema_complete(finding))
        screenshot_grounded = sum(1 for finding in issues if finding.screenshot_refs)

        page_evidence_total = 0
        page_evidence_partial = 0
        page_evidence_failed = 0
        timeout_count = 0
        invalid_summary_count = 0
        for result in results:
            if result.metrics.get("timed_out"):
                timeout_count += 1
            for item in result.evidence:
                data = item.data if isinstance(item.data, dict) else {}
                if data.get("invalid_agent_summary"):
                    invalid_summary_count += 1
                page_evidence = data.get("page_evidence")
                if not isinstance(page_evidence, dict):
                    continue
                page_evidence_total += 1
                status = str(page_evidence.get("status") or "").lower()
                if status == "partial":
                    page_evidence_partial += 1
                elif status == "failed":
                    page_evidence_failed += 1

        checklist_total = len(plan.checklist)
        checklist_covered = sum(1 for item in plan.checklist if item.status.lower() not in {"untested", "unknown", ""})
        checklist_passed = sum(1 for item in plan.checklist if item.status.lower() in {"pass", "passed", "completed", "ok"})
        summary_checklist_total = sum(int(analysis.metrics.get("checklist_total", 0)) for analysis in analyses)
        summary_checklist_passed = sum(int(analysis.metrics.get("checklist_passed", 0)) for analysis in analyses)
        if summary_checklist_total:
            checklist_total += summary_checklist_total
            checklist_covered += summary_checklist_total
            checklist_passed += summary_checklist_passed

        evidence_coverage_rate = self._ratio(evidence_covered, result_count)
        finding_grounding_rate = self._ratio(grounded, len(issues))
        recommendation_actionability_rate = self._ratio(actionable, len(issues))
        issue_schema_completeness_rate = self._ratio(schema_complete, len(issues))
        screenshot_grounding_rate = self._ratio(screenshot_grounded, len(issues))
        page_evidence_success_rate = self._ratio(
            page_evidence_total - page_evidence_partial - page_evidence_failed,
            page_evidence_total,
        )
        timeout_rate = self._ratio(timeout_count, result_count)
        invalid_summary_rate = self._ratio(invalid_summary_count, result_count)
        checklist_coverage_rate = self._ratio(checklist_covered, checklist_total)
        checklist_pass_rate = self._ratio(checklist_passed, checklist_total)
        evidence_quality_score = round(
            (
                evidence_coverage_rate * 0.35
                + finding_grounding_rate * 0.25
                + screenshot_grounding_rate * 0.2
                + page_evidence_success_rate * 0.2
            ),
            3,
        )

        scores: dict[str, Any] = {
            "task_completion_rate": self._ratio(completed, result_count),
            "evidence_coverage_rate": evidence_coverage_rate,
            "finding_grounding_rate": finding_grounding_rate,
            "recommendation_actionability_rate": recommendation_actionability_rate,
            "issue_schema_completeness_rate": issue_schema_completeness_rate,
            "screenshot_grounding_rate": screenshot_grounding_rate,
            "checklist_coverage_rate": checklist_coverage_rate,
            "checklist_pass_rate": checklist_pass_rate,
            "page_evidence_success_rate": page_evidence_success_rate,
            "page_evidence_partial_rate": self._ratio(page_evidence_partial, page_evidence_total),
            "page_evidence_failed_rate": self._ratio(page_evidence_failed, page_evidence_total),
            "timeout_rate": timeout_rate,
            "invalid_summary_rate": invalid_summary_rate,
            "evidence_quality_score": evidence_quality_score,
            "evidence_items": evidence_count,
            "findings": len(findings),
            "issues": len(issues),
            "product_issues": len(product_issues),
            "coverage_gaps": len(coverage_gaps),
            "system_reliability_issues": len(reliability_issues),
            "critical_issues": len(critical_issues),
        }

        weighted = (
            scores["task_completion_rate"] * 0.2
            + evidence_quality_score * 0.25
            + finding_grounding_rate * 0.15
            + recommendation_actionability_rate * 0.15
            + issue_schema_completeness_rate * 0.15
            + page_evidence_success_rate * 0.1
        )
        quality_gate_status = self._quality_gate_status(plan, scores)
        scores["quality_gate_passed"] = 1.0 if quality_gate_status == "pass" else 0.0
        notes = self._notes(plan, scores, quality_gate_status)
        return EvaluationResult(
            scores=scores,
            overall_score=round(weighted, 3),
            notes=notes,
            quality_gate_status=quality_gate_status,
        )

    def _actionable(self, finding: Any) -> bool:
        return bool(
            len(str(getattr(finding, "recommendation", "")).strip()) >= 20
            and getattr(finding, "acceptance_criteria", None)
        )

    def _schema_complete(self, finding: Any) -> bool:
        return bool(
            getattr(finding, "priority", "")
            and getattr(finding, "issue_type", "")
            and getattr(finding, "current_behavior", "")
            and getattr(finding, "expected_behavior", "")
            and getattr(finding, "repro_steps", None)
            and getattr(finding, "acceptance_criteria", None)
            and getattr(finding, "evidence_ids", None)
        )

    def _ratio(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 1.0 if numerator == 0 else 0.0
        return round(numerator / denominator, 3)

    def _quality_gate_status(self, plan: ResearchPlan, scores: dict[str, Any]) -> str:
        target_completion = float(plan.evaluation.get("target_completion_rate", 0.9))
        target_grounding = float(plan.evaluation.get("target_grounded_finding_rate", 1.0))
        min_evidence_quality = float(plan.evaluation.get("min_evidence_quality_score", 0.7))
        max_timeout_rate = float(plan.evaluation.get("max_timeout_rate", 0.0))
        max_invalid_summary_rate = float(plan.evaluation.get("max_invalid_summary_rate", 0.0))
        max_reliability_issues = int(plan.evaluation.get("max_system_reliability_issues", 0))
        if float(scores["task_completion_rate"]) < target_completion:
            return "fail"
        if float(scores["finding_grounding_rate"]) < target_grounding:
            return "fail"
        if float(scores["evidence_quality_score"]) < min_evidence_quality:
            return "warn"
        if float(scores["timeout_rate"]) > max_timeout_rate:
            return "fail"
        if float(scores["invalid_summary_rate"]) > max_invalid_summary_rate:
            return "warn"
        if int(scores["system_reliability_issues"]) > max_reliability_issues:
            return "warn"
        return "pass"

    def _notes(self, plan: ResearchPlan, scores: dict[str, Any], quality_gate_status: str) -> list[str]:
        notes: list[str] = []
        target_completion = float(plan.evaluation.get("target_completion_rate", 0.9))
        target_grounding = float(plan.evaluation.get("target_grounded_finding_rate", 1.0))
        if float(scores["task_completion_rate"]) < target_completion:
            notes.append("Completion is below target; inspect blocked walkthroughs and browser credentials.")
        if float(scores["finding_grounding_rate"]) < target_grounding:
            notes.append("Some issues are not grounded in captured evidence.")
        if float(scores["issue_schema_completeness_rate"]) < 1.0:
            notes.append("Some issues are missing repro steps, expected behavior, or acceptance criteria.")
        if float(scores["evidence_quality_score"]) < float(plan.evaluation.get("min_evidence_quality_score", 0.7)):
            notes.append("Evidence quality is below the PM replacement threshold.")
        if int(scores["coverage_gaps"]):
            notes.append("Coverage gaps remain; high-risk entries need safe probing or explicit exclusions.")
        if int(scores["system_reliability_issues"]):
            notes.append("System reliability issues were separated from product issues and should be fixed before trusting conclusions.")
        if not notes:
            notes.append("Run meets the configured PM-review quality gate.")
        notes.append(f"Quality gate: {quality_gate_status}.")
        return notes
