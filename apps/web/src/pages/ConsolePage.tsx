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
import type {
  AgentExecution,
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
  { id: "dashboard", label: "Dashboard" },
  { id: "report", label: "Report" },
  { id: "evidence", label: "Evidence" },
  { id: "history", label: "History" },
  { id: "details", label: "Details" },
];

function getCompletion(run: RunDetail | null): number {
  if (!run || run.progress.total_scenarios === 0) {
    return 0;
  }

  return Math.round((run.progress.completed_scenarios / run.progress.total_scenarios) * 100);
}

function formatScore(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "Pending";
  }

  return value <= 1 ? `${Math.round(value * 100)}%` : String(value);
}

function getRunMessage(status: ConsoleStatus, run: RunDetail | null): string {
  if (!run) {
    return "Choose a plan and start a run.";
  }

  if (run.status === "awaiting_verification") {
    return "Browser-use is waiting for manual verification in the local browser.";
  }

  if (status === "running") {
    return "Agents are collecting evidence and preparing the report.";
  }

  if (status === "done") {
    return "Run completed. Review the report and evidence below.";
  }

  if (status === "blocked") {
    return "Run is waiting for an operator or environment action. Available artifacts remain reviewable.";
  }

  if (status === "failed") {
    return "Run failed. Partial artifacts and debug details are still available.";
  }

  if (status === "timeout") {
    return "Run timed out. Partial artifacts and browser diagnostics remain available.";
  }

  return "Run is ready to start.";
}

function getCurrentPhase(agents: AgentExecution[], status: ConsoleStatus): string {
  const activeAgent = agents.find((agent) => agent.status === "running" || agent.status === "waiting");
  const failedAgent = agents.find((agent) => agent.status === "failed");

  if (failedAgent) {
    return `Needs review: ${failedAgent.label}`;
  }

  if (activeAgent) {
    return activeAgent.label;
  }

  if (status === "done") {
    return "Report and evaluation ready";
  }

  if (status === "timeout") {
    return "Timed out before completion";
  }

  if (status === "idle") {
    return "Waiting to start";
  }

  return "Preparing next stage";
}

function evidenceScreenshotCount(evidence: EvidenceResponse | null): number {
  return (evidence?.evidence ?? []).filter((item) => item.screenshot_artifact_id || item.screenshot_artifact_ids?.length).length;
}

interface RunProgressPanelProps {
  run: RunDetail | null;
  status: ConsoleStatus;
  agents: AgentExecution[];
  events: RunEvent[];
  error: string | null;
  verificationError: string | null;
  confirmingVerification: boolean;
  onConfirmVerification: () => void;
}

