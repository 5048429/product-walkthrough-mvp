import { StatusBadge } from "../StatusBadge";
import type { ConsoleStatus, PlanSummary, RunDetail } from "../../types/contracts";
import { labelMode } from "../../i18n/zh";

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

  return `${minutes}分 ${remainder}秒`;
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
        <div className="app-title">Prodwalk 产品走查工作台</div>
        <div className="app-subtitle">{selectedPlan?.title ?? "选择一个本地走查计划"}</div>
      </div>

      <div className="context-grid">
        <div>
          <span className="context-label">计划</span>
          <strong>{selectedPlan?.path ?? "未选择计划"}</strong>
        </div>
        <div>
          <span className="context-label">模式</span>
          <strong>{labelMode(activeRun?.mode ?? "mock")}</strong>
        </div>
        <div>
          <span className="context-label">状态</span>
          <StatusBadge status={consoleStatus} />
        </div>
        <div>
          <span className="context-label">进度</span>
          <strong>{formatProgress(activeRun)}</strong>
        </div>
        <div>
          <span className="context-label">耗时</span>
          <strong>{formatElapsed(activeRun)}</strong>
        </div>
        <div>
          <span className="context-label">任务</span>
          <strong>{activeRun?.id ?? "暂无运行任务"}</strong>
        </div>
      </div>

      <div className="top-actions" aria-label="Run actions">
        <button type="button" className="primary-action" onClick={onStartMock} disabled={startDisabled}>
          启动模拟走查
        </button>
        <button type="button" disabled title="停止功能尚未完整接入。">
          停止
        </button>
        <button type="button" onClick={onOpenReport} disabled={!canOpenReport}>
          打开报告
        </button>
      </div>
    </div>
  );
}
