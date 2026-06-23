import { useMemo, useState } from "react";
import { AgentStatusBoard } from "../components/agents/AgentStatusBoard";
import { AgentTimeline } from "../components/agents/AgentTimeline";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { ArtifactLink } from "../components/common/ArtifactLink";
import { EvaluationSummary } from "../components/evaluation/EvaluationSummary";
import { EvidenceSnapshot } from "../components/evidence/EvidenceSnapshot";
import { EventLog } from "../components/events/EventLog";
import { AppShell } from "../components/layout/AppShell";
import { TopRunContextBar } from "../components/layout/TopRunContextBar";
import { ReportPreview } from "../components/reports/ReportPreview";
import { PlanSelector } from "../components/runs/PlanSelector";
import { RunHistoryPanel } from "../components/runs/RunHistoryPanel";
import { StatusBadge } from "../components/StatusBadge";
import type { ConsoleDataSource, ConsoleErrorState } from "../hooks/useProdwalkConsole";
import { useProdwalkConsole } from "../hooks/useProdwalkConsole";
import type { RunEventConnectionState } from "../api/sse";
import { labelAgentType, labelEventType, labelMode, labelStatus } from "../i18n/zh";
import type {
  AgentExecution,
  AuthReadinessStatus,
  AuthSessionDetail,
  Artifact,
  ConsoleStatus,
  EvaluationResponse,
  EvidenceResponse,
  HealthResponse,
  PlanSummary,
  ReportResponse,
  RunDetail,
  RunEvent,
} from "../types/contracts";

type ConsoleView = "dashboard" | "report" | "evidence" | "history" | "details";

const views: Array<{ id: ConsoleView; label: string }> = [
  { id: "dashboard", label: "工作台" },
  { id: "report", label: "报告" },
  { id: "evidence", label: "证据" },
  { id: "history", label: "历史" },
  { id: "details", label: "详情" },
];

interface ProgressStage {
  label: string;
  types: Array<AgentExecution["type"]>;
}

const progressStages: ProgressStage[] = [
  { label: "总控", types: ["director"] },
  { label: "规划", types: ["planner"] },
  { label: "走查", types: ["walker", "auth_session"] },
  { label: "证据", types: ["evidence_extractor"] },
  { label: "分析", types: ["product_analyst", "competitive_analyst"] },
  { label: "审阅", types: ["reviewer"] },
  { label: "报告", types: ["report_writer"] },
  { label: "评分", types: ["evaluator"] },
];

function getCompletion(run: RunDetail | null): number {
  if (!run || run.progress.total_scenarios === 0) {
    return 0;
  }

  return Math.round((run.progress.completed_scenarios / run.progress.total_scenarios) * 100);
}

function formatScore(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "待生成";
  }

  return value <= 1 ? `${Math.round(value * 100)}%` : String(value);
}

