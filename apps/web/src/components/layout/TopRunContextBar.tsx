import { StatusBadge } from "../StatusBadge";
import type { ConsoleStatus, PlanSummary, RunDetail } from "../../types/contracts";

interface TopRunContextBarProps {
  activeRun: RunDetail | null;
  selectedPlan: PlanSummary | undefined;
  consoleStatus: ConsoleStatus;
  onStartMock: () => void;
  onOpenReport: () => void;
  canOpenReport: boolean;
  startDisabled?: boolean;
}

function formatElapsed(run: RunDetail | null): string {
  if (!run?.started_at) {
    return "--";
  }

  const started = Date.parse(run.started_at);
  const end = run.completed_at ? Date.parse(run.completed_at) : Date.now();
  const seconds = Math.max(0, Math.floor((end - started) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;

  return `${minutes}m ${remainder}s`;
}

function formatProgress(run: RunDetail | null): string {
  if (!run || run.progress.total_scenarios === 0) {
    return "--";
  }

  return `${run.progress.completed_scenarios}/${run.progress.total_scenarios}`;
}

export function TopRunContextBar({
  activeRun,
  selectedPlan,
  consoleStatus,
  onStartMock,
  onOpenReport,
  canOpenReport,
  startDisabled = false,
}: TopRunContextBarProps) {
  return (
    <div className="top-context-bar">
      <div className="brand-block">
        <div className="app-title">Prodwalk PM Workbench</div>
        <div className="app-subtitle">{selectedPlan?.title ?? "Choose a local research plan"}</div>
      </div>

      <div className="context-grid">
        <div>
          <span className="context-label">Plan</span>
          <strong>{selectedPlan?.path ?? "No plan selected"}</strong>
        </div>
        <div>
          <span className="context-label">Mode</span>
          <strong>{activeRun?.mode ?? "mock"}</strong>
        </div>
        <div>
          <span className="context-label">Status</span>
          <StatusBadge status={consoleStatus} />
        </div>
        <div>
          <span className="context-label">Progress</span>
          <strong>{formatProgress(activeRun)}</strong>
        </div>
        <div>
          <span className="context-label">Elapsed</span>
          <strong>{formatElapsed(activeRun)}</strong>
        </div>
        <div>
          <span className="context-label">Run</span>
          <strong>{activeRun?.id ?? "No active run"}</strong>
        </div>
      </div>

      <div className="top-actions" aria-label="Run actions">
        <button type="button" className="primary-action" onClick={onStartMock} disabled={startDisabled}>
          Start Mock Run
        </button>
        <button type="button" disabled title="Stop is not wired in this console yet.">
          Stop
        </button>
        <button type="button" onClick={onOpenReport} disabled={!canOpenReport}>
          Open Report
        </button>
      </div>
    </div>
  );
}
