from __future__ import annotations

from pathlib import Path
from typing import Any

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
        issues = [
            finding
            for analysis in analyses
            for finding in analysis.findings
            if getattr(finding, "issue_type", "product") != "positive"
        ]
        lines: list[str] = []
        lines.append(f"# {labels['title']}")
        lines.append("")
        lines.append(f"**{labels['research_goal']}:** {plan.research_goal}")
        lines.append("")
        lines.extend(self._render_pm_summary(labels, results, issues, evidence))
        lines.append("")
        lines.append(f"## {labels['issue_board']}")
        lines.extend(self._render_issue_group(labels, issues, "product"))
        lines.extend(self._render_issue_group(labels, issues, "coverage"))
        lines.extend(self._render_issue_group(labels, issues, "system_reliability"))
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
                f"{self._cell(result.product)} | {self._cell(result.scenario_title)} | {self._status(result.status, language)} | "
                f"{result.metrics.get('completion_score', 0)} | "
                f"{result.metrics.get('friction_count', 0)} | "
                f"{result.metrics.get('blocker_count', 0)} |"
            )
        lines.append("")
        lines.append(f"## {labels['checklist']}")
        if plan.checklist:
            lines.append(f"| {labels['check']} | {labels['status']} | {labels['severity']} | {labels['notes']} |")
            lines.append("| --- | --- | --- | --- |")
            for item in plan.checklist:
                lines.append(
                    f"| {self._cell(item.title)} | {self._cell(item.status)} | "
                    f"{self._severity(item.severity, language)} | {self._cell(item.notes or labels['not_yet_scored'])} |"
                )
        else:
            lines.append(f"- {labels['no_checklist']}")
        lines.append("")
        lines.append(f"## {labels['product_summaries']}")
        for analysis in analyses:
            lines.append(f"### {analysis.product}")
            lines.append("")
            lines.append(analysis.summary)
            lines.append("")
        lines.append(f"## {labels['competitive_insights']}")
        if insights:
            for insight in insights:
                lines.append(
                    f"- **{self._cell(insight.theme)}:** {insight.claim} "
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

    def _render_pm_summary(
        self,
        labels: dict[str, str],
        results: list[WalkthroughResult],
        issues: list[Any],
        evidence: list[EvidenceItem],
    ) -> list[str]:
        product_issues = [issue for issue in issues if getattr(issue, "issue_type", "product") == "product"]
        coverage_gaps = [issue for issue in issues if getattr(issue, "issue_type", "") == "coverage"]
        reliability = [issue for issue in issues if getattr(issue, "issue_type", "") == "system_reliability"]
        p0_p1 = [issue for issue in issues if getattr(issue, "priority", "") in {"P0", "P1"}]
        completed = sum(1 for result in results if result.status == "completed")
        screenshot_count = sum(1 for item in evidence if item.screenshot or item.data.get("screenshot_path") or item.data.get("screenshot_paths"))
        lines = [f"## {labels['pm_summary']}"]
        lines.append(
            f"- {labels['scenario_completion']}: {completed}/{len(results)}"
        )
        lines.append(
            f"- {labels['issue_distribution']}: "
            f"{labels['product_issue']} {len(product_issues)} / "
            f"{labels['coverage_gap']} {len(coverage_gaps)} / "
            f"{labels['system_reliability']} {len(reliability)} / P0-P1 {len(p0_p1)}"
        )
        lines.append(f"- {labels['evidence_distribution']}: {len(evidence)} {labels['items']}, {screenshot_count} {labels['screenshots']}")
        return lines

    def _render_issue_group(self, labels: dict[str, str], issues: list[Any], issue_type: str) -> list[str]:
        group = [issue for issue in issues if getattr(issue, "issue_type", "product") == issue_type]
        heading = {
            "product": labels["product_issues"],
            "coverage": labels["coverage_gaps"],
            "system_reliability": labels["system_reliability_issues"],
        }[issue_type]
        lines = [f"### {heading}"]
        if not group:
            lines.append(f"- {labels['none']}")
            lines.append("")
            return lines

        group.sort(key=lambda item: (self._priority_rank(getattr(item, "priority", "P3")), -float(getattr(item, "confidence", 0))))
        lines.append(
            f"| {labels['priority']} | {labels['severity']} | {labels['theme']} | "
            f"{labels['page']} | {labels['issue']} | {labels['evidence']} | {labels['recommendation']} |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for issue in group:
            evidence_links = ", ".join(getattr(issue, "evidence_ids", []) or []) or labels["none"]
            page = getattr(issue, "page", "") or labels["unknown_page"]
            lines.append(
                "| "
                f"{self._cell(getattr(issue, 'priority', 'P2'))} | "
                f"{self._severity(getattr(issue, 'severity', 'medium'), labels['language'])} | "
                f"{self._theme(getattr(issue, 'theme', ''), labels['language'])} | "
                f"{self._cell(page)} | "
                f"{self._cell(getattr(issue, 'claim', ''))} | "
                f"`{self._cell(evidence_links)}` | "
                f"{self._cell(getattr(issue, 'recommendation', ''))} |"
            )
        lines.append("")
        high_priority = [issue for issue in group if getattr(issue, "priority", "") in {"P0", "P1"}]
        if high_priority:
            lines.append(f"#### {labels['high_priority_details']}")
            for issue in high_priority:
                lines.append(f"- **{getattr(issue, 'priority', 'P1')} / {self._theme(getattr(issue, 'theme', ''), labels['language'])}:** {getattr(issue, 'claim', '')}")
                if getattr(issue, "current_behavior", ""):
                    lines.append(f"  - {labels['current_behavior']}: {getattr(issue, 'current_behavior')}")
                if getattr(issue, "expected_behavior", ""):
                    lines.append(f"  - {labels['expected_behavior']}: {getattr(issue, 'expected_behavior')}")
                repro = getattr(issue, "repro_steps", []) or []
                if repro:
                    lines.append(f"  - {labels['repro_steps']}: {'; '.join(repro[:5])}")
                criteria = getattr(issue, "acceptance_criteria", []) or []
                if criteria:
                    lines.append(f"  - {labels['acceptance_criteria']}: {'; '.join(criteria[:3])}")
            lines.append("")
        return lines

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
                "language": "zh",
                "title": "产品走查问题报告",
                "research_goal": "调研目标",
                "pm_summary": "PM 走查汇总",
                "scenario_completion": "场景完成",
                "issue_distribution": "问题分布",
                "evidence_distribution": "证据分布",
                "items": "条证据",
                "screenshots": "张截图",
                "issue_board": "结构化问题板",
                "product_issues": "产品问题",
                "coverage_gaps": "覆盖缺口",
                "system_reliability_issues": "走查可靠性限制",
                "product_issue": "产品问题",
                "coverage_gap": "覆盖缺口",
                "system_reliability": "可靠性限制",
                "priority": "优先级",
                "severity": "严重度",
                "theme": "主题",
                "page": "影响页面",
                "issue": "问题",
                "evidence": "证据",
                "recommendation": "建议",
                "unknown_page": "未定位页面",
                "high_priority_details": "高优先级问题详情",
                "current_behavior": "当前行为",
                "expected_behavior": "预期行为",
                "repro_steps": "复现步骤",
                "acceptance_criteria": "验收标准",
                "scenario_coverage": "场景覆盖",
                "product": "产品",
                "scenario": "场景",
                "status": "状态",
                "completion": "完成度",
                "friction": "摩擦点",
                "blockers": "阻塞点",
                "checklist": "检查清单",
                "check": "检查项",
                "notes": "备注",
                "not_yet_scored": "尚未由检测器打分",
                "no_checklist": "未配置检查清单。",
                "product_summaries": "产品摘要",
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
            "language": "en",
            "title": "Product Walkthrough Issue Report",
            "research_goal": "Research goal",
            "pm_summary": "PM Review Summary",
            "scenario_completion": "Scenario completion",
            "issue_distribution": "Issue distribution",
            "evidence_distribution": "Evidence distribution",
            "items": "items",
            "screenshots": "screenshots",
            "issue_board": "Structured Issue Board",
            "product_issues": "Product Issues",
            "coverage_gaps": "Coverage Gaps",
            "system_reliability_issues": "Walkthrough Reliability Limits",
            "product_issue": "product issues",
            "coverage_gap": "coverage gaps",
            "system_reliability": "reliability limits",
            "priority": "Priority",
            "severity": "Severity",
            "theme": "Theme",
            "page": "Impact page",
            "issue": "Issue",
            "evidence": "Evidence",
            "recommendation": "Recommendation",
            "unknown_page": "unknown page",
            "high_priority_details": "High Priority Details",
            "current_behavior": "Current behavior",
            "expected_behavior": "Expected behavior",
            "repro_steps": "Repro steps",
            "acceptance_criteria": "Acceptance criteria",
            "scenario_coverage": "Scenario Coverage",
            "product": "Product",
            "scenario": "Scenario",
            "status": "Status",
            "completion": "Completion",
            "friction": "Friction",
            "blockers": "Blockers",
            "checklist": "Checklist",
            "check": "Check",
            "notes": "Notes",
            "not_yet_scored": "not yet scored by detectors",
            "no_checklist": "No checklist was configured.",
            "product_summaries": "Product Summaries",
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
            return str(value).upper()
        return {
            "high": "高",
            "medium": "中",
            "low": "低",
            "info": "信息",
        }.get(str(value).lower(), value)

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
            "Evidence collection reliability": "证据采集可靠性",
            "Page runtime errors": "页面运行时错误",
            "High-risk coverage gap": "高风险覆盖缺口",
        }.get(value, value)

    def _priority_rank(self, value: str) -> int:
        return {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(str(value).upper(), 9)

    def _cell(self, value: Any) -> str:
        text = " ".join(str(value or "").split())
        return text.replace("|", "\\|")
