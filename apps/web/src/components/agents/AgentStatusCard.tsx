import { StatusBadge } from "../StatusBadge";
import type { AgentExecution, AgentStatus, ConsoleStatus } from "../../types/contracts";
import { formatApiError } from "../../types/contracts";
import { labelAgentType, labelStatus } from "../../i18n/zh";

interface AgentStatusCardProps {
  agent: AgentExecution;
  consoleStatus: ConsoleStatus;
}

function formatAgentMeta(agent: AgentExecution): string {
  const parts = [labelAgentType(agent.type)];

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

  if (agentStatus === "waiting" && (consoleStatus === "blocked" || consoleStatus === "awaiting_verification")) {
    return consoleStatus;
  }

  if (agentStatus === "failed") {
    return "failed";
  }

  return agentStatus;
}

function getStatusLabel(agentStatus: AgentStatus, consoleStatus: ConsoleStatus): string {
  if (agentStatus === "succeeded") {
    return labelStatus("done");
  }

  if (agentStatus === "waiting" && (consoleStatus === "blocked" || consoleStatus === "awaiting_verification")) {
    return labelStatus(consoleStatus);
  }

  return labelStatus(agentStatus);
}

function formatMetric(value: unknown, fallback = "--"): string {
  if (typeof value === "number" || typeof value === "string") {
    return String(value);
  }

  return fallback;
}

function getCompletionPercent(agent: AgentExecution): number {
  const completionScore = agent.metrics.completion_score;

  if (typeof completionScore === "number") {
    return Math.round(Math.max(0, Math.min(1, completionScore)) * 100);
  }

  const stepCount = agent.metrics.step_count;

  if (typeof agent.current_step === "number" && typeof stepCount === "number" && stepCount > 0) {
    return Math.round(Math.max(0, Math.min(1, agent.current_step / stepCount)) * 100);
  }

  if (agent.status === "succeeded" || agent.status === "skipped") {
    return 100;
  }

  if (agent.status === "running" || agent.status === "waiting") {
    return 42;
  }

  return 0;
}

export function AgentStatusCard({ agent, consoleStatus }: AgentStatusCardProps) {
  const displayStatus = getDisplayStatus(agent.status, consoleStatus);
  const stepCount = formatMetric(agent.metrics.step_count);
  const completionScore = agent.metrics.completion_score;
  const completionPercent = getCompletionPercent(agent);
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

      <div className="agent-card-meter" aria-label={`${labelAgentType(agent.type)} 进度 ${completionPercent}%`}>
        <span style={{ width: `${completionPercent}%` }} />
      </div>

      <dl className="detail-list">
        <div>
          <dt>当前步骤</dt>
          <dd>{agent.current_step ?? "--"}</dd>
        </div>
        <div>
          <dt>总步骤</dt>
          <dd>{stepCount}</dd>
        </div>
        <div>
          <dt>开始时间</dt>
          <dd>{formatClock(agent.started_at)}</dd>
        </div>
        <div>
          <dt>心跳</dt>
          <dd>{formatClock(agent.updated_at)}</dd>
        </div>
        <div>
          <dt>完成度</dt>
          <dd>{typeof completionScore === "number" ? `${Math.round(completionScore * 100)}%` : `${completionPercent}%`}</dd>
        </div>
      </dl>

      {error ? <p className="inline-warning">{error}</p> : null}
      {agent.status === "failed" && !error ? <p className="inline-warning">失败事件已保留在日志中。</p> : null}
    </article>
  );
}
