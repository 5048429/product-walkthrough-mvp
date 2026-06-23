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
import { RunHistoryPanel } from "../components/runs/RunHistoryPanel";
import { RunLauncher } from "../components/runs/RunLauncher";
import { StatusBadge } from "../components/StatusBadge";
import type { ConsoleDataSource, ConsoleErrorState } from "../hooks/useProdwalkConsole";
import { useProdwalkConsole } from "../hooks/useProdwalkConsole";
import type { RunEventConnectionState } from "../api/sse";
import { labelAgentType, labelMode, labelStatus } from "../i18n/zh";
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
} from "../types/contracts";

type ConsoleView = "dashboard" | "report" | "evidence" | "history" | "details";

const views: Array<{ id: ConsoleView; label: string }> = [
  { id: "dashboard", label: "工作台" },
  { id: "report", label: "报告" },
  { id: "evidence", label: "证据" },
  { id: "history", label: "历史" },
  { id: "details", label: "详情" },
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
    return labelAgentType(activeAgent.type);
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
  return (evidence?.evidence ?? []).filter((item) => item.screenshot_artifact_id || item.screenshot_artifact_ids?.length).length;
}

interface RunProgressPanelProps {
  run: RunDetail | null;
  status: ConsoleStatus;
  agents: AgentExecution[];
  authSession: AuthSessionDetail | null;
  retryRunId: string | null;
  error: string | null;
  verificationError: string | null;
  verificationBusy: boolean;
  onStartAuthSession: () => void;
  onCompleteAuthSessionAndRetry: () => void;
}

function RunProgressPanel({
  run,
  status,
  agents,
  authSession,
  retryRunId,
  error,
  verificationError,
  verificationBusy,
  onStartAuthSession,
  onCompleteAuthSessionAndRetry,
}: RunProgressPanelProps) {
  const completion = getCompletion(run);
  const awaitingVerification = run?.status === "awaiting_verification";
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
        <StatusBadge status={status} />
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
  selectedPlan: PlanSummary | undefined;
  source: ConsoleDataSource;
  loading: boolean;
  onStartMock: () => void;
}

function QuickStartPanel({ selectedPlan, source, loading, onStartMock }: QuickStartPanelProps) {
  const needsPlan = source === "api" && !selectedPlan;
  const reportLanguage = selectedPlan?.report_language === "en" ? "英文" : "中文";

  return (
    <section className="panel compact-panel" aria-labelledby="quick-start-title">
      <div className="panel-header">
        <div>
          <h2 id="quick-start-title">启动走查</h2>
          <p>{selectedPlan ? "使用当前计划快速启动一次模拟走查。" : "先选择走查计划，或使用离线预览数据。"}</p>
        </div>
      </div>

      <div className="active-summary">
        <div className="section-title">当前计划</div>
        <strong>{selectedPlan?.title ?? "未选择计划"}</strong>
        <div className="metric-row">
          <span>{selectedPlan ? `${selectedPlan.product_count} 个产品` : "等待选择"}</span>
          <span>{selectedPlan ? `${selectedPlan.scenario_count} 个场景` : "暂无场景"}</span>
          <span>{selectedPlan ? `报告语言：${reportLanguage}` : "中文报告"}</span>
        </div>
      </div>

      <div className="button-row">
        <button type="button" className="primary-action" onClick={onStartMock} disabled={loading || needsPlan}>
          {loading ? "启动中..." : "启动模拟走查"}
        </button>
      </div>
      <p className="empty-copy">需要真实浏览器、browser-use 或验证参数时，展开下方“高级启动设置”。</p>
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
          {startLoading ? "启动中..." : "开始真实走查"}
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

  const launcher = (
    <RunLauncher
      source={console.source}
      health={console.health}
      plans={console.plans}
      selectedPlanId={console.selectedPlanId}
      selectedPlanDetail={console.selectedPlanDetail}
      consoleStatus={console.consoleStatus}
      authReady={console.loginAuthStatus === "auth_ready"}
      authSessionId={console.loginSession?.session_id ?? null}
      loading={console.loading}
      errors={console.errors}
      onPlanChange={console.setSelectedPlanId}
      onStartRun={(options) => void console.startRun(options)}
      onMockStatusChange={console.setMockPreviewStatus}
      onRetryApi={console.retryApi}
    />
  );

  const reportPreview = (
    <ReportPreview
      report={console.viewedRun ? console.viewedReport : null}
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
            selectedPlan={console.selectedPlan}
            source={console.source}
            loading={console.loading.start}
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
          <details className="workbench-foldout launcher-foldout">
            <summary>
              <strong>高级启动设置</strong>
              <span>计划选择、browser-use 和人工验证参数</span>
            </summary>
            {launcher}
          </details>
        </div>
        <RunProgressPanel
          run={console.activeRun}
          status={console.consoleStatus}
          agents={console.activeRun ? console.agents : []}
          authSession={console.authSession}
          retryRunId={console.retryRunId}
          error={console.runError}
          verificationError={console.errors.verification}
          verificationBusy={console.loading.verification}
          onStartAuthSession={() => void console.startAuthSession()}
          onCompleteAuthSessionAndRetry={() => void console.completeAuthSessionAndRetry()}
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
          onOpenReport={() => setActiveView("report")}
          canOpenReport={canOpenReport}
          startDisabled={console.loading.start}
        />
      }
      navigation={navigation}
    >
      {content}
    </AppShell>
  );
}
