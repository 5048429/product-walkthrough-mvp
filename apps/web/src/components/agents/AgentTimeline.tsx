import { StatusBadge } from "../StatusBadge";
import type { AgentExecution, AgentStatus, AgentType, ConsoleStatus } from "../../types/contracts";
import { formatApiError } from "../../types/contracts";
import { labelAgentType, labelStatus } from "../../i18n/zh";

interface StageDefinition {
  label: string;
  types: AgentType[];
}

interface AgentTimelineProps {
  agents: AgentExecution[];
  consoleStatus: ConsoleStatus;
}

type DisplayStatus = AgentStatus | ConsoleStatus;

const stages: StageDefinition[] = [
  { label: "总控", types: ["director"] },
  { label: "规划", types: ["planner"] },
  { label: "走查", types: ["walker", "auth_session"] },
  { label: "证据", types: ["evidence_extractor"] },
  { label: "分析", types: ["product_analyst", "competitive_analyst"] },
  { label: "审阅", types: ["reviewer"] },
  { label: "报告", types: ["report_writer"] },
  { label: "评分", types: ["evaluator"] },
];

const statusTone: Record<ConsoleStatus, string> = {
  idle: "#64748b",
  running: "#1f5ed2",
  awaiting_verification: "#c47a00",
  done: "#087657",
  blocked: "#c47a00",
  failed: "#b42318",
  timeout: "#b42318",
};

function getStageStatus(stageAgents: AgentExecution[], consoleStatus: ConsoleStatus): ConsoleStatus {
  if (stageAgents.length === 0) {
    return "idle";
  }

  if (stageAgents.some((agent) => agent.status === "failed")) {
    return "failed";
  }

  if (stageAgents.some((agent) => agent.status === "running")) {
    return "running";
  }

  if (stageAgents.some((agent) => agent.status === "waiting")) {
    return consoleStatus === "blocked" || consoleStatus === "awaiting_verification" ? consoleStatus : "running";
  }

  if (stageAgents.every((agent) => agent.status === "succeeded" || agent.status === "skipped")) {
    return "done";
  }

  return "idle";
}

function getDisplayStatus(agent: AgentExecution, consoleStatus: ConsoleStatus): DisplayStatus {
  if (agent.status === "succeeded") {
    return "done";
  }

  if (agent.status === "waiting" && (consoleStatus === "blocked" || consoleStatus === "awaiting_verification")) {
    return consoleStatus;
  }

  return agent.status;
}

function normalizeNodeClass(status: DisplayStatus): string {
  return status === "succeeded" ? "done" : status;
}

function formatAgentTarget(agent: AgentExecution): string {
  const parts = [agent.product, agent.scenario_id].filter((value): value is string => Boolean(value));
  return parts.length ? parts.join(" / ") : "全局任务";
}

function numberMetric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function getAgentProgress(agent: AgentExecution): number {
  const completionScore = numberMetric(agent.metrics.completion_score);

  if (completionScore !== null) {
    return Math.max(0, Math.min(100, Math.round(completionScore * 100)));
  }

  const stepCount = numberMetric(agent.metrics.step_count);

  if (typeof agent.current_step === "number" && stepCount && stepCount > 0) {
    return Math.max(0, Math.min(100, Math.round((agent.current_step / stepCount) * 100)));
  }

  if (agent.status === "succeeded" || agent.status === "skipped") {
    return 100;
  }

  if (agent.status === "running" || agent.status === "waiting") {
    return 42;
  }

  return 0;
}

function getAgentHint(agent: AgentExecution, displayStatus: DisplayStatus): string {
  if (agent.error) {
    return formatApiError(agent.error) ?? "等待处理异常";
  }

  if (displayStatus === "running") {
    if (typeof agent.current_step === "number") {
      return `正在执行第 ${agent.current_step} 步`;
    }

    return "正在处理当前阶段";
  }

  if (displayStatus === "awaiting_verification") {
    return "需要你完成浏览器登录或验证";
  }

  if (displayStatus === "blocked" || displayStatus === "waiting") {
    return "等待人工操作、资源或前置阶段";
  }

  if (displayStatus === "done") {
    return "阶段已完成，结果已写入产物";
  }

  if (displayStatus === "failed") {
    return "执行失败，展开查看错误";
  }

  if (displayStatus === "skipped") {
    return "本次任务跳过该阶段";
  }

  if (displayStatus === "canceled") {
    return "阶段已取消";
  }

  return "等待调度";
}

function formatClock(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleTimeString() : "--";
}

function formatMetricValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "--";
  }

  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }

  if (typeof value === "string") {
    return value;
  }

  return JSON.stringify(value);
}

