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
    normalize_report_language,
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
        language: str = "en",
    ) -> str:
        language = normalize_report_language(language)
        labels = self._labels(language)
        lines: list[str] = []
        lines.append(f"# {labels['title']}")
        lines.append("")
        lines.append(f"**{labels['research_goal']}:** {plan.research_goal}")
        lines.append("")
        lines.append(f"## {labels['scope']}")
        for product in plan.products:
            lines.append(f"- {product.name} ({self._product_kind(product.kind, language)}): {product.url}")
        lines.append("")
        lines.append(f"## {labels['scenario_coverage']}")
        lines.append(
            f"| {labels['product']} | {labels['scenario']} | {labels['status']} | "
            f"{labels['completion']} | {labels['friction']} | {labels['blockers']} |"
        )
        lines.append("| --- | --- | --- | ---: | ---: | ---: |")
        for result in results:
            lines.append(
                "| "
                f"{result.product} | {result.scenario_title} | {self._status(result.status, language)} | "
                f"{result.metrics.get('completion_score', 0)} | "
                f"{result.metrics.get('friction_count', 0)} | "
                f"{result.metrics.get('blocker_count', 0)} |"
            )
        lines.append("")
        lines.append(f"## {labels['product_findings']}")
        for analysis in analyses:
            lines.append(f"### {analysis.product}")
            lines.append("")
            lines.append(analysis.summary)
            lines.append("")
            for finding in analysis.findings:
                evidence_links = ", ".join(finding.evidence_ids) or labels["none"]
                lines.append(
                    f"- **{self._severity(finding.severity, language)} / "
                    f"{self._theme(finding.theme, language)}:** "
                    f"{finding.claim} {labels['evidence']}: `{evidence_links}`. "
                    f"{labels['recommendation']}: {finding.recommendation}"
                )
            lines.append("")
        lines.append(f"## {labels['competitive_insights']}")
        if insights:
            for insight in insights:
                lines.append(
                    f"- **{insight.theme}:** {insight.claim} "
                    f"{labels['products']}: {', '.join(insight.products)}. "
                    f"{labels['evidence']}: `{', '.join(insight.evidence_ids) or labels['none']}`. "
                    f"{labels['recommendation']}: {insight.recommendation}"
                )
        else:
            lines.append(f"- {labels['no_competitive_insight']}")
        lines.append("")
        lines.append(f"## {labels['reviewer_notes']}")
        for note in review_notes:
            lines.append(f"- **{self._severity(note.severity, language)}** `{note.target}`: {note.message}")
        lines.append("")
        lines.append(f"## {labels['evidence_appendix']}")
        for item in evidence:
            screenshot_note = self._screenshot_note(item, language)
            lines.append(
                f"- `{item.id}` [{item.product}/{item.scenario_id}] "
                f"{item.title}: {item.summary}{screenshot_note}"
            )
        lines.append("")
        lines.append(f"## {labels['scenario_definitions']}")
        for scenario in scenarios:
            lines.append(f"### {scenario.title}")
            lines.append(f"- {labels['goal']}: {scenario.goal}")
            lines.append(f"- {labels['persona']}: {scenario.persona}")
            lines.append(f"- {labels['success_criteria']}: {'; '.join(scenario.success_criteria)}")
            lines.append("")
        return "\n".join(lines)

    def write(self, path: str | Path, markdown: str) -> Path:
        report_path = Path(path)
        report_path.write_text(markdown, encoding="utf-8")
        return report_path

    def _screenshot_note(self, item: EvidenceItem, language: str) -> str:
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
        label = "截图" if language == "zh" else "Screenshots"
        return f" {label}: {links}{suffix}."

    def _labels(self, language: str) -> dict[str, str]:
        if language == "zh":
            return {
                "title": "产品走查调研报告",
                "research_goal": "调研目标",
                "scope": "调研范围",
                "scenario_coverage": "场景覆盖",
                "product": "产品",
                "scenario": "场景",
                "status": "状态",
                "completion": "完成度",
                "friction": "摩擦点",
                "blockers": "阻塞点",
                "product_findings": "产品发现",
                "evidence": "证据",
                "recommendation": "建议",
                "competitive_insights": "竞品洞察",
                "products": "产品",
                "no_competitive_insight": "未生成跨产品洞察。可以增加更多产品或场景。",
                "reviewer_notes": "复核备注",
                "evidence_appendix": "证据附录",
                "scenario_definitions": "场景定义",
                "goal": "目标",
                "persona": "用户画像",
                "success_criteria": "成功标准",
                "none": "无",
            }
        return {
            "title": "Product Walkthrough Research Report",
            "research_goal": "Research goal",
            "scope": "Scope",
            "scenario_coverage": "Scenario Coverage",
            "product": "Product",
            "scenario": "Scenario",
            "status": "Status",
            "completion": "Completion",
            "friction": "Friction",
            "blockers": "Blockers",
            "product_findings": "Product Findings",
            "evidence": "Evidence",
            "recommendation": "Recommendation",
            "competitive_insights": "Competitive Insights",
            "products": "Products",
            "no_competitive_insight": "No cross-product insight was generated. Add more products or scenarios.",
            "reviewer_notes": "Reviewer Notes",
            "evidence_appendix": "Evidence Appendix",
            "scenario_definitions": "Scenario Definitions",
            "goal": "Goal",
            "persona": "Persona",
            "success_criteria": "Success criteria",
            "none": "none",
        }

    def _product_kind(self, value: str, language: str) -> str:
        if language != "zh":
            return value
        return {
            "owned": "自家产品",
            "competitor": "竞品",
        }.get(value, value)

    def _status(self, value: str, language: str) -> str:
        if language != "zh":
            return value
        return {
            "completed": "已完成",
            "blocked": "受阻",
            "friction": "有摩擦",
            "passed": "通过",
        }.get(value, value)

    def _severity(self, value: str, language: str) -> str:
        if language != "zh":
            return value.upper()
        return {
            "high": "高",
            "medium": "中",
            "low": "低",
            "info": "信息",
        }.get(value.lower(), value)

    def _theme(self, value: str, language: str) -> str:
        if language != "zh":
            return value
        return {
            "Secret handling/admin safety": "敏感信息与管理安全",
            "Permission and destructive controls": "权限与高风险操作控制",
            "Navigation and loading feedback": "导航与加载反馈",
            "Empty-state guidance": "空状态引导",
            "External-link clarity": "外部链接清晰度",
            "Completion blocker": "完成阻塞点",
            "Experience friction": "体验摩擦点",
            "Baseline pass": "基线通过",
        }.get(value, value)
