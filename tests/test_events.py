from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prodwalk.agents.director import ResearchDirector
from prodwalk.agents.walker import MockBrowserWalker
from prodwalk.events import RunEvent
from prodwalk.models import ProductTarget, ResearchPlan, Scenario


def sample_plan() -> ResearchPlan:
    return ResearchPlan(
        research_goal="Verify mock event instrumentation.",
        products=[ProductTarget(name="Example", url="https://example.test")],
        scenarios=[
            Scenario(
                id="smoke",
                title="Smoke walkthrough",
                persona="Product manager",
                goal="Confirm the mock pipeline can run end to end.",
                steps=["Open the entry page", "Confirm the main state"],
                success_criteria=["The main state is observable"],
                observation_points=["Clarity", "Completion"],
            )
        ],
    )


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)


class RunEventInstrumentationTest(unittest.IsolatedAsyncioTestCase):
    async def test_mock_run_emits_run_started_and_completed(self) -> None:
        sink = ListEventSink()
        with tempfile.TemporaryDirectory() as tmp:
            director = ResearchDirector(MockBrowserWalker(), concurrency=1, event_sink=sink)

            await director.run(sample_plan(), tmp)

        event_types = [event.event_type for event in sink.events]
        self.assertEqual(event_types[0], "run_started")
        self.assertEqual(event_types[-1], "run_completed")
        self.assertTrue(all(event.run_id for event in sink.events))
        self.assertTrue(all(event.event_id.startswith("evt_") for event in sink.events))

    async def test_mock_run_emits_started_and_finished_for_major_agents(self) -> None:
        sink = ListEventSink()
        plan = sample_plan()
        with tempfile.TemporaryDirectory() as tmp:
            director = ResearchDirector(MockBrowserWalker(), concurrency=1, event_sink=sink)

            await director.run(plan, tmp)

        expected_agents = {
            "ResearchDirector",
            "ScenarioPlanner",
            "BrowserWalker",
            "EvidenceExtractor",
            "ProductAnalyst",
            "CompetitiveAnalyst",
            "Reviewer",
            "MarkdownReportWriter",
            "Evaluator",
        }
        started_agents = {event.agent for event in sink.events if event.event_type == "agent_started"}
        finished_agents = {event.agent for event in sink.events if event.event_type == "agent_finished"}
        self.assertTrue(expected_agents.issubset(started_agents))
        self.assertTrue(expected_agents.issubset(finished_agents))

        walker_started = [
            event for event in sink.events if event.event_type == "agent_started" and event.agent == "BrowserWalker"
        ]
        walker_finished = [
            event for event in sink.events if event.event_type == "agent_finished" and event.agent == "BrowserWalker"
        ]
        expected_walkthroughs = len(plan.products) * len(plan.scenarios)
        self.assertEqual(len(walker_started), expected_walkthroughs)
        self.assertEqual(len(walker_finished), expected_walkthroughs)
        self.assertEqual(walker_started[0].product, "Example")
        self.assertEqual(walker_started[0].scenario_id, "smoke")
        self.assertEqual(walker_started[0].data["step_count"], 2)

    async def test_artifact_written_events_include_evidence_report_and_evaluation(self) -> None:
        sink = ListEventSink()
        with tempfile.TemporaryDirectory() as tmp:
            director = ResearchDirector(MockBrowserWalker(), concurrency=1, event_sink=sink)

            await director.run(sample_plan(), tmp)

            artifact_events = [event for event in sink.events if event.event_type == "artifact_written"]
            self.assertEqual(
                [event.artifact_type for event in artifact_events],
                ["evidence_json", "issues_json", "report_markdown", "evaluation_json"],
            )
            for event in artifact_events:
                self.assertIsNotNone(event.artifact_path)
                assert event.artifact_path is not None
                self.assertTrue(Path(event.artifact_path).exists())
                self.assertGreater(event.data["size_bytes"], 0)

    async def test_director_run_without_event_sink_still_generates_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            director = ResearchDirector(MockBrowserWalker(), concurrency=1)

            paths = await director.run(sample_plan(), tmp)

            self.assertTrue(paths["evidence"].exists())
            self.assertTrue(paths["report"].exists())
            self.assertTrue(paths["evaluation"].exists())


if __name__ == "__main__":
    unittest.main()
