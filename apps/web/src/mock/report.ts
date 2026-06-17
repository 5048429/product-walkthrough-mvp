import type { ReportResponse } from "../types/contracts";
import { mockArtifacts } from "./artifacts";

export const mockReport: ReportResponse = {
  run_id: "run-20260616-163039-a33a65",
  language: "zh",
  markdown_artifact_id: "art_report_md",
  evaluation_artifact_id: "art_evaluation_json",
  generated_at: "2026-06-16T08:31:15Z",
  artifacts: mockArtifacts,
  evaluation: {
    overall_score: 0.92,
    scores: {
      task_completion_rate: 0.83,
      evidence_coverage_rate: 1,
      finding_grounding_rate: 0.9,
      recommendation_actionability_rate: 0.95,
      evidence_items: 2,
      findings: 3,
    },
    notes: [
      "Mock data covers report, evidence, evaluation, and event preview paths.",
      "Screenshot artifacts are intentionally absent so the missing-state UI is visible.",
    ],
  },
  markdown: `# Product Walkthrough Research Report

## Summary

The mock run shows an owned-product onboarding path with a clear first-run checklist and a competitor project flow that adds friction before dashboard arrival.

## Key Findings

- Owned onboarding gives users an immediate setup checklist and keeps progress visible. Evidence: ev-our-product-onboarding-1.
- Competitor project creation requires a template decision before the user can inspect the workspace. Evidence: ev-competitor-project-1.
- Checkout recovery is currently blocked by manual verification. Evidence: ev-competitor-checkout-blocked.
- Legacy settings evidence is partial because screenshot archival failed. Evidence: ev-legacy-settings-failed.

## Recommendations

1. Keep the checklist visible until the user completes the first dashboard action.
2. Surface project templates after basic workspace creation when possible.
3. Preserve missing screenshot states in the UI so partial evidence remains reviewable.
`,
};
