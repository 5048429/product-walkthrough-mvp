import { StatusBadge } from "../StatusBadge";
import type { AgentExecution, AgentStatus, ConsoleStatus } from "../../types/contracts";
import { formatApiError } from "../../types/contracts";

interface AgentStatusCardProps {
  agent: AgentExecution;
  consoleStatus: ConsoleStatus;
}

function formatAgentMeta(agent: AgentExecution): string {
  const parts = [agent.type.replaceAll("_", " ")];

  if (agent.product) {
    parts.push(agent.product);
  }

  if (agent.scenario_id) {
    parts.push(agent.scenario_id);
  }

  return parts.join(" / ");
}

function formatClock(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleTimeString() : "--";
}

function getDisplayStatus(agentStatus: AgentStatus, consoleStatus: ConsoleStatus): AgentStatus | ConsoleStatus {
  if (agentStatus === "succeeded") {
    return "done";
  }

  if (agentStatus === "waiting" && consoleStatus === "blocked") {
    return "blocked";
  }

  if (agentStatus === "failed") {
    return "failed";
  }

  return agentStatus;
}

function getStatusLabel(agentStatus: AgentStatus, consoleStatus: ConsoleStatus): string {
  if (agentStatus === "succeeded") {
    return "done";
  }

  if (agentStatus === "waiting" && consoleStatus === "blocked") {
    return "blocked";
  }

  return agentStatus;
}

function formatMetric(value: unknown, fallback = "--"): string {
  if (typeof value === "number" || typeof value === "string") {
    return String(value);
  }

  return fallback;
}

export function AgentStatusCard({ agent, consoleStatus }: AgentStatusCardProps) {
  const displayStatus = getDisplayStatus(agent.status, consoleStatus);
  const stepCount = formatMetric(agent.metrics.step_count);
  const completionScore = agent.metrics.completion_score;
  const error = formatApiError(agent.error);

  return (
    <article className="agent-card">
      <div className="card-heading">
        <div>
          <h3>{agent.label}</h3>
          <span>{formatAgentMeta(agent)}</span>
        </div>
        <StatusBadge status={displayStatus} label={getStatusLabel(agent.status, consoleStatus)} />
      </div>

      <dl className="detail-list">
        <div>
          <dt>Current step</dt>
          <dd>{agent.current_step ?? "--"}</dd>
        </div>
        <div>
          <dt>Step count</dt>
          <dd>{stepCount}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{formatClock(agent.started_at)}</dd>
        </div>
        <div>
          <dt>Heartbeat</dt>
          <dd>{formatClock(agent.updated_at)}</dd>
        </div>
        <div>
          <dt>Completion</dt>
          <dd>{typeof completionScore === "number" ? `${Math.round(completionScore * 100)}%` : "pending"}</dd>
        </div>
      </dl>

      {error ? <p className="inline-warning">{error}</p> : null}
      {agent.status === "failed" && !error ? <p className="inline-warning">Failed event is available in log.</p> : null}
    </article>
  );
}
