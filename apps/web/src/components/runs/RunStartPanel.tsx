import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "../StatusBadge";
import type { ConsoleDataSource, ConsoleErrorState, ConsoleLoadingState, StartRunOptions } from "../../hooks/useProdwalkConsole";
import type {
  ConsoleStatus,
  HealthResponse,
  PlanDetailResponse,
  PlanSummary,
  RunDetail,
  RunMode,
  VerificationMode,
} from "../../types/contracts";
import { formatApiError } from "../../types/contracts";
import { PlanSelector } from "./PlanSelector";
import { RunModeSelector } from "./RunModeSelector";

const consoleStates: ConsoleStatus[] = ["idle", "running", "done", "blocked", "failed", "timeout"];

interface RunStartPanelProps {
  source: ConsoleDataSource;
  health: HealthResponse | null;
  plans: PlanSummary[];
  selectedPlanId: string;
  selectedPlanDetail: PlanDetailResponse | null;
  activeRun: RunDetail | null;
  consoleStatus: ConsoleStatus;
  loading: ConsoleLoadingState;
  errors: ConsoleErrorState;
  onPlanChange: (planId: string) => void;
  onStartRun: (options: StartRunOptions) => void;
  onMockStatusChange: (status: ConsoleStatus) => void;
  onRetryApi: () => void;
}

function getStateCopy(status: ConsoleStatus, source: ConsoleDataSource): string {
  if (source === "mock") {
    return "Mock fallback is active. The UI is previewing local fixtures because the API is unavailable.";
  }

  switch (status) {
    case "idle":
      return "No active run. Select a local plan before starting.";
    case "running":
      return "Run is active. Agent status and events are updating from API events.";
    case "done":
      return "Run completed. Report, evidence, and evaluation artifacts are available.";
    case "blocked":
      return "Run is blocked by manual verification. Partial evidence remains reviewable.";
    case "failed":
      return "Run failed. Existing events and partial artifacts remain visible.";
    case "timeout":
      return "Run timed out. Partial evidence and diagnostics remain visible.";
    default:
      return "Unknown run state.";
  }
}

function getCompletion(run: RunDetail | null): number {
  if (!run || run.progress.total_scenarios === 0) {
    return 0;
  }

  return Math.round((run.progress.completed_scenarios / run.progress.total_scenarios) * 100);
}

