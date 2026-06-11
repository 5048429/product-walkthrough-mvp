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
                message = (
                    "该走查结果没有采集到证据。"
                    if language == "zh"
                    else "No evidence was captured for this walkthrough result."
                )
                notes.append(
                    ReviewNote(
                        severity="high",
                        target=f"{result.product}/{result.scenario_id}",
                        message=message,
                    )
                )

        for analysis in analyses:
            for finding in analysis.findings:
                missing = [item for item in finding.evidence_ids if item not in evidence_ids]
                if missing:
                    message = (
                        f"该发现引用了不存在的证据 ID：{', '.join(missing)}"
                        if language == "zh"
                        else f"Finding references missing evidence IDs: {', '.join(missing)}"
                    )
                    notes.append(
                        ReviewNote(
                            severity="high",
                            target=finding.id,
                            message=message,
                        )
                    )
                if not finding.recommendation.strip():
                    message = (
                        "该发现缺少可执行建议。"
                        if language == "zh"
                        else "Finding has no actionable recommendation."
                    )
                    notes.append(
                        ReviewNote(
                            severity="medium",
                            target=finding.id,
                            message=message,
                        )
                    )

        for insight in insights:
            if not insight.evidence_ids:
                message = (
                    "该竞品洞察没有关联证据。"
                    if language == "zh"
                    else "Competitive insight has no evidence references."
                )
                notes.append(
                    ReviewNote(
                        severity="medium",
                        target=insight.theme,
                        message=message,
                    )
                )

        if not notes:
            message = (
                "所有发现和洞察都已经关联到已采集证据。"
                if language == "zh"
                else "All findings and insights are linked to captured evidence."
            )
            notes.append(
                ReviewNote(
                    severity="info",
                    target="report",
                    message=message,
                )
            )
        return notes
