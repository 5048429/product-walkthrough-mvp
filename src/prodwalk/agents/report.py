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
            screenshot_note = self._screenshot_note(item)
            lines.append(
                f"- `{item.id}` [{item.product}/{item.scenario_id}] "
                f"{item.title}: {item.summary}{screenshot_note}"
            )
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

    def _screenshot_note(self, item: EvidenceItem) -> str:
        refs: list[str] = []
        if item.screenshot:
            refs.append(item.screenshot)

        screenshot_path = item.data.get("screenshot_path")
        if isinstance(screenshot_path, str) and screenshot_path:
            refs.append(screenshot_path)

        screenshot_paths = item.data.get("screenshot_paths")
        if isinstance(screenshot_paths, list):
            refs.extend(path for path in screenshot_paths if isinstance(path, str) and path)

        unique_refs = list(dict.fromkeys(refs))
        if not unique_refs:
            return ""

        links = ", ".join(f"[{Path(ref).name}]({ref})" for ref in unique_refs[:5])
        suffix = "..." if len(unique_refs) > 5 else ""
        return f" Screenshots: {links}{suffix}."
