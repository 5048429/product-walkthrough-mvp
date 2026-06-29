from __future__ import annotations

from ..models import (
    CompetitiveInsight,
    EvidenceItem,
    ProductAnalysis,
    ReviewNote,
    WalkthroughResult,
    normalize_report_language,
)


class Reviewer:
    def review(
        self,
        results: list[WalkthroughResult],
        analyses: list[ProductAnalysis],
        insights: list[CompetitiveInsight],
        evidence: list[EvidenceItem],
        language: str = "en",
    ) -> list[ReviewNote]:
        language = normalize_report_language(language)
        notes: list[ReviewNote] = []
        evidence_ids = {item.id for item in evidence}

        for result in results:
            if not result.evidence:
                notes.append(
                    ReviewNote(
                        severity="high",
                        target=f"{result.product}/{result.scenario_id}",
                        message=(
                            "该走查结果没有采集到证据。"
                            if language == "zh"
                            else "No evidence was captured for this walkthrough result."
                        ),
                    )
                )

        for analysis in analyses:
            for finding in analysis.findings:
                issue_type = getattr(finding, "issue_type", "product")
                if issue_type == "positive":
                    continue
                missing = [item for item in finding.evidence_ids if item not in evidence_ids]
                if missing:
                    notes.append(
                        ReviewNote(
                            severity="high",
                            target=finding.id,
                            message=(
                                f"该问题引用了不存在的证据 ID：{', '.join(missing)}"
                                if language == "zh"
                                else f"Issue references missing evidence IDs: {', '.join(missing)}"
                            ),
                        )
                    )
                if not finding.recommendation.strip():
                    notes.append(
                        ReviewNote(
                            severity="medium",
                            target=finding.id,
                            message=(
                                "该问题缺少可执行建议。"
                                if language == "zh"
                                else "Issue has no actionable recommendation."
                            ),
                        )
                    )
                if finding.priority in {"P0", "P1"} or finding.severity == "high":
                    if not finding.repro_steps:
                        notes.append(
                            ReviewNote(
                                severity="high",
                                target=finding.id,
                                message=(
                                    "高优先级问题缺少复现步骤。"
                                    if language == "zh"
                                    else "High-priority issue is missing repro steps."
                                ),
                            )
                        )
                    if not finding.acceptance_criteria:
                        notes.append(
                            ReviewNote(
                                severity="high",
                                target=finding.id,
                                message=(
                                    "高优先级问题缺少验收标准。"
                                    if language == "zh"
                                    else "High-priority issue is missing acceptance criteria."
                                ),
                            )
                        )
                if issue_type == "system_reliability":
                    notes.append(
                        ReviewNote(
                            severity="medium",
                            target=finding.id,
                            message=(
                                "该项已归类为走查可靠性限制，不应直接当作产品缺陷。"
                                if language == "zh"
                                else "This item is classified as a walkthrough reliability limit, not a direct product defect."
                            ),
                        )
                    )

        for insight in insights:
            if not insight.evidence_ids:
                notes.append(
                    ReviewNote(
                        severity="medium",
                        target=insight.theme,
                        message=(
                            "该竞品洞察没有关联证据。"
                            if language == "zh"
                            else "Competitive insight has no evidence references."
                        ),
                    )
                )

        if not notes:
            notes.append(
                ReviewNote(
                    severity="info",
                    target="report",
                    message=(
                        "所有问题和洞察都已关联到已采集证据。"
                        if language == "zh"
                        else "All issues and insights are linked to captured evidence."
                    ),
                )
            )
        return notes
