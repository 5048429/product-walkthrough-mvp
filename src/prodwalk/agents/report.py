from __future__ import annotations

from pathlib import Path

from ..models import (
    CompetitiveInsight,
    EvidenceItem,
    ProductAnalysis,
    ResearchPlan,
    ReviewNote,
    Scenario,
    WalkthroughResult,
)


class MarkdownReportWriter:
    def render(
        self,
        plan: ResearchPlan,
        scenarios: list[Scenario],
        results: list[WalkthroughResult],
        analyses: list[ProductAnalysis],
        insights: list[CompetitiveInsight],
        review_notes: list[ReviewNote],
        evidence: list[EvidenceItem],
    ) -> str:
        lines: list[str] = []
        lines.append("# Product Walkthrough Research Report")
        lines.append("")
        lines.append(f"**Research goal:** {plan.research_goal}")
        lines.append("")
        lines.append("## Scope")
        for product in plan.products:
            lines.append(f"- {product.name} ({product.kind}): {product.url}")
        lines.append("")
        lines.append("## Scenario Coverage")
        lines.append("| Product | Scenario | Status | Completion | Friction | Blockers |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: |")
        for result in results:
            lines.append(
                "| "
                f"{result.product} | {result.scenario_title} | {result.status} | "
                f"{result.metrics.get('completion_score', 0)} | "
                f"{result.metrics.get('friction_count', 0)} | "
                f"{result.metrics.get('blocker_count', 0)} |"
            )
        lines.append("")
        lines.append("## Product Findings")
        for analysis in analyses:
            lines.append(f"### {analysis.product}")
            lines.append("")
            lines.append(analysis.summary)
            lines.append("")
            for finding in analysis.findings:
                evidence_links = ", ".join(finding.evidence_ids) or "none"
                lines.append(
                    f"- **{finding.severity.upper()} / {finding.theme}:** "
                    f"{finding.claim} Evidence: `{evidence_links}`. "
                    f"Recommendation: {finding.recommendation}"
                )
            lines.append("")
        lines.append("## Competitive Insights")
        if insights:
            for insight in insights:
                lines.append(
                    f"- **{insight.theme}:** {insight.claim} "
                    f"Products: {', '.join(insight.products)}. "
                    f"Evidence: `{', '.join(insight.evidence_ids)}`. "
                    f"Recommendation: {insight.recommendation}"
                )
        else:
            lines.append("- No cross-product insight was generated. Add more products or scenarios.")
        lines.append("")
        lines.append("## Reviewer Notes")
        for note in review_notes:
            lines.append(f"- **{note.severity.upper()}** `{note.target}`: {note.message}")
        lines.append("")
        lines.append("## Evidence Appendix")
        for item in evidence:
            lines.append(f"- `{item.id}` [{item.product}/{item.scenario_id}] {item.title}: {item.summary}")
        lines.append("")
        lines.append("## Scenario Definitions")
        for scenario in scenarios:
            lines.append(f"### {scenario.title}")
            lines.append(f"- Goal: {scenario.goal}")
            lines.append(f"- Persona: {scenario.persona}")
            lines.append(f"- Success criteria: {'; '.join(scenario.success_criteria)}")
            lines.append("")
        return "\n".join(lines)

    def write(self, path: str | Path, markdown: str) -> Path:
        report_path = Path(path)
        report_path.write_text(markdown, encoding="utf-8")
        return report_path

