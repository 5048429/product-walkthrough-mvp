import { StatusBadge } from "../StatusBadge";
import type { RunEventConnectionState } from "../../api/sse";
import type { ConsoleDataSource } from "../../hooks/useProdwalkConsole";
import type { ConsoleStatus, PlanSummary, RunDetail } from "../../types/contracts";

interface TopRunContextBarProps {
  activeRun: RunDetail | null;
  selectedPlan: PlanSummary | undefined;
  consoleStatus: ConsoleStatus;
  source: ConsoleDataSource;
  connectionState: RunEventConnectionState;
  onStartMock: () => void;
  onStartBrowser: () => void;
  onRetryApi: () => void;
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

export function TopRunContextBar({
  activeRun,
  selectedPlan,
  consoleStatus,
  source,
  connectionState,
  onStartMock,
  onStartBrowser,
  onRetryApi,
}: TopRunContextBarProps) {
  return (
    <div className="top-context-bar">
      <div className="brand-block">
        <div className="app-title">Prodwalk Console</div>
        <div className="app-subtitle">{selectedPlan?.title ?? "No plan selected"}</div>
      </div>

      <div className="context-grid">
        <div>
          <span className="context-label">Run</span>
          <strong>{activeRun?.id ?? "No active run"}</strong>
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
          <span className="context-label">Source</span>
          <strong>{source === "api" ? connectionState : "mock fallback"}</strong>
        </div>
        <div>
          <span className="context-label">Elapsed</span>
          <strong>{formatElapsed(activeRun)}</strong>
        </div>
        <div>
          <span className="context-label">Run dir</span>
          <strong>{activeRun?.run_dir ?? "runs/"}</strong>
        </div>
      </div>

      <div className="top-actions" aria-label="Run actions">
        <button type="button" onClick={onStartMock}>Start Mock</button>
        <button type="button" onClick={onStartBrowser}>Start Browser</button>
        <button type="button" disabled title="Stop is not wired in this console yet.">Stop</button>
        <button type="button" onClick={onRetryApi}>Retry API</button>
      </div>
    </div>
  );
}
