from __future__ import annotations

from ..models import CompetitiveInsight, EvidenceItem, ProductAnalysis, ReviewNote, WalkthroughResult


class Reviewer:
    def review(
        self,
        results: list[WalkthroughResult],
        analyses: list[ProductAnalysis],
        insights: list[CompetitiveInsight],
        evidence: list[EvidenceItem],
    ) -> list[ReviewNote]:
        notes: list[ReviewNote] = []
        evidence_ids = {item.id for item in evidence}

        for result in results:
            if not result.evidence:
                notes.append(
                    ReviewNote(
                        severity="high",
                        target=f"{result.product}/{result.scenario_id}",
                        message="No evidence was captured for this walkthrough result.",
                    )
                )

        for analysis in analyses:
            for finding in analysis.findings:
                missing = [item for item in finding.evidence_ids if item not in evidence_ids]
                if missing:
                    notes.append(
                        ReviewNote(
                            severity="high",
                            target=finding.id,
                            message=f"Finding references missing evidence IDs: {', '.join(missing)}",
                        )
                    )
                if not finding.recommendation.strip():
                    notes.append(
                        ReviewNote(
                            severity="medium",
                            target=finding.id,
                            message="Finding has no actionable recommendation.",
                        )
                    )

        for insight in insights:
            if not insight.evidence_ids:
                notes.append(
                    ReviewNote(
                        severity="medium",
                        target=insight.theme,
                        message="Competitive insight has no evidence references.",
                    )
                )

        if not notes:
            notes.append(
                ReviewNote(
                    severity="info",
                    target="report",
                    message="All findings and insights are linked to captured evidence.",
                )
            )
        return notes