export function RunStartPanel({
  source,
  health,
  plans,
  selectedPlanId,
  selectedPlanDetail,
  activeRun,
  consoleStatus,
  loading,
  errors,
  onPlanChange,
  onStartRun,
  onMockStatusChange,
  onRetryApi,
}: RunStartPanelProps) {
  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId || plan.path === selectedPlanId);
  const [mode, setMode] = useState<RunMode>("mock");
  const [concurrency, setConcurrency] = useState(3);
  const [reportLanguage, setReportLanguage] = useState(selectedPlan?.report_language ?? "zh");
  const [browserMaxSteps, setBrowserMaxSteps] = useState(25);
  const [browserTimeoutSec, setBrowserTimeoutSec] = useState(600);
  const [browserUserDataDir, setBrowserUserDataDir] = useState("");
  const [browserStorageState, setBrowserStorageState] = useState("");
  const [verificationMode, setVerificationMode] = useState<VerificationMode>("auto");
  const [verificationTimeoutSec, setVerificationTimeoutSec] = useState(300);
  const [verificationSuccessUrlContains, setVerificationSuccessUrlContains] = useState("");
  const [verificationLoginUrlContains, setVerificationLoginUrlContains] = useState("/auth/login");

  const completion = getCompletion(activeRun);
  const activeRunError = formatApiError(activeRun?.error);
  const isBrowserUse = mode === "browser-use";
  const resolvedConcurrency = isBrowserUse ? 1 : concurrency;
  const successUrlContains = useMemo(
    () =>
      verificationSuccessUrlContains
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [verificationSuccessUrlContains],
  );
  const launchPayload = useMemo(
    () => ({
      config_path: selectedPlan?.path ?? null,
      plan: null,
      mode,
      out: "runs",
      concurrency: resolvedConcurrency,
      report_language: reportLanguage,
      browser_model: null,
      browser_max_steps: browserMaxSteps,
      browser_timeout_sec: browserTimeoutSec,
      browser_user_data_dir: browserUserDataDir.trim() || null,
      browser_storage_state: browserStorageState.trim() || null,
      verification_mode: isBrowserUse ? verificationMode : "off",
      verification_timeout_sec: verificationTimeoutSec,
      verification_success_url_contains: successUrlContains,
      verification_login_url_contains: verificationLoginUrlContains,
    }),
    [
      browserMaxSteps,
      browserStorageState,
      browserTimeoutSec,
      browserUserDataDir,
      isBrowserUse,
      mode,
      reportLanguage,
      resolvedConcurrency,
      selectedPlan?.path,
      successUrlContains,
      verificationLoginUrlContains,
      verificationMode,
      verificationTimeoutSec,
    ],
  );

  useEffect(() => {
    if (selectedPlan?.report_language) {
      setReportLanguage(selectedPlan.report_language);
    }
  }, [selectedPlan?.report_language]);

  function handleModeChange(nextMode: RunMode) {
    onStartRun({
      mode: nextMode,
      concurrency: nextMode === "browser-use" ? 1 : concurrency,
      reportLanguage,
      browserMaxSteps,
      browserTimeoutSec,
      browserUserDataDir,
      browserStorageState,
      verificationMode: nextMode === "mock" ? "off" : verificationMode,
      verificationTimeoutSec,
      verificationSuccessUrlContains: successUrlContains,
      verificationLoginUrlContains,
    });
  }

  function handleModeSelect(nextMode: RunMode) {
    setMode(nextMode);
    if (nextMode === "mock") {
      setConcurrency(3);
    } else {
      setConcurrency(1);
      setVerificationMode("auto");
    }
  }

  return (
    <section className="panel launcher-panel" aria-labelledby="run-start-title">
      <div className="panel-header">
        <div>
          <h2 id="run-start-title">Start a Run</h2>
          <p>Select a plan, choose mock or browser-use, and start the review workflow.</p>
        </div>
        <StatusBadge status={consoleStatus} />
      </div>

      {source === "mock" ? (
        <div className="source-banner source-banner-mock">
          <strong>Offline preview</strong>
          <span>{errors.initial ?? "Using local fixtures while the API is unavailable."}</span>
          <button type="button" onClick={onRetryApi}>
            Retry API
          </button>
        </div>
      ) : null}
      {errors.initial && source === "api" ? <p className="inline-warning">{errors.initial}</p> : null}
      {errors.start ? <p className="inline-warning">{errors.start}</p> : null}

      <PlanSelector plans={plans} selectedPlanId={selectedPlanId} onPlanChange={onPlanChange} />
      {loading.planDetail ? <p className="loading-line">Loading plan detail...</p> : null}
      {errors.planDetail ? <p className="inline-warning">{errors.planDetail}</p> : null}
      {selectedPlanDetail ? (
        <div className="plan-detail-line">
          Plan detail loaded from <strong>{selectedPlanDetail.path}</strong>
        </div>
      ) : null}

      <RunModeSelector
        mode={mode}
        browserMaxSteps={browserMaxSteps}
        browserTimeoutSec={browserTimeoutSec}
        browserUserDataDir={browserUserDataDir}
        browserStorageState={browserStorageState}
        verificationMode={verificationMode}
        verificationTimeoutSec={verificationTimeoutSec}
        verificationSuccessUrlContains={verificationSuccessUrlContains}
        verificationLoginUrlContains={verificationLoginUrlContains}
        onModeChange={handleModeSelect}
        onBrowserMaxStepsChange={setBrowserMaxSteps}
        onBrowserTimeoutSecChange={setBrowserTimeoutSec}
        onBrowserUserDataDirChange={setBrowserUserDataDir}
        onBrowserStorageStateChange={setBrowserStorageState}
        onVerificationModeChange={setVerificationMode}
        onVerificationTimeoutSecChange={setVerificationTimeoutSec}
        onVerificationSuccessUrlContainsChange={setVerificationSuccessUrlContains}
        onVerificationLoginUrlContainsChange={setVerificationLoginUrlContains}
      />

      <div className="button-row">
        <button
          type="button"
          className="primary-action"
          disabled={!selectedPlan || loading.start}
          onClick={() => {
            handleModeChange(mode);
          }}
        >
          {loading.start ? "Starting..." : isBrowserUse ? "Start Browser-use Run" : "Start Mock Run"}
        </button>
        <button type="button" disabled title="Stop is not wired in this console yet.">
          Stop
        </button>
      </div>

      <div className="active-summary">
        <div className="section-title">Current Run</div>
        {loading.activeRun && !activeRun ? (
          <p className="empty-copy">Loading active run...</p>
        ) : activeRun ? (
          <>
            <div className="run-id">{activeRun.id}</div>
            <p>{activeRun.research_goal}</p>
            <div className="progress-track" aria-label={`${completion}% complete`}>
              <div style={{ width: `${completion}%` }} />
            </div>
            <div className="metric-row">
              <span>{activeRun.progress.completed_scenarios}/{activeRun.progress.total_scenarios} complete</span>
              <span>{activeRun.progress.failed_scenarios} failed</span>
              <span>{activeRun.mode}</span>
            </div>
            {activeRun.status === "awaiting_verification" ? (
              <div className="verification-inline">
                <strong>Awaiting verification</strong>
                <span>Complete the visible browser checkpoint, then use the continue button in Current Run Status.</span>
              </div>
            ) : null}
            {activeRunError ? <p className="inline-warning">{activeRunError}</p> : null}
          </>
        ) : (
          <p className="empty-copy">No run context is active.</p>
        )}
      </div>

      <details className="debug-details">
        <summary>Details / Debug</summary>
        <div className={`source-banner source-banner-${source}`}>
          <strong>{source === "api" ? "API connected" : "Mock fallback"}</strong>
          <span>
            {source === "api"
              ? `${health?.service ?? "prodwalk-server"} ${health?.version ?? ""}`.trim() || "Using real FastAPI data."
              : errors.initial ?? "Using local mock fixtures."}
          </span>
          <button type="button" onClick={onRetryApi}>
            Retry API
          </button>
        </div>

        <div className="form-grid">
          <label className="field">
            <span>Concurrency</span>
            <input
              type="number"
              min="1"
              max="8"
              value={resolvedConcurrency}
              disabled={isBrowserUse}
              onChange={(event) => setConcurrency(Number(event.target.value))}
            />
          </label>
          <label className="field">
            <span>Report language</span>
            <select value={reportLanguage} onChange={(event) => setReportLanguage(event.target.value)}>
              <option value="zh">zh</option>
              <option value="en">en</option>
            </select>
          </label>
        </div>

        {source === "mock" ? (
          <div className="state-control" aria-label="Mock fallback state selector">
            {consoleStates.map((state) => (
              <button
                key={state}
                type="button"
                className={state === consoleStatus ? "selected" : ""}
                onClick={() => onMockStatusChange(state)}
              >
                {state}
              </button>
            ))}
          </div>
        ) : null}

        <div className="plan-summary">
          <div className="section-title">{source === "api" ? "API request" : "Mock request"}</div>
          <dl className="detail-list">
            {Object.entries(launchPayload).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>{String(value ?? "--")}</dd>
              </div>
            ))}
          </dl>
        </div>
      </details>
    </section>
  );
}
