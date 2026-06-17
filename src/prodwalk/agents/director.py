from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..events import RunEvent, RunEventCallback, dispatch_run_event
from ..models import ResearchPlan, Scenario, WalkthroughResult, normalize_report_language, to_jsonable, utc_now
from .analyst import CompetitiveAnalyst, ProductAnalyst
from .evaluator import Evaluator
from .evidence import EvidenceExtractor
from .planner import ScenarioPlanner
from .report import MarkdownReportWriter
from .reviewer import Reviewer
from .walker import BrowserWalker


class ResearchDirector:
    def __init__(
        self,
        walker: BrowserWalker,
        concurrency: int = 3,
        report_language: str | None = None,
        event_sink: Any | None = None,
        event_callback: RunEventCallback | None = None,
    ) -> None:
        self.walker = walker
        self.concurrency = max(1, concurrency)
        self.report_language = normalize_report_language(report_language) if report_language else None
        self.event_sink = event_sink
        self.event_callback = event_callback
        self._active_run_id: str | None = None
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
        report_language = self.report_language or normalize_report_language(plan.report_language)
        previous_run_id = self._active_run_id
        self._active_run_id = self._run_id_from_dir(output_dir)

        try:
            await self._emit_event(
                "run_started",
                agent="ResearchDirector",
                status="running",
                message="Research run started",
                data={
                    "product_count": len(plan.products),
                    "configured_scenario_count": len(plan.scenarios),
                    "concurrency": self.concurrency,
                    "report_language": report_language,
                },
            )
            await self._emit_agent_started(
                "ResearchDirector",
                data={
                    "run_dir": str(output_dir),
                    "product_count": len(plan.products),
                    "configured_scenario_count": len(plan.scenarios),
                },
            )

            await self._emit_agent_started("ScenarioPlanner")
            scenarios = self.planner.plan(plan)
            await self._emit_agent_finished(
                "ScenarioPlanner",
                data={"scenario_count": len(scenarios)},
            )

            results = await self._run_walkthroughs(plan, scenarios)

            await self._emit_agent_started("EvidenceExtractor")
            archived_screenshots = self.evidence_extractor.archive_screenshots(results, output_dir)
            evidence = self.evidence_extractor.collect(results)
            await self._emit_agent_finished(
                "EvidenceExtractor",
                data={
                    "evidence_count": len(evidence),
                    "archived_screenshot_count": len(archived_screenshots),
                },
            )

            await self._emit_agent_started("ProductAnalyst")
            analyses = self.product_analyst.analyze(results, language=report_language)
            await self._emit_agent_finished(
                "ProductAnalyst",
                data={"analysis_count": len(analyses)},
            )

            await self._emit_agent_started("CompetitiveAnalyst")
            insights = self.competitive_analyst.compare(results, evidence, language=report_language)
            await self._emit_agent_finished(
                "CompetitiveAnalyst",
                data={"insight_count": len(insights)},
            )

            await self._emit_agent_started("Reviewer")
            review_notes = self.reviewer.review(results, analyses, insights, evidence, language=report_language)
            await self._emit_agent_finished(
                "Reviewer",
                data={"review_note_count": len(review_notes)},
            )

            await self._emit_agent_started("Evaluator")
            evaluation = self.evaluator.evaluate(plan, results, analyses)
            await self._emit_agent_finished(
                "Evaluator",
                data={
                    "overall_score": evaluation.overall_score,
                    "score_count": len(evaluation.scores),
                },
            )

            await self._emit_agent_started("MarkdownReportWriter")
            markdown = self.report_writer.render(
                plan=plan,
                scenarios=scenarios,
                results=results,
                analyses=analyses,
                insights=insights,
                review_notes=review_notes,
                evidence=evidence,
                language=report_language,
            )
            await self._emit_agent_finished(
                "MarkdownReportWriter",
                data={"character_count": len(markdown), "language": report_language},
            )

            evidence_path = output_dir / "evidence.json"
            report_path = output_dir / "report.md"
            evaluation_path = output_dir / "evaluation.json"

            payload = {
                "created_at": utc_now(),
                "report_language": report_language,
                "plan": to_jsonable(plan),
                "scenarios": to_jsonable(scenarios),
                "results": to_jsonable(results),
                "evidence": to_jsonable(evidence),
                "analyses": to_jsonable(analyses),
                "competitive_insights": to_jsonable(insights),
                "review_notes": to_jsonable(review_notes),
            }
            evidence_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            await self._emit_artifact_written("evidence_json", evidence_path)

            report_path.write_text(markdown, encoding="utf-8")
            await self._emit_artifact_written("report_markdown", report_path)

            evaluation_path.write_text(
                json.dumps(to_jsonable(evaluation), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            await self._emit_artifact_written("evaluation_json", evaluation_path)

            await self._emit_agent_finished(
                "ResearchDirector",
                data={
                    "artifact_count": 3,
                    "result_count": len(results),
                    "evidence_count": len(evidence),
                },
            )
            await self._emit_event(
                "run_completed",
                agent="ResearchDirector",
                status="succeeded",
                message="Research run completed",
                data={
                    "result_count": len(results),
                    "artifact_count": 3,
                    "overall_score": evaluation.overall_score,
                },
            )

            return {
                "run_dir": output_dir,
                "evidence": evidence_path,
                "report": report_path,
                "evaluation": evaluation_path,
            }
        except Exception as exc:
            with suppress(Exception):
                await self._emit_event(
                    "run_failed",
                    agent="ResearchDirector",
                    status="failed",
                    message=f"Research run failed: {exc}",
                    data={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            raise
        finally:
            self._active_run_id = previous_run_id

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
                await self._emit_agent_started(
                    "BrowserWalker",
                    product=product.name,
                    scenario_id=scenario.id,
                    data={
                        "product_kind": product.kind,
                        "scenario_title": scenario.title,
                        "step_count": len(scenario.steps),
                    },
                )
                result = await self.walker.walk(product, scenario)
                if result.status == "blocked":
                    await self._emit_event(
                        "agent_blocked",
                        agent="BrowserWalker",
                        status="blocked",
                        message=f"BrowserWalker blocked for {product.name} / {scenario.id}",
                        product=product.name,
                        scenario_id=scenario.id,
                        data=self._walkthrough_event_data(result),
                    )
                await self._emit_agent_finished(
                    "BrowserWalker",
                    status="blocked" if result.status == "blocked" else "succeeded",
                    product=product.name,
                    scenario_id=scenario.id,
                    data=self._walkthrough_event_data(result),
                )
            return product_index, scenario_index, result

        tasks = [
            run_one(product_index, scenario_index)
            for product_index in range(len(plan.products))
            for scenario_index in range(len(scenarios))
        ]
        raw_results = await asyncio.gather(*tasks)
        raw_results.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in raw_results]

    async def _emit_agent_started(
        self,
        agent: str,
        *,
        product: str | None = None,
        scenario_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        await self._emit_event(
            "agent_started",
            agent=agent,
            status="running",
            message=f"{agent} started",
            product=product,
            scenario_id=scenario_id,
            data=data,
        )

    async def _emit_agent_finished(
        self,
        agent: str,
        *,
        status: str = "succeeded",
        product: str | None = None,
        scenario_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        await self._emit_event(
            "agent_finished",
            agent=agent,
            status=status,
            message=f"{agent} finished",
            product=product,
            scenario_id=scenario_id,
            data=data,
        )

    async def _emit_artifact_written(self, artifact_type: str, artifact_path: Path) -> None:
        await self._emit_event(
            "artifact_written",
            agent="ResearchDirector",
            status="finalizing",
            message=f"Artifact written: {artifact_path.name}",
            artifact_type=artifact_type,
            artifact_path=str(artifact_path),
            data={
                "filename": artifact_path.name,
                "size_bytes": artifact_path.stat().st_size if artifact_path.exists() else None,
            },
        )

    async def _emit_event(
        self,
        event_type: str,
        *,
        agent: str | None = None,
        status: str | None = None,
        message: str = "",
        product: str | None = None,
        scenario_id: str | None = None,
        artifact_type: str | None = None,
        artifact_path: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        if self.event_sink is None and self.event_callback is None:
            return

        event = RunEvent(
            run_id=self._active_run_id or "run",
            event_type=event_type,
            agent=agent,
            status=status,
            message=message,
            product=product,
            scenario_id=scenario_id,
            artifact_type=artifact_type,
            artifact_path=artifact_path,
            data=data or {},
        )
        if self.event_sink is not None:
            await dispatch_run_event(self.event_sink, event)
        if self.event_callback is not None and self.event_callback is not self.event_sink:
            await dispatch_run_event(self.event_callback, event)

    def _run_id_from_dir(self, output_dir: Path) -> str:
        return output_dir.name or str(output_dir)

    def _walkthrough_event_data(self, result: WalkthroughResult) -> dict[str, Any]:
        return {
            "result_status": result.status,
            "scenario_title": result.scenario_title,
            "step_count": len(result.steps),
            "evidence_count": len(result.evidence),
            "metrics": to_jsonable(result.metrics),
            "errors": to_jsonable(result.errors),
        }