function RunProgressPanel({
  run,
  status,
  agents,
  events,
  error,
  verificationError,
  confirmingVerification,
  onConfirmVerification,
}: RunProgressPanelProps) {
  const completion = getCompletion(run);
  const recentEvents = events.slice(-4).reverse();
  const awaitingVerification = run?.status === "awaiting_verification";

  return (
    <section className="panel run-progress-panel" aria-labelledby="run-progress-title">
      <div className="panel-header">
        <div>
          <h2 id="run-progress-title">Current Run Status</h2>
          <p>{getRunMessage(status, run)}</p>
        </div>
        <StatusBadge status={status} />
      </div>

      {run ? (
        <div className="active-summary">
          <div className="section-title">Run</div>
          <strong className="run-id">{run.id}</strong>
          <p>{run.research_goal}</p>
          <div className="progress-track" aria-label={`${completion}% complete`}>
            <div style={{ width: `${completion}%` }} />
          </div>
          <div className="metric-row">
            <span>{run.progress.completed_scenarios}/{run.progress.total_scenarios} scenarios</span>
            <span>{run.progress.failed_scenarios} failed</span>
            <span>{run.mode}</span>
          </div>
        </div>
      ) : (
        <EmptyState title="No active run" message="Start a mock run to see progress here." compact />
      )}

      {error ? <ErrorState title="Run issue" message="The run reported a blocker or error." details={error} compact /> : null}

      {awaitingVerification ? (
        <div className="verification-panel">
          <div>
            <strong>Awaiting verification</strong>
            <span>Finish the CAPTCHA, MFA, SSO, or login checkpoint in the local browser window, then continue from here.</span>
          </div>
          <button type="button" className="primary-action" disabled={confirmingVerification} onClick={onConfirmVerification}>
            {confirmingVerification ? "Confirming..." : "我已完成验证，继续"}
          </button>
          {verificationError ? <p className="inline-warning">{verificationError}</p> : null}
        </div>
      ) : null}

      <div className="stage-summary">
        <div className="section-title">Agent Progress</div>
        <p>{getCurrentPhase(agents, status)}</p>
        <AgentTimeline agents={agents} consoleStatus={status} />
      </div>

      <div className="activity-summary">
        <div className="section-title">Recent Activity</div>
        {recentEvents.length === 0 ? (
          <p className="empty-copy">Activity will appear after the run starts.</p>
        ) : (
          <ol>
            {recentEvents.map((event) => (
              <li key={event.id}>
                <strong>{event.type.replaceAll(".", " ")}</strong>
                <span>{event.message}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

interface ResultShortcutsProps {
  report: ReportResponse | null;
  evidence: EvidenceResponse | null;
  evaluation: EvaluationResponse | null;
  status: ConsoleStatus;
  onViewChange: (view: ConsoleView) => void;
}

function ResultShortcuts({ report, evidence, evaluation, status, onViewChange }: ResultShortcutsProps) {
  const hasReport = Boolean(report?.markdown.trim());
  const evidenceCount = evidence?.evidence.length ?? 0;
  const screenshotCount = evidenceScreenshotCount(evidence);

  return (
    <section className="panel results-panel" aria-labelledby="results-title">
      <div className="panel-header">
        <div>
          <h2 id="results-title">Results</h2>
          <p>Review the generated product walk artifacts.</p>
        </div>
        <StatusBadge status={status} />
      </div>

      <div className="result-card-grid">
        <button type="button" className="result-card" onClick={() => onViewChange("report")} disabled={!hasReport}>
          <strong>Report</strong>
          <span>{hasReport ? "Ready to review" : "Waiting for report"}</span>
        </button>
        <button type="button" className="result-card" onClick={() => onViewChange("evidence")} disabled={evidenceCount === 0}>
          <strong>Evidence</strong>
          <span>{evidenceCount} items, {screenshotCount} with screenshots</span>
        </button>
        <button type="button" className="result-card" onClick={() => onViewChange("report")} disabled={!evaluation}>
          <strong>Evaluation</strong>
          <span>{formatScore(evaluation?.overall_score)}</span>
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
          <h2 id="debug-title">API / Debug</h2>
          <p>Engineering details for diagnosing the current console state.</p>
        </div>
        <button type="button" onClick={onRetryApi}>
          Retry API
        </button>
      </div>

      <dl className="detail-list">
        <div>
          <dt>Source</dt>
          <dd>{source}</dd>
        </div>
        <div>
          <dt>API</dt>
          <dd>{health ? `${health.service} ${health.version}` : "unavailable"}</dd>
        </div>
        <div>
          <dt>SSE</dt>
          <dd>{connectionState}</dd>
        </div>
        <div>
          <dt>Plan</dt>
          <dd>{selectedPlan?.path ?? "--"}</dd>
        </div>
        <div>
          <dt>Run dir</dt>
          <dd>{activeRun?.run_dir ?? "--"}</dd>
        </div>
      </dl>

      {errors.initial || errors.start || errors.activeRun ? (
        <ErrorState
          title="Debug messages"
          message="The console captured API or run errors."
          details={[errors.initial, errors.start, errors.activeRun].filter(Boolean).join("\n")}
          compact
        />
      ) : null}

      <details className="debug-details">
        <summary>Run params</summary>
        <pre>{JSON.stringify(activeRun?.params ?? {}, null, 2)}</pre>
      </details>

      <details className="debug-details">
        <summary>Artifacts ({artifacts.length})</summary>
        <div className="linked-list">
          {artifacts.length === 0 ? <span>No artifacts loaded.</span> : null}
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
      activeRun={console.activeRun}
      consoleStatus={console.consoleStatus}
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
        <div className="dashboard-primary">
          {launcher}
          <RunProgressPanel
            run={console.activeRun}
            status={console.consoleStatus}
            agents={console.activeRun ? console.agents : []}
            events={console.activeRun ? console.events : []}
            error={console.runError}
            verificationError={console.errors.verification}
            confirmingVerification={console.loading.verification}
            onConfirmVerification={() => void console.confirmVerification()}
          />
          <ResultShortcuts
            report={console.viewedReport}
            evidence={console.viewedEvidence}
            evaluation={console.viewedEvaluation}
            status={console.viewedStatus}
            onViewChange={setActiveView}
          />
        </div>
        <div className="dashboard-report">{reportPreview}</div>
        <div className="dashboard-foldouts">
          <details className="workbench-foldout">
            <summary>
              <strong>Evidence / Screenshots</strong>
              <span>{console.viewedEvidence?.evidence.length ?? 0} evidence items</span>
            </summary>
            {evidenceSnapshot}
          </details>
          <details className="workbench-foldout">
            <summary>
              <strong>Run History</strong>
              <span>{console.recentRuns.length} local runs</span>
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