function sortAgents(agents: AgentExecution[]): AgentExecution[] {
  const priority = new Map<AgentStatus, number>([
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

function getLiveHeadline(agents: AgentExecution[], consoleStatus: ConsoleStatus): string {
  const runningCount = agents.filter((agent) => agent.status === "running").length;
  const waitingCount = agents.filter((agent) => agent.status === "waiting").length;
  const failedCount = agents.filter((agent) => agent.status === "failed").length;

  if (failedCount > 0) {
    return `${failedCount} 个 Agent 需要复核`;
  }

  if (consoleStatus === "awaiting_verification") {
    return "等待人工验证";
  }

  if (runningCount || waitingCount) {
    return `${runningCount} 个运行中，${waitingCount} 个等待中`;
  }

  if (consoleStatus === "done") {
    return "所有关键阶段已收束";
  }

  return "Agent 等待启动";
}

function getLiveSubcopy(agents: AgentExecution[], consoleStatus: ConsoleStatus): string {
  const activeAgent = agents.find((agent) => agent.status === "running" || agent.status === "waiting");

  if (activeAgent) {
    return `${labelAgentType(activeAgent.type)}：${getAgentHint(activeAgent, getDisplayStatus(activeAgent, consoleStatus))}`;
  }

  if (consoleStatus === "done") {
    return "可以查看报告、证据和评分。";
  }

  return "启动走查后，这里会像 Codex 一样持续滚动显示执行状态。";
}

export function AgentTimeline({ agents, consoleStatus }: AgentTimelineProps) {
  const orderedAgents = sortAgents(agents);
  const hasAgents = orderedAgents.length > 0;

  return (
    <div className="agent-workbench">
      <div className={`agent-live-strip agent-live-${consoleStatus}`}>
        <span className="agent-live-pulse" aria-hidden="true" />
        <div>
          <strong>{getLiveHeadline(agents, consoleStatus)}</strong>
          <span>{getLiveSubcopy(agents, consoleStatus)}</span>
        </div>
      </div>

      <div className="timeline" aria-label="Agent 阶段总览">
        {stages.map((stage) => {
          const stageAgents = agents.filter((agent) => stage.types.includes(agent.type));
          const stageStatus = getStageStatus(stageAgents, consoleStatus);
          const statusClass = stageStatus === "done" ? "node-done" : `node-${stageStatus}`;

          return (
            <div key={stage.label} className={`timeline-node ${statusClass}`}>
              <span className="timeline-dot" style={{ background: statusTone[stageStatus] }} />
              <strong>{stage.label}</strong>
              <StatusBadge status={stageStatus} />
            </div>
          );
        })}
      </div>

      <div className="agent-activity-list" aria-label="Agent 实时活动">
        {!hasAgents ? (
          <div className="agent-activity-empty">
            <strong>暂无 Agent 活动</strong>
            <span>启动或选择一个任务后，每个 Agent 的进度会显示在这里。</span>
          </div>
        ) : (
          orderedAgents.map((agent) => {
            const displayStatus = getDisplayStatus(agent, consoleStatus);
            const normalizedStatus = normalizeNodeClass(displayStatus);
            const progress = getAgentProgress(agent);
            const metrics = Object.entries(agent.metrics).filter(([, value]) => value !== null && value !== undefined);
            const defaultOpen = ["running", "waiting", "failed", "blocked", "awaiting_verification"].includes(String(displayStatus));

            return (
              <details key={agent.id} className={`agent-activity-row agent-activity-${normalizedStatus}`} open={defaultOpen}>
                <summary>
                  <span className="agent-activity-pin" aria-hidden="true" />
                  <div className="agent-activity-copy">
                    <strong>{labelAgentType(agent.type)}</strong>
                    <span>{getAgentHint(agent, displayStatus)}</span>
                  </div>
                  <div className="agent-activity-meter" aria-label={`${labelAgentType(agent.type)} 进度 ${progress}%`}>
                    <span style={{ width: `${progress}%` }} />
                  </div>
                  <StatusBadge status={displayStatus} label={labelStatus(displayStatus)} />
                </summary>

                <div className="agent-activity-detail">
                  <dl>
                    <div>
                      <dt>目标</dt>
                      <dd>{formatAgentTarget(agent)}</dd>
                    </div>
                    <div>
                      <dt>当前步骤</dt>
                      <dd>{agent.current_step ?? "--"}</dd>
                    </div>
                    <div>
                      <dt>开始</dt>
                      <dd>{formatClock(agent.started_at)}</dd>
                    </div>
                    <div>
                      <dt>心跳</dt>
                      <dd>{formatClock(agent.updated_at)}</dd>
                    </div>
                  </dl>
                  {metrics.length ? (
                    <div className="agent-metric-chips" aria-label="Agent metrics">
                      {metrics.map(([key, value]) => (
                        <span key={key}>
                          {key.replaceAll("_", " ")}: {formatMetricValue(value)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </details>
            );
          })
        )}
      </div>
    </div>
  );
}
