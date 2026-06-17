import { StatusBadge } from "../StatusBadge";
import type { AgentExecution, AgentType, ConsoleStatus } from "../../types/contracts";

interface StageDefinition {
  label: string;
  types: AgentType[];
}

interface AgentTimelineProps {
  agents: AgentExecution[];
  consoleStatus: ConsoleStatus;
}

const stages: StageDefinition[] = [
  { label: "Director", types: ["director"] },
  { label: "Planner", types: ["planner"] },
  { label: "Walker", types: ["walker", "auth_session"] },
  { label: "Evidence", types: ["evidence_extractor"] },
  { label: "Analyst", types: ["product_analyst", "competitive_analyst"] },
  { label: "Reviewer", types: ["reviewer"] },
  { label: "Reporter", types: ["report_writer"] },
  { label: "Evaluator", types: ["evaluator"] },
];

const statusTone: Record<ConsoleStatus, string> = {
  idle: "#627083",
  running: "#2458d3",
  done: "#1f8a5f",
  blocked: "#a56300",
  failed: "#ba2d2d",
};

function getStageStatus(stageAgents: AgentExecution[], consoleStatus: ConsoleStatus): ConsoleStatus {
  if (stageAgents.length === 0) {
    return consoleStatus === "idle" ? "idle" : "idle";
  }

  if (stageAgents.some((agent) => agent.status === "failed")) {
    return "failed";
  }

  if (stageAgents.some((agent) => agent.status === "running")) {
    return "running";
  }

  if (stageAgents.some((agent) => agent.status === "waiting")) {
    return consoleStatus === "blocked" ? "blocked" : "running";
  }

  if (stageAgents.every((agent) => agent.status === "succeeded" || agent.status === "skipped")) {
    return "done";
  }

  return "idle";
}

export function AgentTimeline({ agents, consoleStatus }: AgentTimelineProps) {
  return (
    <div className="timeline" aria-label="Agent stage timeline">
      {stages.map((stage) => {
        const stageAgents = agents.filter((agent) => stage.types.includes(agent.type));
        const stageStatus = getStageStatus(stageAgents, consoleStatus);

        return (
          <div key={stage.label} className="timeline-node">
            <span style={{ background: statusTone[stageStatus] }} />
            <strong>{stage.label}</strong>
            <StatusBadge status={stageStatus} />
          </div>
        );
      })}
    </div>
  );
}
