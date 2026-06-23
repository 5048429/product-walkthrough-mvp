import { useMemo, useState } from "react";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { StatusBadge } from "../StatusBadge";
import type { RunSummary } from "../../types/contracts";

interface RunHistoryPanelProps {
  runs: RunSummary[];
  activeRunId: string | null;
  selectedRunId: string | null;
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
  onSelectRun?: (runId: string) => void;
  onDeleteRun?: (runId: string) => void;
  onClearRuns?: () => void;
  onClearSelection?: () => void;
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "Unknown time";
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatProgress(run: RunSummary): string {
  if (run.progress.total_scenarios === 0) {
    return "--";
  }

  return `${run.progress.completed_scenarios}/${run.progress.total_scenarios}`;
}

function metadataString(run: RunSummary, key: string): string | null {
  const value = run.metadata?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function RunHistoryPanel({
  runs,
  activeRunId,
  selectedRunId,
  loading = false,
  error,
  onRefresh,
  onSelectRun,
  onDeleteRun,
  onClearRuns,
  onClearSelection,
}: RunHistoryPanelProps) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const isViewingHistoricalRun = Boolean(selectedRunId && selectedRunId !== activeRunId);
  const statuses = useMemo(
    () => Array.from(new Set(runs.map((run) => run.status))).sort(),
    [runs],
  );
  const filteredRuns = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return runs
      .filter((run) => statusFilter === "all" || run.status === statusFilter)
      .filter((run) => {
        if (!normalizedQuery) {
          return true;
        }

        return [run.id, run.run_id, run.research_goal, run.mode]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      });
  }, [query, runs, statusFilter]);

  return (
    <section className="panel compact-panel" aria-labelledby="run-history-title">
      <div className="panel-header">
        <div>
          <h2 id="run-history-title">历史任务</h2>
          <p>{loading && runs.length === 0 ? "正在读取历史任务..." : `显示 ${filteredRuns.length} / ${runs.length} 条记录。`}</p>
        </div>
        <div className="button-row history-actions">
          {onRefresh ? (
            <button type="button" onClick={onRefresh} disabled={loading}>
              {loading ? "刷新中..." : "刷新"}
            </button>
          ) : null}
          {onClearRuns ? (
            <button type="button" onClick={onClearRuns} disabled={loading || runs.length === 0}>
              清空历史记录
            </button>
          ) : null}
        </div>
      </div>

      {isViewingHistoricalRun ? (
        <div className="source-banner source-banner-mock">
          <strong>正在查看历史任务</strong>
          <span>{selectedRunId} 已打开用于查看报告、证据和评分；当前运行任务仍保持独立。</span>
          {onClearSelection ? (
            <button type="button" onClick={onClearSelection}>
              返回当前任务
            </button>
          ) : null}
        </div>
      ) : activeRunId ? (
        <div className="source-banner source-banner-api">
          <strong>当前任务上下文</strong>
          <span>{activeRunId} 正在驱动实时 Agent、事件、报告、证据和评分。</span>
          <span />
        </div>
      ) : null}

      {error ? <ErrorState title="历史任务暂不可用" message={error} compact /> : null}
      {loading && runs.length > 0 ? <p className="loading-line">正在刷新任务列表...</p> : null}

      <div className="filter-row history-filters" aria-label="Run history filters">
        <label className="field" style={{ flex: "1 1 260px", marginBottom: 0 }}>
          <span>搜索</span>
          <input value={query} placeholder="run id 或走查目标" onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="field" style={{ flex: "0 1 180px", marginBottom: 0 }}>
          <span>状态</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">全部</option>
            {statuses.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="run-list">
        {runs.length === 0 && !loading ? (
          <EmptyState title="暂无任务记录" message="启动走查后，这里会显示本地任务记录。" compact />
        ) : null}
        {runs.length > 0 && filteredRuns.length === 0 ? (
          <EmptyState title="没有匹配记录" message="换一个搜索词或状态筛选试试。" compact />
        ) : null}
        {filteredRuns.map((run) => {
          const isActive = run.id === activeRunId;
          const isSelected = run.id === selectedRunId;
          const retryOfRunId = metadataString(run, "retry_of_run_id");
          const retryRunId = metadataString(run, "retry_run_id");
          const verificationSessionId = metadataString(run, "verification_session_id");
          return (
            <article key={run.id} className={`run-row run-row-card ${isSelected ? "selected" : ""}`.trim()}>
              <div>
                <strong>{run.run_id}</strong>
                <span>{formatDate(run.created_at)}</span>
                <span>{run.research_goal}</span>
                <div className="metric-row">
                  <span>{run.mode}</span>
                  <span>{formatProgress(run)} 完成</span>
                  {run.report_exists ? <span className="status-badge status-done">报告可用</span> : null}
                  {run.evidence_exists ? <span className="status-badge status-done">证据可用</span> : null}
                  {retryOfRunId ? <span className="status-badge status-running">续跑自 {retryOfRunId}</span> : null}
                  {retryRunId ? <span className="status-badge status-running">已续跑 {retryRunId}</span> : null}
                  {verificationSessionId ? <span className="status-badge status-awaiting_verification">Auth {verificationSessionId}</span> : null}
                </div>
                <details className="debug-details run-debug-details">
                  <summary>Run details</summary>
                  <dl className="detail-list">
                    <div>
                      <dt>运行目录</dt>
                      <dd>{run.run_dir}</dd>
                    </div>
                    <div>
                      <dt>报告</dt>
                      <dd>{run.report_exists ? "可用" : "不可用"}</dd>
                    </div>
                    <div>
                      <dt>证据</dt>
                      <dd>{run.evidence_exists ? "可用" : "不可用"}</dd>
                    </div>
                    <div>
                      <dt>评分</dt>
                      <dd>{run.evaluation_exists ? "可用" : "不可用"}</dd>
                    </div>
                    <div>
                      <dt>截图</dt>
                      <dd>{run.screenshot_count}</dd>
                    </div>
                  </dl>
                </details>
              </div>
              <div className="artifact-strip">
                <StatusBadge status={run.status} />
                {isActive ? <span className="status-badge status-running">当前</span> : null}
                {isSelected && !isActive ? <span className="status-badge status-done">查看中</span> : null}
                {onSelectRun ? (
                  <button type="button" onClick={() => onSelectRun(run.id)}>
                    打开
                  </button>
                ) : null}
                {onDeleteRun ? (
                  <button type="button" onClick={() => onDeleteRun(run.id)} disabled={loading || isActive}>
                    删除
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
