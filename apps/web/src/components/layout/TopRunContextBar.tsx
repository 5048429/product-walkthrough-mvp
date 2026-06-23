import { StatusBadge } from "../StatusBadge";
import type { ConsoleStatus, PlanSummary, RunDetail } from "../../types/contracts";
import { labelMode } from "../../i18n/zh";

interface TopRunContextBarProps {
  activeRun: RunDetail | null;
  selectedPlan: PlanSummary | undefined;
  consoleStatus: ConsoleStatus;
  onStartMock: () => void;
  onStopRun: () => void;
  onOpenReport: () => void;
  canOpenReport: boolean;
  startDisabled?: boolean;
  stopDisabled?: boolean;
}

function formatElapsed(run: RunDetail | null): string {
  if (!run?.started_at) {
    return "--";
  }

  const started = Date.parse(run.started_at);
  const end = run.completed_at ? Date.parse(run.completed_at) : Date.now();
  const seconds = Math.max(0, Math.floor((end - started) / 1000));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor(seconds / 60);
  const minuteRemainder = Math.floor((seconds % 3600) / 60);
  const secondRemainder = seconds % 60;

  if (days > 0) {
    return `${days}天 ${hours}小时`;
  }

  if (hours > 0) {
    return `${hours}小时 ${minuteRemainder}分`;
  }

  return `${minutes}分 ${secondRemainder}秒`;
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
  onStopRun,
  onOpenReport,
  canOpenReport,
  startDisabled = false,
  stopDisabled = false,
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

      <div className="top-actions" aria-label="任务操作">
        <button type="button" className="primary-action" onClick={onStartMock} disabled={startDisabled}>
          启动模拟走查
        </button>
        <button type="button" onClick={onStopRun} disabled={stopDisabled}>
          立即停止当前任务
        </button>
        <button type="button" onClick={onOpenReport} disabled={!canOpenReport}>
          打开报告
        </button>
      </div>
    </div>
  );
}
