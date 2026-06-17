import { StatusBadge } from "../StatusBadge";
import type { AgentExecution, ConsoleStatus } from "../../types/contracts";
import { AgentStatusCard } from "./AgentStatusCard";
import { AgentTimeline } from "./AgentTimeline";

interface AgentStatusPanelProps {
  agents: AgentExecution[];
  consoleStatus?: ConsoleStatus;
}

function inferConsoleStatus(agents: AgentExecution[]): ConsoleStatus {
  if (agents.length === 0) {
    return "idle";
  }

  if (agents.some((agent) => agent.status === "failed")) {
    return "failed";
  }

  if (agents.every((agent) => agent.status === "succeeded" || agent.status === "skipped" || agent.status === "canceled")) {
    return "done";
  }

  if (agents.some((agent) => agent.status === "running")) {
    return "running";
  }

  if (agents.some((agent) => agent.status === "waiting")) {
    return "blocked";
  }

  return "idle";
}

function getPanelSummary(status: ConsoleStatus, agents: AgentExecution[]): string {
  if (status === "idle") {
    return "No active agents.";
  }

  const activeCount = agents.filter((agent) => agent.status === "running" || agent.status === "waiting").length;

  switch (status) {
    case "running":
      return `${activeCount} active or waiting agent stages.`;
    case "awaiting_verification":
      return "A browser-use stage is waiting for manual verification acknowledgement.";
    case "done":
      return "All required agent stages completed or were skipped.";
    case "blocked":
      return "A waiting agent needs operator or environment action.";
    case "failed":
      return "A failed agent preserved its error and related events.";
    default:
      return "Agent status unavailable.";
  }
}

function sortAgents(agents: AgentExecution[]): AgentExecution[] {
  const priority = new Map([
    ["running", 0],
    ["waiting", 1],
    ["failed", 2],
    ["pending", 3],
    ["succeeded", 4],
    ["skipped", 5],
    ["canceled", 6],
  ]);

  return [...agents].sort((a, b) => (priority.get(a.status) ?? 10) - (priority.get(b.status) ?? 10));
}

export function AgentStatusPanel({ agents, consoleStatus }: AgentStatusPanelProps) {
  const displayStatus = consoleStatus ?? inferConsoleStatus(agents);
  const orderedAgents = sortAgents(agents);

  return (
    <section className="panel agent-panel" aria-labelledby="agent-status-title">
      <div className="panel-header">
        <div>
          <h2 id="agent-status-title">Agent Status</h2>
          <p>{getPanelSummary(displayStatus, agents)}</p>
        </div>
        <StatusBadge status={displayStatus} />
      </div>

      <AgentTimeline agents={agents} consoleStatus={displayStatus} />

      {agents.length === 0 ? (
        <div className="active-summary">
          <div className="section-title">Idle</div>
          <p className="empty-copy">Start or select a run to inspect agent execution.</p>
        </div>
      ) : (
        <div className="agent-grid">
          {orderedAgents.map((agent) => (
            <AgentStatusCard key={agent.id} agent={agent} consoleStatus={displayStatus} />
          ))}
        </div>
      )}
    </section>
  );
}
