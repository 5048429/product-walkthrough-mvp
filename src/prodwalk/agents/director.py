from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..models import ResearchPlan, Scenario, WalkthroughResult, to_jsonable, utc_now
from .analyst import CompetitiveAnalyst, ProductAnalyst
from .evaluator import Evaluator
from .evidence import EvidenceExtractor
from .planner import ScenarioPlanner
from .report import MarkdownReportWriter
from .reviewer import Reviewer
from .walker import BrowserWalker


class ResearchDirector:
    def __init__(self, walker: BrowserWalker, concurrency: int = 3) -> None:
        self.walker = walker
        self.concurrency = max(1, concurrency)
        self.planner = ScenarioPlanner()
        self.evidence_extractor = EvidenceExtractor()
        self.product_analyst = ProductAnalyst()
        self.competitive_analyst = CompetitiveAnalyst()
        self.reviewer = Reviewer()
        self.report_writer = MarkdownReportWriter()
        self.evaluator = Evaluator()

    async def run(self, plan: ResearchPlan, run_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(run_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        scenarios = self.planner.plan(plan)
        results = await self._run_walkthroughs(plan, scenarios)
        evidence = self.evidence_extractor.collect(results)
        analyses = self.product_analyst.analyze(results)
        insights = self.competitive_analyst.compare(results, evidence)
        review_notes = self.reviewer.review(results, analyses, insights, evidence)
        evaluation = self.evaluator.evaluate(plan, results, analyses)
        markdown = self.report_writer.render(
            plan=plan,
            scenarios=scenarios,
            results=results,
            analyses=analyses,
            insights=insights,
            review_notes=review_notes,
            evidence=evidence,
        )

        evidence_path = output_dir / "evidence.json"
        report_path = output_dir / "report.md"
        evaluation_path = output_dir / "evaluation.json"

        payload = {
            "created_at": utc_now(),
            "plan": to_jsonable(plan),
            "scenarios": to_jsonable(scenarios),
            "results": to_jsonable(results),
            "evidence": to_jsonable(evidence),
            "analyses": to_jsonable(analyses),
            "competitive_insights": to_jsonable(insights),
            "review_notes": to_jsonable(review_notes),
        }
        evidence_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        report_path.write_text(markdown, encoding="utf-8")
        evaluation_path.write_text(
            json.dumps(to_jsonable(evaluation), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return {
            "run_dir": output_dir,
            "evidence": evidence_path,
            "report": report_path,
            "evaluation": evaluation_path,
        }

    async def _run_walkthroughs(
        self,
        plan: ResearchPlan,
        scenarios: list[Scenario],
    ) -> list[WalkthroughResult]:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def run_one(product_index: int, scenario_index: int) -> tuple[int, int, WalkthroughResult]:
            product = plan.products[product_index]
            scenario = scenarios[scenario_index]
            async with semaphore:
                result = await self.walker.walk(product, scenario)
            return product_index, scenario_index, result

        tasks = [
            run_one(product_index, scenario_index)
            for product_index in range(len(plan.products))
            for scenario_index in range(len(scenarios))
        ]
        raw_results = await asyncio.gather(*tasks)
        raw_results.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in raw_results]

