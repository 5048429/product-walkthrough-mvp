import type { AgentExecution, AgentStatus, ConsoleStatus } from "../types/contracts";

const runId = "run-20260616-163039-a33a65";

export const mockAgents: AgentExecution[] = [
  {
    id: "agent_director",
    run_id: runId,
    type: "director",
    status: "succeeded",
    label: "ResearchDirector",
    product: null,
    scenario_id: null,
    current_step: null,
    started_at: "2026-06-16T08:30:40Z",
    updated_at: "2026-06-16T08:30:42Z",
    completed_at: "2026-06-16T08:30:42Z",
    metrics: { step_count: null, completion_score: 1 },
    error: null,
  },
  {
    id: "agent_planner",
    run_id: runId,
    type: "planner",
    status: "succeeded",
    label: "Plan Loader",
    product: null,
    scenario_id: null,
    current_step: null,
    started_at: "2026-06-16T08:30:41Z",
    updated_at: "2026-06-16T08:30:43Z",
    completed_at: "2026-06-16T08:30:43Z",
    metrics: { product_count: 3, scenario_count: 2 },
    error: null,
  },
  {
    id: "agent_walker_our-product_onboarding",
    run_id: runId,
    type: "walker",
    status: "running",
    label: "BrowserWalker: Our Product / onboarding",
    product: "Our Product",
    scenario_id: "onboarding",
    current_step: 4,
    started_at: "2026-06-16T08:30:44Z",
    updated_at: "2026-06-16T08:31:12Z",
    completed_at: null,
    metrics: { step_count: 5, completion_score: null },
    error: null,
  },
  {
    id: "agent_walker_competitor_project",
    run_id: runId,
    type: "walker",
    status: "waiting",
    label: "BrowserWalker: Competitor / first project",
    product: "Competitor",
    scenario_id: "first_project",
    current_step: 1,
    started_at: "2026-06-16T08:30:45Z",
    updated_at: "2026-06-16T08:31:00Z",
    completed_at: null,
    metrics: { step_count: 5, completion_score: null },
    error: "Waiting for available mock worker slot",
  },
  {
    id: "agent_evidence_extractor",
    run_id: runId,
    type: "evidence_extractor",
    status: "pending",
    label: "Evidence Extractor",
    product: null,
    scenario_id: null,
    current_step: null,
    started_at: null,
    updated_at: null,
    completed_at: null,
    metrics: { evidence_items: 2 },
    error: null,
  },
  {
    id: "agent_product_analyst",
    run_id: runId,
    type: "product_analyst",
    status: "pending",
    label: "Product Analyst",
    product: "Our Product",
    scenario_id: null,
    current_step: null,
    started_at: null,
    updated_at: null,
    completed_at: null,
    metrics: { findings: null },
    error: null,
  },
  {
    id: "agent_reviewer",
    run_id: runId,
    type: "reviewer",
    status: "pending",
    label: "Reviewer",
    product: null,
    scenario_id: null,
    current_step: null,
    started_at: null,
    updated_at: null,
    completed_at: null,
    metrics: { grounding_checks: null },
    error: null,
  },
  {
    id: "agent_report_writer",
    run_id: runId,
    type: "report_writer",
    status: "pending",
    label: "Report Writer",
    product: null,
    scenario_id: null,
    current_step: null,
    started_at: null,
    updated_at: null,
    completed_at: null,
    metrics: {},
    error: null,
  },
  {
    id: "agent_evaluator",
    run_id: runId,
    type: "evaluator",
    status: "pending",
    label: "Evaluation Scorer",
    product: null,
    scenario_id: null,
    current_step: null,
    started_at: null,
    updated_at: null,
    completed_at: null,
    metrics: {},
    error: null,
  },
];

function cloneAgent(agent: AgentExecution, status: AgentStatus, error: string | null = null): AgentExecution {
  const completed = status === "succeeded" || status === "skipped" || status === "canceled";
  const active = status === "running" || status === "waiting";

  return {
    ...agent,
    status,
    current_step: completed ? agent.current_step : agent.current_step,
    updated_at: active || completed ? agent.updated_at ?? "2026-06-16T08:31:16Z" : null,
    completed_at: completed ? agent.completed_at ?? "2026-06-16T08:31:16Z" : null,
    metrics: {
      ...agent.metrics,
      completion_score: completed ? 1 : agent.metrics.completion_score,
    },
    error,
  };
}

export function getMockAgentsForStatus(status: ConsoleStatus): AgentExecution[] {
  if (status === "idle") {
    return [];
  }

  if (status === "running") {
    return mockAgents;
  }

  if (status === "done") {
    return mockAgents.map((agent) => cloneAgent(agent, agent.status === "pending" ? "skipped" : "succeeded"));
  }

  if (status === "awaiting_verification") {
    return mockAgents.map((agent) => {
      if (agent.id === "agent_director" || agent.id === "agent_planner" || agent.id === "agent_walker_our-product_onboarding") {
        return cloneAgent(agent, "succeeded");
      }

      if (agent.id === "agent_walker_competitor_project") {
        return cloneAgent(agent, "waiting", "Manual verification required before the competitor dashboard can continue.");
      }

      return cloneAgent(agent, "pending");
    });
  }

  if (status === "blocked") {
    return mockAgents.map((agent) => {
      if (agent.id === "agent_director" || agent.id === "agent_planner") {
        return cloneAgent(agent, "succeeded");
      }

      if (agent.id === "agent_walker_our-product_onboarding") {
        return cloneAgent(agent, "waiting", "Environment precondition blocked this mock walkthrough.");
      }

      return cloneAgent(agent, "pending");
    });
  }

  return mockAgents.map((agent) => {
    if (agent.id === "agent_director") {
      return cloneAgent(agent, "succeeded");
    }

    if (agent.id === "agent_planner") {
      return cloneAgent(agent, "failed", "Plan parse error: missing scenarios array in invalid fixture.");
    }

    return cloneAgent(agent, "pending");
  });
}
