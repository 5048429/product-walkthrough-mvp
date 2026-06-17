import { AgentStatusBoard } from "../components/agents/AgentStatusBoard";
import { EvidenceSnapshot } from "../components/evidence/EvidenceSnapshot";
import { EvaluationSummary } from "../components/evaluation/EvaluationSummary";
import { EventLog } from "../components/events/EventLog";
import { AppShell } from "../components/layout/AppShell";
import { TopRunContextBar } from "../components/layout/TopRunContextBar";
import { ReportPreview } from "../components/reports/ReportPreview";
import { RunHistoryPanel } from "../components/runs/RunHistoryPanel";
import { RunLauncher } from "../components/runs/RunLauncher";
import { useProdwalkConsole } from "../hooks/useProdwalkConsole";

export function ConsolePage() {
  const console = useProdwalkConsole();
  const viewedRunError = console.viewingHistory
    ? console.errors.historyRun
    : console.viewedStatus === "failed"
      ? console.runError
      : null;

  const startTopMockRun = () => {
    void console.startRun({
      mode: "mock",
      concurrency: 3,
      reportLanguage: console.selectedPlan?.report_language ?? "zh",
      browserMaxSteps: 25,
      verificationMode: "off",
    });
  };

  const startTopBrowserRun = () => {
    void console.startRun({
      mode: "browser-use",
      concurrency: 3,
      reportLanguage: console.selectedPlan?.report_language ?? "zh",
      browserMaxSteps: 25,
      verificationMode: "manual",
    });
  };

  return (
    <AppShell
      topBar={
        <TopRunContextBar
          activeRun={console.activeRun}
          selectedPlan={console.selectedPlan}
          consoleStatus={console.consoleStatus}
          source={console.source}
          connectionState={console.connectionState}
          onStartMock={startTopMockRun}
          onStartBrowser={startTopBrowserRun}
          onRetryApi={console.retryApi}
        />
      }
      left={
        <div className="stack">
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
          <RunHistoryPanel
            runs={console.recentRuns}
            activeRunId={console.activeRunId}
            selectedRunId={console.viewingHistory ? console.selectedHistoryRunId : console.activeRunId}
            loading={console.loading.initial || console.loading.runHistory}
            error={console.errors.runHistory}
            onRefresh={() => void console.refreshRunHistory()}
            onSelectRun={console.selectRun}
            onClearSelection={console.clearHistorySelection}
          />
          <EvaluationSummary
            evaluation={console.viewedEvaluation}
            run={console.viewedRun}
            status={console.viewedStatus}
            loading={console.viewedEvaluationLoading}
            error={console.viewedEvaluationError}
            viewingHistory={console.viewingHistory}
          />
        </div>
      }
      main={<AgentStatusBoard agents={console.activeRun ? console.agents : []} consoleStatus={console.consoleStatus} />}
      right={
        <EventLog
          events={console.activeRun ? console.events : []}
          activeRunId={console.activeRunId}
          connectionState={console.connectionState}
          loading={console.loading.activeRun}
          error={console.errors.activeRun}
          source={console.source}
        />
      }
      bottom={
        <div className="bottom-grid">
          <ReportPreview
            report={console.viewedRun ? console.viewedReport : null}
            artifacts={console.viewedArtifacts}
            status={console.viewedStatus}
            error={console.viewedReportError ?? viewedRunError}
            evaluationError={console.viewedEvaluationError}
            loading={console.viewedReportLoading}
          />
          <EvidenceSnapshot
            evidence={console.viewedRun ? console.viewedEvidence : null}
            artifacts={console.viewedArtifacts}
            status={console.viewedStatus}
            error={console.viewedEvidenceError ?? viewedRunError}
            loading={console.viewedEvidenceLoading}
          />
        </div>
      }
    />
  );
}
