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
import { labelMode } from "../../i18n/zh";
import { PlanSelector } from "./PlanSelector";
import { RunModeSelector } from "./RunModeSelector";

const consoleStates: ConsoleStatus[] = [
  "idle",
  "running",
  "awaiting_verification",
  "done",
  "blocked",
  "failed",
  "timeout",
];

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
    return "当前处于离线预览。API 不可用时，界面会展示本地示例数据。";
  }

  switch (status) {
    case "idle":
      return "暂无运行任务。请选择一个本地走查计划。";
    case "running":
      return "任务正在运行，Agent 状态和事件会实时更新。";
    case "awaiting_verification":
      return "真实浏览器走查等待人工验证确认；已有证据、截图和诊断产物仍可查看。";
    case "done":
      return "任务已完成，报告、证据和评分都可以查看。";
    case "blocked":
      return "任务需要人工处理或环境操作；已有产物仍可查看。";
    case "failed":
      return "任务失败；已有事件和部分产物仍会保留。";
    case "timeout":
      return "任务超时；已有证据和诊断信息仍可查看。";
    default:
      return "未知任务状态。";
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
  const [verificationMode, setVerificationMode] = useState<VerificationMode>("off");
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
      setVerificationMode("off");
    }
  }

  return (
    <section className="panel launcher-panel" aria-labelledby="run-start-title">
      <div className="panel-header">
        <div>
          <h2 id="run-start-title">Start a Run</h2>
          <p>选择计划和运行模式，然后启动产品走查。</p>
        </div>
        <StatusBadge status={consoleStatus} />
      </div>

      {source === "mock" ? (
        <div className="source-banner source-banner-mock">
          <strong>离线预览</strong>
          <span>{errors.initial ?? "API 不可用，当前使用本地示例数据。"}</span>
          <button type="button" onClick={onRetryApi}>
            重试 API
          </button>
        </div>
      ) : null}
      {errors.initial && source === "api" ? <p className="inline-warning">{errors.initial}</p> : null}
      {errors.start ? <p className="inline-warning">{errors.start}</p> : null}

      <PlanSelector plans={plans} selectedPlanId={selectedPlanId} onPlanChange={onPlanChange} />
      {loading.planDetail ? <p className="loading-line">正在读取计划详情...</p> : null}
      {errors.planDetail ? <p className="inline-warning">{errors.planDetail}</p> : null}
      {selectedPlanDetail ? (
        <div className="plan-detail-line">
          已读取计划：<strong>{selectedPlanDetail.path}</strong>
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
          {loading.start ? "启动中..." : isBrowserUse ? "启动真实页面测试" : "启动模拟走查"}
        </button>
        <button type="button" disabled title="停止功能尚未完整接入。">
          停止
        </button>
      </div>

      <div className="active-summary">
        <div className="section-title">当前任务</div>
        {loading.activeRun && !activeRun ? (
          <p className="empty-copy">正在加载当前任务...</p>
        ) : activeRun ? (
          <>
            <div className="run-id">{activeRun.id}</div>
            <p>{activeRun.research_goal}</p>
            <div className="progress-track" aria-label={`${completion}% complete`}>
              <div style={{ width: `${completion}%` }} />
            </div>
            <div className="metric-row">
              <span>{activeRun.progress.completed_scenarios}/{activeRun.progress.total_scenarios} 已完成</span>
              <span>{activeRun.progress.failed_scenarios} 个失败</span>
              <span>{labelMode(activeRun.mode)}</span>
            </div>
            {activeRun.status === "awaiting_verification" ? (
              <div className="verification-inline">
                <strong>等待人工验证</strong>
                <span>请在可见浏览器窗口完成登录、验证码或 MFA，然后回到当前任务区域记录验证结果。</span>
              </div>
            ) : null}
            {activeRunError ? <p className="inline-warning">{activeRunError}</p> : null}
          </>
        ) : (
          <p className="empty-copy">暂无运行中的任务。</p>
        )}
      </div>

      <details className="debug-details">
        <summary>详情 / 调试</summary>
        <div className={`source-banner source-banner-${source}`}>
          <strong>{source === "api" ? "API 已连接" : "离线示例"}</strong>
          <span>
            {source === "api"
              ? `${health?.service ?? "prodwalk-server"} ${health?.version ?? ""}`.trim() || "正在使用 FastAPI 真实数据。"
              : errors.initial ?? "正在使用本地示例数据。"}
          </span>
          <button type="button" onClick={onRetryApi}>
            重试 API
          </button>
        </div>

        <div className="form-grid">
          <label className="field">
            <span>并发数</span>
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
            <span>报告语言</span>
            <select value={reportLanguage} onChange={(event) => setReportLanguage(event.target.value)}>
              <option value="zh">中文</option>
              <option value="en">英文</option>
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
          <div className="section-title">{source === "api" ? "API 请求" : "模拟请求"}</div>
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
