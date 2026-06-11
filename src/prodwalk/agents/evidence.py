from __future__ import annotations

from ..models import EvidenceItem, WalkthroughResult


class EvidenceExtractor:
    def collect(self, results: list[WalkthroughResult]) -> list[EvidenceItem]:
        seen: set[str] = set()
        collected: list[EvidenceItem] = []
        for result in results:
            for item in result.evidence:
                if item.id in seen:
                    continue
                seen.add(item.id)
                collected.append(item)
        return collected

    def by_id(self, evidence: list[EvidenceItem]) -> dict[str, EvidenceItem]:
        return {item.id: item for item in evidence}

