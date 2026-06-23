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
    return "暂无运行中的 Agent。";
  }

  const activeCount = agents.filter((agent) => agent.status === "running" || agent.status === "waiting").length;

  switch (status) {
    case "running":
      return `${activeCount} 个 Agent 正在运行或等待。`;
    case "awaiting_verification":
      return "browser-use 阶段正在等待人工验证。";
    case "done":
      return "所有必要 Agent 阶段已完成或跳过。";
    case "blocked":
      return "有 Agent 正在等待人工操作或环境恢复。";
    case "failed":
      return "失败 Agent 已保留错误和相关事件。";
    default:
      return "Agent 状态不可用。";
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
          <h2 id="agent-status-title">Agent 状态</h2>
          <p>{getPanelSummary(displayStatus, agents)}</p>
        </div>
        <StatusBadge status={displayStatus} />
      </div>

      <AgentTimeline agents={agents} consoleStatus={displayStatus} />

      {agents.length === 0 ? (
        <div className="active-summary">
          <div className="section-title">等待启动</div>
          <p className="empty-copy">启动或选择一个任务后，可以在这里查看 Agent 执行过程。</p>
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
