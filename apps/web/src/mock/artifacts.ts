import type { Artifact } from "../types/contracts";

const runId = "run-20260616-163039-a33a65";

export const mockArtifacts: Artifact[] = [
  {
    id: "art_report_md",
    run_id: runId,
    type: "report_markdown",
    title: "report.md",
    path: "report.md",
    media_type: "text/markdown; charset=utf-8",
    size_bytes: 12842,
    created_at: "2026-06-16T08:31:15Z",
    metadata: {
      language: "zh",
    },
  },
  {
    id: "art_evaluation_json",
    run_id: runId,
    type: "evaluation_json",
    title: "evaluation.json",
    path: "evaluation.json",
    media_type: "application/json",
    size_bytes: 2416,
    created_at: "2026-06-16T08:31:15Z",
    metadata: {
      overall_score: 0.92,
    },
  },
  {
    id: "art_evidence_json",
    run_id: runId,
    type: "evidence_json",
    title: "evidence.json",
    path: "evidence.json",
    media_type: "application/json",
    size_bytes: 9480,
    created_at: "2026-06-16T08:31:12Z",
    metadata: {
      evidence_items: 4,
    },
  },
  {
    id: "art_walkthrough_map",
    run_id: runId,
    type: "walkthrough_map",
    title: "walkthrough_map.json",
    path: "walkthrough_map.json",
    media_type: "application/json",
    size_bytes: 18340,
    created_at: "2026-06-16T08:31:16Z",
    metadata: {
      node_count: 6,
      edge_count: 5,
    },
  },
  {
    id: "art_screenshot_onboarding_step_1",
    run_id: runId,
    type: "screenshot",
    title: "onboarding-step-1.png",
    path: "screenshots/onboarding-step-1.png",
    media_type: "image/png",
    size_bytes: 0,
    created_at: "2026-06-16T08:30:57Z",
    metadata: {
      mock_placeholder: true,
      product: "Our Product",
      scenario_id: "onboarding",
    },
  },
];
