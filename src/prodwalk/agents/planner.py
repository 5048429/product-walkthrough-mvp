from __future__ import annotations

from ..models import ResearchPlan, Scenario


class ScenarioPlanner:
    """Normalizes configured journeys and creates defaults when none are provided."""

    def plan(self, plan: ResearchPlan) -> list[Scenario]:
        if plan.scenarios:
            return [self._normalize(scenario) for scenario in plan.scenarios]
        return self._default_scenarios()

    def _normalize(self, scenario: Scenario) -> Scenario:
        steps = scenario.steps or [
            "Open the product entry URL",
            "Identify the main path for this goal",
            "Attempt the goal using visible UI affordances",
            "Record the completion state and any blockers",
        ]
        observation_points = scenario.observation_points or [
            "Entry point clarity",
            "Copy and guidance",
            "Interaction friction",
            "Success or failure feedback",
        ]
        success_criteria = scenario.success_criteria or [
            "The user can understand the next action",
            "The user can complete the stated goal",
        ]
        return Scenario(
            id=scenario.id,
            title=scenario.title,
            persona=scenario.persona,
            goal=scenario.goal,
            steps=steps,
            success_criteria=success_criteria,
            observation_points=observation_points,
            risk_level=scenario.risk_level,
        )

    def _default_scenarios(self) -> list[Scenario]:
        return [
            Scenario(
                id="onboarding",
                title="First-time onboarding",
                persona="New evaluator",
                goal="Understand the product value and reach the first meaningful state.",
                steps=[
                    "Open the product entry URL",
                    "Identify primary value proposition and call to action",
                    "Start signup or login if safe credentials are available",
                    "Observe the first in-product screen",
                    "Find the next recommended action",
                ],
                success_criteria=[
                    "Value proposition is visible",
                    "Entry path is clear",
                    "Next action is understandable",
                ],
                observation_points=[
                    "CTA clarity",
                    "Account entry friction",
                    "Guidance quality",
                    "Empty state quality",
                ],
            ),
            Scenario(
                id="core_action",
                title="Complete core action",
                persona="New active user",
                goal="Complete the most important first action in the product.",
                steps=[
                    "Locate the core action",
                    "Start the action flow",
                    "Complete required inputs",
                    "Submit or save",
                    "Confirm the result is visible",
                ],
                success_criteria=[
                    "Core action is discoverable",
                    "Required inputs are clear",
                    "Completion is confirmed",
                ],
                observation_points=[
                    "Discoverability",
                    "Form complexity",
                    "Validation",
                    "Success feedback",
                ],
            ),
        ]

