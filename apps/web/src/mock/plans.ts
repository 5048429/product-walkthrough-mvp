import type { PlanSummary } from "../types/contracts";

export const mockPlans: PlanSummary[] = [
  {
    id: "examples/smoke_plan.json",
    path: "examples/smoke_plan.json",
    title: "Smoke plan for Prodwalk mock run validation",
    product_count: 2,
    scenario_count: 3,
    report_language: "en",
  },
  {
    id: "examples/research_plan.json",
    path: "examples/research_plan.json",
    title: "Compare onboarding and first project creation experience",
    product_count: 3,
    scenario_count: 2,
    report_language: "en",
  },
  {
    id: "examples/clink_uat_plan.json",
    path: "examples/clink_uat_plan.json",
    title: "Clink UAT dashboard product walkthrough",
    product_count: 1,
    scenario_count: 4,
    report_language: "zh",
  },
];