function metadataString(run: RunDetail | null, key: string): string | null {
  const value = run?.metadata?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function getRunMessage(status: ConsoleStatus, run: RunDetail | null): string {
  if (!run) {
    return "选择计划后即可启动一次产品走查。";
  }

  if (run.status === "awaiting_verification") {
    return "需要手动操作：真实浏览器正在等待登录或验证。";
  }

  if (status === "running") {
    return "Agent 正在走查页面、收集证据并准备报告。";
  }

  if (status === "done") {
    return "走查已完成，可以查看报告、证据、评分和截图。";
  }

  if (status === "blocked") {
    return "走查受阻，需要人工处理或环境操作；已有产物仍可查看。";
  }

  if (status === "failed") {
    return "走查失败，部分产物和诊断详情仍可查看。";
  }

  if (status === "timeout") {
    return "走查超时，部分证据和浏览器诊断信息仍可查看。";
  }

  return "走查可以启动。";
}

function getCurrentPhase(agents: AgentExecution[], status: ConsoleStatus): string {
  const activeAgent = agents.find((agent) => agent.status === "running" || agent.status === "waiting");
  const failedAgent = agents.find((agent) => agent.status === "failed");

  if (failedAgent) {
    return `需要复核：${labelAgentType(failedAgent.type)}`;
  }

  if (activeAgent) {
    return [labelAgentType(activeAgent.type), activeAgent.current_step ? `第 ${activeAgent.current_step} 步` : null]
      .filter(Boolean)
      .join(" · ");
  }

  if (status === "done") {
    return "报告和评分已生成";
  }

  if (status === "awaiting_verification") {
    return "等待人工验证完成后重试";
  }

  if (status === "timeout") {
    return "任务超时，未完成全部走查";
  }

  if (status === "idle") {
    return "等待启动";
  }

  return "准备进入下一阶段";
}

function evidenceScreenshotCount(evidence: EvidenceResponse | null): number {
  const screenshotIds = new Set<string>();

  for (const item of evidence?.evidence ?? []) {
    if (item.screenshot_artifact_id) {
      screenshotIds.add(item.screenshot_artifact_id);
    }

    for (const screenshotId of item.screenshot_artifact_ids ?? []) {
      screenshotIds.add(screenshotId);
    }
  }

  return screenshotIds.size;
}

function formatClock(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleTimeString() : "--";
}

function getActiveAgent(agents: AgentExecution[]): AgentExecution | null {
  const priority = new Map<AgentExecution["status"], number>([
    ["running", 0],
    ["waiting", 1],
    ["failed", 2],
    ["pending", 3],
    ["succeeded", 4],
    ["skipped", 5],
    ["canceled", 6],
  ]);

  return (
    [...agents].sort((a, b) => {
      const statusDiff = (priority.get(a.status) ?? 10) - (priority.get(b.status) ?? 10);

      if (statusDiff !== 0) {
        return statusDiff;
      }

      return new Date(b.updated_at ?? b.started_at ?? 0).getTime() - new Date(a.updated_at ?? a.started_at ?? 0).getTime();
    })[0] ?? null
  );
}

function meaningfulEvents(events: RunEvent[]): RunEvent[] {
  const sourceEvents = events.filter((event) => {
    const eventType = event.type.toLowerCase();

    return event.level !== "debug" && !eventType.includes("heartbeat") && (event.message.trim() || event.type);
  });

  return (sourceEvents.length ? sourceEvents : events).slice(-5).reverse();
}

function phaseCounts(agents: AgentExecution[]): { done: number; active: number; total: number; activeLabel: string } {
  const done = progressStages.filter((stage) => {
    const stageAgents = agents.filter((agent) => stage.types.includes(agent.type));

    return stageAgents.length > 0 && stageAgents.every((agent) => agent.status === "succeeded" || agent.status === "skipped");
  }).length;
  const activeStage = progressStages.find((stage) =>
    agents.some((agent) => stage.types.includes(agent.type) && (agent.status === "running" || agent.status === "waiting")),
  );

  return {
    done,
    active: agents.filter((agent) => ["running", "waiting"].includes(agent.status)).length,
    total: progressStages.length,
    activeLabel: activeStage?.label ?? (done === progressStages.length ? "全部完成" : "等待调度"),
  };
}

function metricNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function getAgentProgress(agent: AgentExecution): number {
  const completionScore = metricNumber(agent.metrics.completion_score);

  if (completionScore !== null) {
    return Math.max(0, Math.min(100, Math.round(completionScore * 100)));
  }

  const stepCount = metricNumber(agent.metrics.step_count);

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

function agentStatusForDisplay(agent: AgentExecution, status: ConsoleStatus): AgentExecution["status"] | ConsoleStatus {
  if (agent.status === "succeeded") {
    return "done";
  }

  if (agent.status === "waiting" && (status === "awaiting_verification" || status === "blocked")) {
    return status;
  }

  return agent.status;
}

function getAgentDetail(agent: AgentExecution | null, status: ConsoleStatus): string {
  if (!agent) {
    return "等待下一条事件";
  }

  if (agent.status === "waiting" && status === "awaiting_verification") {
    return "暂停等待人工验证，完成登录、验证码或 MFA 后继续。";
  }

  if (agent.status === "failed") {
    return "执行失败，错误和上下文已保留在详情与事件日志。";
  }

  const target = [agent.product, agent.scenario_id ? `场景 ${agent.scenario_id}` : null].filter(Boolean).join(" / ");
  const actionByType: Record<AgentExecution["type"], string> = {
    director: "正在调度走查流程",
    planner: "正在拆解产品、场景和检查点",
    walker: "正在走查页面并记录操作结果",
    auth_session: "正在准备登录验证会话",
    evidence_extractor: "正在整理证据、截图和浏览器结果",
    product_analyst: "正在提炼产品发现",
    competitive_analyst: "正在对比竞品表现",
    reviewer: "正在复核发现和证据链",
    report_writer: "正在汇总报告内容",
    evaluator: "正在计算评分",
  };
  const stepCount = metricNumber(agent.metrics.step_count);
  const step =
    typeof agent.current_step === "number"
      ? stepCount
        ? `第 ${agent.current_step}/${stepCount} 步`
        : `第 ${agent.current_step} 步`
      : null;

  return [actionByType[agent.type], step, target || "全局任务"].filter(Boolean).join(" · ");
}

function formatEventMeta(event: RunEvent): string {
  const agent = event.agent_type ? labelAgentType(event.agent_type) : event.agent_id ?? "系统";
  const parts = [
    agent,
    event.product,
    event.scenario_id ? `场景 ${event.scenario_id}` : null,
    event.status ? labelStatus(event.status) : null,
  ];

  return parts.filter(Boolean).join(" · ");
}

interface RunProgressPanelProps {
  run: RunDetail | null;
  status: ConsoleStatus;
  agents: AgentExecution[];
  events: RunEvent[];
  artifacts: Artifact[];
  evidence: EvidenceResponse | null;
  authSession: AuthSessionDetail | null;
  retryRunId: string | null;
  error: string | null;
  verificationError: string | null;
  verificationBusy: boolean;
  stopBusy: boolean;
  onStartAuthSession: () => void;
  onCompleteAuthSessionAndRetry: () => void;
  onStopRun: () => void;
}

function RunProgressPanel({
  run,
  status,
  agents,
  events,
  artifacts,
  evidence,
  authSession,
  retryRunId,
  error,
  verificationError,
  verificationBusy,
  stopBusy,
  onStartAuthSession,
  onCompleteAuthSessionAndRetry,
  onStopRun,
}: RunProgressPanelProps) {
  const completion = getCompletion(run);
  const awaitingVerification = run?.status === "awaiting_verification";
  const activeAgent = getActiveAgent(agents);
  const recentEvents = meaningfulEvents(events);
  const phases = phaseCounts(agents);
  const activeAgentProgress = activeAgent ? getAgentProgress(activeAgent) : 0;
  const screenshotCount = Math.max(
    run?.screenshot_count ?? 0,
    evidenceScreenshotCount(evidence),
    artifacts.filter((artifact) => artifact.type === "screenshot").length,
  );
  const evidenceCount = evidence?.evidence.length ?? null;
  const canStopRun = Boolean(
    run && ["queued", "starting", "running", "awaiting_verification", "finalizing", "canceling"].includes(run.status),
  );
  const panelSession = authSession?.run_id === run?.id ? authSession : null;
  const sessionStatus = panelSession?.status ?? "not_started";
  const canStartAuthSession =
    awaitingVerification &&
    (!panelSession || ["failed", "timeout", "canceled"].includes(panelSession.status));
  const canCompleteAuthSession =
    awaitingVerification &&
    Boolean(panelSession) &&
    ["running", "awaiting_user", "succeeded"].includes(panelSession?.status ?? "");
  const activeRetryRunId = retryRunId ?? panelSession?.retry_run_id ?? metadataString(run, "retry_run_id");
  const retryOfRunId = metadataString(run, "retry_of_run_id");

  return (
    <section className="panel run-progress-panel" aria-labelledby="run-progress-title">
      <div className="panel-header">
        <div>
          <h2 id="run-progress-title">当前任务</h2>
          <p>{getRunMessage(status, run)}</p>
        </div>
        <div className="panel-header-actions">
          <StatusBadge status={status} />
          <button type="button" onClick={onStopRun} disabled={!canStopRun || stopBusy}>
            {stopBusy && canStopRun ? "停止中..." : "立即停止"}
          </button>
        </div>
      </div>

      {run ? (
        <div className="active-summary run-overview-strip">
          <div className="run-overview-main">
            <div className="section-title">任务概览</div>
            <strong className="run-id">{run.id}</strong>
            <p>{run.research_goal}</p>
          </div>
          <div className="run-overview-progress">
            <div className="progress-track" aria-label={`已完成 ${completion}%`}>
              <div style={{ width: `${completion}%` }} />
            </div>
            <div className="metric-row">
              <span>{run.progress.completed_scenarios}/{run.progress.total_scenarios} 个场景</span>
              <span>{run.progress.failed_scenarios} 个失败</span>
              <span>{labelMode(run.mode)}</span>
            </div>
          </div>
        </div>
      ) : (
        <EmptyState title="暂无当前任务" message="启动走查后，这里会显示任务目标和场景进度。" compact />
      )}

      {error && !awaitingVerification ? <ErrorState title="任务异常" message="当前任务返回了阻塞或错误信息。" details={error} compact /> : null}

      {run ? (
        <div className={`run-live-snapshot ${awaitingVerification ? "run-live-paused" : ""}`} aria-label="运行现场">
          <div className="live-focus-card">
            <div className="section-title">当前 Agent</div>
            <div className="live-focus-heading">
              <strong>{activeAgent ? labelAgentType(activeAgent.type) : status === "done" ? "报告已完成" : "等待事件"}</strong>
              {activeAgent ? (
                <StatusBadge
                  status={agentStatusForDisplay(activeAgent, status)}
                  label={labelStatus(agentStatusForDisplay(activeAgent, status))}
                />
              ) : null}
            </div>
            <span>
              {activeAgent
                ? getAgentDetail(activeAgent, status)
                : status === "done"
                  ? "报告、证据和评分都已生成。"
                  : "启动后会显示正在执行的 Agent 和页面动作。"}
            </span>
            {activeAgent ? (
              <div className="live-agent-meter" aria-label={`${labelAgentType(activeAgent.type)} 完成度 ${activeAgentProgress}%`}>
                <span style={{ width: `${activeAgentProgress}%` }} />
              </div>
            ) : null}
          </div>
          <div className="live-metric-card">
            <span>阶段</span>
            <strong>
              {phases.done}/{phases.total}
            </strong>
            <small>
              {phases.active
                ? `${phases.active} 个进行中 · ${phases.activeLabel}`
                : status === "done"
                  ? "必要阶段已收束"
                  : phases.activeLabel}
            </small>
          </div>
          <div className="live-metric-card">
            <span>证据</span>
            <strong>{evidenceCount === null ? "待同步" : `${evidenceCount} 条`}</strong>
            <small>{screenshotCount} 张截图</small>
          </div>
          <div className="live-metric-card">
            <span>最近更新</span>
            <strong>{recentEvents[0] ? formatClock(recentEvents[0].ts) : "--"}</strong>
            <small>{recentEvents[0]?.message ?? "暂无事件"}</small>
          </div>
        </div>
      ) : null}

      {run ? (
        <details className="run-recent-events" open aria-label="最近运行动态">
          <summary className="report-section-heading">
            <div>
              <div className="section-title">最近动态</div>
              <strong>看得见的执行过程</strong>
            </div>
            <span>{recentEvents.length} 条</span>
          </summary>
          {recentEvents.length ? (
            <ol>
              {recentEvents.map((event) => (
                <li key={event.id}>
                  <time dateTime={event.ts}>{formatClock(event.ts)}</time>
                  <div>
                    <strong>{labelEventType(event.type)}</strong>
                    <p>{event.message}</p>
                    <span>
                      {formatEventMeta(event)}
                      {event.artifact_ids?.length ? ` · ${event.artifact_ids.length} 个产物` : ""}
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="empty-copy">任务启动后，这里会显示最近的 Agent、证据和报告生成事件。</p>
          )}
        </details>
      ) : null}

      {awaitingVerification ? (
        <div className="verification-panel">
          <div>
            <strong>暂停等待人工验证</strong>
            <span>1. 点击“开始人工验证”，系统会打开可见浏览器。</span>
            <span>2. 在浏览器里完成登录、验证码、MFA 或 SSO。</span>
            <span>3. 回到这里点击“完成验证并继续”，用新的登录态继续走查。</span>
            <span>
              验证会话：{labelStatus(sessionStatus)}
              {panelSession?.storage_state_saved ? "，storage state 已保存" : ""}
              {activeRetryRunId ? `，重试任务：${activeRetryRunId}` : ""}
            </span>
            {error ? <span>暂停原因：{error}</span> : null}
          </div>
          <div className="verification-actions">
            <button type="button" disabled={!canStartAuthSession || verificationBusy} onClick={onStartAuthSession}>
              {verificationBusy && canStartAuthSession ? "正在打开可见浏览器..." : "开始人工验证"}
            </button>
            <button
              type="button"
              className="primary-action"
              disabled={!canCompleteAuthSession || verificationBusy}
              onClick={onCompleteAuthSessionAndRetry}
            >
              {verificationBusy && canCompleteAuthSession ? "正在保存并继续..." : "完成验证并继续"}
            </button>
          </div>
          {verificationError ? <p className="inline-warning">{verificationError}</p> : null}
        </div>
      ) : null}

      {retryOfRunId ? (
        <div className="verification-inline">
          <strong>人工验证后的重试任务</strong>
          <span>来源任务：{retryOfRunId}；验证会话：{metadataString(run, "verification_session_id") ?? "未记录"}。</span>
        </div>
      ) : null}

      <div className="stage-summary">
        <div className="section-title">Agent 进度</div>
        <p>{getCurrentPhase(agents, status)}</p>
        <AgentTimeline agents={agents} consoleStatus={status} />
      </div>
    </section>
  );
}

interface QuickStartPanelProps {
  plans: PlanSummary[];
  selectedPlan: PlanSummary | undefined;
  selectedPlanId: string;
  source: ConsoleDataSource;
  loading: boolean;
  planLoading: boolean;
  planError: string | null;
  onPlanChange: (planId: string) => void;
  onStartMock: () => void;
}

function QuickStartPanel({
  plans,
  selectedPlan,
  selectedPlanId,
  source,
  loading,
  planLoading,
  planError,
  onPlanChange,
  onStartMock,
}: QuickStartPanelProps) {
  const needsPlan = source === "api" && !selectedPlan;

  return (
    <section className="panel compact-panel" aria-labelledby="quick-start-title">
      <div className="panel-header">
        <div>
          <h2 id="quick-start-title">全站走查</h2>
          <p>{selectedPlan ? "选定计划后，先完成登录，再启动一次全站只读走查。" : "先选择走查计划，或使用离线预览数据。"}</p>
        </div>
      </div>

      <PlanSelector plans={plans} selectedPlanId={selectedPlanId} onPlanChange={onPlanChange} />
      {planLoading ? <p className="loading-line">正在读取计划详情...</p> : null}
      {planError ? <p className="inline-warning">{planError}</p> : null}

      <div className="button-row">
        <button type="button" className="primary-action" onClick={onStartMock} disabled={loading || needsPlan}>
          {loading ? "启动中..." : "启动离线模拟"}
        </button>
      </div>
      <p className="empty-copy">真实走查会自动使用全站只读默认参数，不需要手动设置步骤数、超时或浏览器状态。</p>
    </section>
  );
}

function loginStatusCopy(status: AuthReadinessStatus, session: AuthSessionDetail | null): { title: string; detail: string } {
  if (status === "auth_ready") {
    return {
      title: "登录态已就绪",
      detail: "已保存可复用的浏览器登录态，可以开始真实走查。",
    };
  }

  if (status === "awaiting_manual_login") {
    return {
      title: "等待你在浏览器中完成登录",
      detail: "请在已打开的浏览器里完成登录、验证码、MFA 或 SSO，然后回到这里确认。",
    };
  }

  if (session && ["failed", "timeout", "canceled"].includes(session.status)) {
    return {
      title: "登录态可能失效",
      detail: session.message ?? "请重新打开浏览器手动登录。",
    };
  }

  return {
    title: "未登录",
    detail: "先打开浏览器完成手动登录，再启动真实页面走查。",
  };
}

interface LoginPreparationPanelProps {
  selectedPlan: PlanSummary | undefined;
  source: ConsoleDataSource;
  loginSession: AuthSessionDetail | null;
  loginAuthStatus: AuthReadinessStatus;
  loading: boolean;
  startLoading: boolean;
  error: string | null;
  startError: string | null;
  onStartManualLogin: () => void;
  onConfirmManualLogin: () => void;
  onStartAuthenticatedRun: () => void;
}

function LoginPreparationPanel({
  selectedPlan,
  source,
  loginSession,
  loginAuthStatus,
  loading,
  startLoading,
  error,
  startError,
  onStartManualLogin,
  onConfirmManualLogin,
  onStartAuthenticatedRun,
}: LoginPreparationPanelProps) {
  const copy = loginStatusCopy(loginAuthStatus, loginSession);
  const needsPlan = source === "api" && !selectedPlan;
  const canOpenLogin = source === "api" && !needsPlan && loginAuthStatus !== "awaiting_manual_login";
  const canConfirmLogin = loginAuthStatus === "awaiting_manual_login";
  const canStartRealRun = source === "api" && !needsPlan && loginAuthStatus === "auth_ready";

  return (
    <section className="panel login-prep-panel" aria-labelledby="login-prep-title">
      <div className="panel-header">
        <div>
          <h2 id="login-prep-title">登录准备</h2>
          <p>{copy.detail}</p>
        </div>
        <span className={`login-status-pill login-status-${loginAuthStatus}`}>{copy.title}</span>
      </div>

      <div className="active-summary login-prep-summary">
        <div>
          <div className="section-title">目标计划</div>
          <strong>{selectedPlan?.title ?? "未选择计划"}</strong>
        </div>
        <div>
          <div className="section-title">登录会话</div>
          <strong>{loginSession?.session_id ?? "尚未创建"}</strong>
        </div>
      </div>

      <div className="button-row login-prep-actions">
        <button type="button" disabled={!canOpenLogin || loading} onClick={onStartManualLogin}>
          {loading && canOpenLogin ? "正在打开浏览器..." : "打开浏览器手动登录"}
        </button>
        <button type="button" disabled={!canConfirmLogin || loading} onClick={onConfirmManualLogin}>
          {loading && canConfirmLogin ? "正在校验登录态..." : "我已完成登录"}
        </button>
        <button
          type="button"
          className="primary-action"
          disabled={!canStartRealRun || startLoading}
          onClick={onStartAuthenticatedRun}
        >
          {startLoading ? "启动中..." : "开始全站只读走查"}
        </button>
      </div>

      {needsPlan ? <p className="inline-warning">请先选择一个本地走查计划。</p> : null}
      {error ? <p className="inline-warning">{error}</p> : null}
      {startError ? <p className="inline-warning">{startError}</p> : null}
    </section>
  );
}

function getReportPreviewLines(markdown: string | null | undefined): string[] {
  if (!markdown?.trim()) {
    return [];
  }

  return markdown
    .split(/\r?\n/)
    .map((line) => line.replace(/^#{1,6}\s*/, "").replace(/^[-*]\s*/, "").trim())
    .filter((line) => line && !line.startsWith("```") && !line.startsWith("|"))
    .slice(0, 4);
}

interface DashboardReportPreviewProps {
  report: ReportResponse | null;
  evaluation: EvaluationResponse | null;
  status: ConsoleStatus;
  loading: boolean;
  error: string | null;
  onOpenReport: () => void;
}

function DashboardReportPreview({
  report,
  evaluation,
  status,
  loading,
  error,
  onOpenReport,
}: DashboardReportPreviewProps) {
  const hasReport = Boolean(report?.markdown.trim());
  const previewLines = getReportPreviewLines(report?.markdown);
  const score = evaluation?.overall_score ?? report?.evaluation?.overall_score;

  return (
    <section className="panel report-panel" aria-labelledby="dashboard-report-title">
      <div className="panel-header">
        <div>
          <h2 id="dashboard-report-title">报告预览</h2>
          <p>首屏只显示摘要和关键入口，完整报告在报告页查看。</p>
        </div>
        <StatusBadge status={status} />
      </div>

      {loading ? <EmptyState title="正在读取报告" message="正在从 API 读取 Markdown 报告和评分。" /> : null}
      {!loading && error ? <ErrorState title="报告暂不可用" message="当前报告请求返回错误。" details={error} compact /> : null}

      {!loading && !error && !hasReport ? (
        <EmptyState title="暂无报告" message="走查开始后，这里会显示报告摘要、评分和完整报告入口。" />
      ) : null}

      {!loading && hasReport ? (
        <div className="active-summary">
          <div className="section-title">摘要</div>
          {previewLines.length > 0 ? (
            previewLines.map((line) => <p key={line}>{line}</p>)
          ) : (
            <p className="empty-copy">报告已生成，可以打开完整内容查看。</p>
          )}
        </div>
      ) : null}

      <div className="result-card-grid">
        <button type="button" className="result-card" onClick={onOpenReport} disabled={!hasReport}>
          <strong>完整报告</strong>
          <span>{hasReport ? "可打开查看" : "等待生成"}</span>
        </button>
        <button type="button" className="result-card" onClick={onOpenReport} disabled={!hasReport}>
          <strong>评分摘要</strong>
          <span>{formatScore(score)}</span>
        </button>
      </div>
    </section>
  );
}

interface DebugInfoPanelProps {
  source: ConsoleDataSource;
  health: HealthResponse | null;
  connectionState: RunEventConnectionState;
  selectedPlan: PlanSummary | undefined;
  activeRun: RunDetail | null;
  artifacts: Artifact[];
  errors: ConsoleErrorState;
  onRetryApi: () => void;
}

function DebugInfoPanel({
  source,
  health,
  connectionState,
  selectedPlan,
  activeRun,
  artifacts,
  errors,
  onRetryApi,
}: DebugInfoPanelProps) {
  return (
    <section className="panel debug-panel" aria-labelledby="debug-title">
      <div className="panel-header">
        <div>
          <h2 id="debug-title">诊断 / Debug</h2>
          <p>用于排查 API、SSE 和当前任务状态。</p>
        </div>
        <button type="button" onClick={onRetryApi}>
          重试 API
        </button>
      </div>

      <dl className="detail-list">
        <div>
          <dt>数据源</dt>
          <dd>{source}</dd>
        </div>
        <div>
          <dt>API</dt>
          <dd>{health ? `${health.service} ${health.version}` : "不可用"}</dd>
        </div>
        <div>
          <dt>SSE</dt>
          <dd>{connectionState}</dd>
        </div>
        <div>
          <dt>计划</dt>
          <dd>{selectedPlan?.path ?? "--"}</dd>
        </div>
        <div>
          <dt>运行目录</dt>
          <dd>{activeRun?.run_dir ?? "--"}</dd>
        </div>
      </dl>

      {errors.initial || errors.start || errors.activeRun ? (
        <ErrorState
          title="诊断消息"
          message="控制台捕获了 API 或任务错误。"
          details={[errors.initial, errors.start, errors.activeRun].filter(Boolean).join("\n")}
          compact
        />
      ) : null}

      <details className="debug-details">
        <summary>运行参数</summary>
        <pre>{JSON.stringify(activeRun?.params ?? {}, null, 2)}</pre>
      </details>

      <details className="debug-details">
        <summary>产物 ({artifacts.length})</summary>
        <div className="linked-list">
          {artifacts.length === 0 ? <span>尚未读取到产物。</span> : null}
          {artifacts.map((artifact) => (
            <ArtifactLink
              key={artifact.id}
              artifact={artifact}
              label={`${artifact.id} / ${artifact.type}`}
            />
          ))}
        </div>
      </details>
    </section>
  );
}

export function ConsolePage() {
  const console = useProdwalkConsole();
  const [activeView, setActiveView] = useState<ConsoleView>("dashboard");
  const canStopActiveRun = Boolean(
    console.activeRun &&
      ["queued", "starting", "running", "awaiting_verification", "finalizing", "canceling"].includes(console.activeRun.status),
  );

  const startTopMockRun = () => {
    void console.startRun({
      mode: "mock",
      concurrency: 3,
      reportLanguage: console.selectedPlan?.report_language ?? "zh",
      browserMaxSteps: 25,
      verificationMode: "off",
    });
  };

  const selectRunForReview = (runId: string) => {
    console.selectRun(runId);
    setActiveView("report");
  };

  const stopCurrentRun = () => {
    if (!canStopActiveRun) {
      return;
    }

    if (window.confirm("确定要立即停止当前任务吗？已生成的产物会保留。")) {
      void console.stopActiveRun();
    }
  };

  const deleteRunRecord = (runId: string) => {
    if (window.confirm(`确定要删除任务记录 ${runId} 吗？这会删除本地 run 目录和产物。`)) {
      void console.deleteRunRecord(runId);
    }
  };

  const clearRunRecords = () => {
    if (window.confirm("确定要清空历史任务记录吗？运行中的任务会被保留。")) {
      void console.clearRunRecords();
    }
  };

  const canOpenReport = Boolean(console.viewedReport?.markdown.trim());
  const navigation = useMemo(
    () => (
      <div className="workbench-tabs">
        {views.map((view) => (
          <button
            key={view.id}
            type="button"
            className={activeView === view.id ? "selected" : ""}
            onClick={() => setActiveView(view.id)}
          >
            {view.label}
          </button>
        ))}
      </div>
    ),
    [activeView],
  );

  const reportPreview = (
    <ReportPreview
      report={console.viewedRun ? console.viewedReport : null}
      evidence={console.viewedRun ? console.viewedEvidence : null}
      artifacts={console.viewedArtifacts}
      status={console.viewedStatus}
      error={console.viewedReportError}
      evaluationError={console.viewedEvaluationError}
      loading={console.viewedReportLoading}
    />
  );

  const evidenceSnapshot = (
    <EvidenceSnapshot
      evidence={console.viewedRun ? console.viewedEvidence : null}
      artifacts={console.viewedArtifacts}
      status={console.viewedStatus}
      error={console.viewedEvidenceError}
      loading={console.viewedEvidenceLoading}
    />
  );

  const runHistory = (
    <RunHistoryPanel
      runs={console.recentRuns}
      activeRunId={console.activeRunId}
      selectedRunId={console.viewingHistory ? console.selectedHistoryRunId : console.activeRunId}
      loading={console.loading.initial || console.loading.runHistory}
      error={console.errors.runHistory}
      onRefresh={() => void console.refreshRunHistory()}
      onSelectRun={selectRunForReview}
      onDeleteRun={deleteRunRecord}
      onClearRuns={clearRunRecords}
      onClearSelection={console.clearHistorySelection}
    />
  );

  let content;

  if (activeView === "report") {
    content = reportPreview;
  } else if (activeView === "evidence") {
    content = evidenceSnapshot;
  } else if (activeView === "history") {
    content = runHistory;
  } else if (activeView === "details") {
    content = (
      <div className="details-grid">
        <DebugInfoPanel
          source={console.source}
          health={console.health}
          connectionState={console.connectionState}
          selectedPlan={console.selectedPlan}
          activeRun={console.activeRun}
          artifacts={console.artifacts}
          errors={console.errors}
          onRetryApi={console.retryApi}
        />
        <EvaluationSummary
          evaluation={console.viewedEvaluation}
          run={console.viewedRun}
          status={console.viewedStatus}
          loading={console.viewedEvaluationLoading}
          error={console.viewedEvaluationError}
          viewingHistory={console.viewingHistory}
        />
        <AgentStatusBoard agents={console.activeRun ? console.agents : []} consoleStatus={console.consoleStatus} />
        <EventLog
          events={console.activeRun ? console.events : []}
          activeRunId={console.activeRunId}
          connectionState={console.connectionState}
          loading={console.loading.activeRun}
          error={console.errors.activeRun}
          source={console.source}
        />
      </div>
    );
  } else {
    content = (
      <div className="dashboard-layout">
        <div className="dashboard-command-row">
          <QuickStartPanel
            plans={console.plans}
            selectedPlan={console.selectedPlan}
            selectedPlanId={console.selectedPlanId}
            source={console.source}
            loading={console.loading.start}
            planLoading={console.loading.planDetail}
            planError={console.errors.planDetail}
            onPlanChange={console.setSelectedPlanId}
            onStartMock={startTopMockRun}
          />
          <LoginPreparationPanel
            selectedPlan={console.selectedPlan}
            source={console.source}
            loginSession={console.loginSession}
            loginAuthStatus={console.loginAuthStatus}
            loading={console.loading.verification}
            startLoading={console.loading.start}
            error={console.errors.verification}
            startError={console.errors.start}
            onStartManualLogin={() => void console.startManualLogin()}
            onConfirmManualLogin={() => void console.confirmManualLogin()}
            onStartAuthenticatedRun={() => void console.startAuthenticatedRun()}
          />
        </div>
        <RunProgressPanel
          run={console.activeRun}
          status={console.consoleStatus}
          agents={console.activeRun ? console.agents : []}
          events={console.activeRun ? console.events : []}
          artifacts={console.artifacts}
          evidence={console.evidence}
          authSession={console.authSession}
          retryRunId={console.retryRunId}
          error={console.runError}
          verificationError={console.errors.verification}
          verificationBusy={console.loading.verification}
          stopBusy={console.loading.activeRun}
          onStartAuthSession={() => void console.startAuthSession()}
          onCompleteAuthSessionAndRetry={() => void console.completeAuthSessionAndRetry()}
          onStopRun={stopCurrentRun}
        />
        <div className="dashboard-report">
          <DashboardReportPreview
            report={console.viewedRun ? console.viewedReport : null}
            evaluation={console.viewedEvaluation}
            status={console.viewedStatus}
            loading={console.viewedReportLoading}
            error={console.viewedReportError}
            onOpenReport={() => setActiveView("report")}
          />
        </div>
        <div className="dashboard-foldouts">
          <details className="workbench-foldout">
            <summary>
              <strong>证据和截图</strong>
              <span>
                {console.viewedEvidence?.evidence.length ?? 0} 条证据，{evidenceScreenshotCount(console.viewedEvidence)} 张截图
              </span>
            </summary>
            {evidenceSnapshot}
          </details>
          <details className="workbench-foldout">
            <summary>
              <strong>历史任务</strong>
              <span>{console.recentRuns.length} 条本地记录</span>
            </summary>
            {runHistory}
          </details>
        </div>
      </div>
    );
  }

  return (
    <AppShell
      topBar={
        <TopRunContextBar
          activeRun={console.activeRun}
          selectedPlan={console.selectedPlan}
          consoleStatus={console.consoleStatus}
          onStartMock={startTopMockRun}
          onStopRun={stopCurrentRun}
          onOpenReport={() => setActiveView("report")}
          canOpenReport={canOpenReport}
          startDisabled={console.loading.start}
          stopDisabled={!canStopActiveRun || console.loading.activeRun}
        />
      }
      navigation={navigation}
    >
      {content}
    </AppShell>
  );
}
