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

export function RunHistoryPanel({
  runs,
  activeRunId,
  selectedRunId,
  loading = false,
  error,
  onRefresh,
  onSelectRun,
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
          <h2 id="run-history-title">Run History</h2>
          <p>{loading && runs.length === 0 ? "Loading run history..." : `${filteredRuns.length} of ${runs.length} runs shown.`}</p>
        </div>
        {onRefresh ? (
          <button type="button" onClick={onRefresh} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        ) : null}
      </div>

      {isViewingHistoricalRun ? (
        <div className="source-banner source-banner-mock">
          <strong>Historical run selected</strong>
          <span>{selectedRunId} is open for report, evidence, and evaluation review. The active run remains separate.</span>
          {onClearSelection ? (
            <button type="button" onClick={onClearSelection}>
              Back to Active
            </button>
          ) : null}
        </div>
      ) : activeRunId ? (
        <div className="source-banner source-banner-api">
          <strong>Active run context</strong>
          <span>{activeRunId} is driving live agents, events, report, evidence, and evaluation.</span>
          <span />
        </div>
      ) : null}

      {error ? <ErrorState title="Run history unavailable" message={error} compact /> : null}
      {loading && runs.length > 0 ? <p className="loading-line">Refreshing run list...</p> : null}

      <div className="filter-row history-filters" aria-label="Run history filters">
        <label className="field" style={{ flex: "1 1 260px", marginBottom: 0 }}>
          <span>Search</span>
          <input value={query} placeholder="run id or research goal" onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="field" style={{ flex: "0 1 180px", marginBottom: 0 }}>
          <span>Status</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">all</option>
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
          <EmptyState title="No runs yet" message="Start a mock run to create the first run directory." compact />
        ) : null}
        {runs.length > 0 && filteredRuns.length === 0 ? (
          <EmptyState title="No matching runs" message="Try a different search or status filter." compact />
        ) : null}
        {filteredRuns.map((run) => {
          const isActive = run.id === activeRunId;
          const isSelected = run.id === selectedRunId;
          return (
            <article key={run.id} className={`run-row run-row-card ${isSelected ? "selected" : ""}`.trim()}>
              <div>
                <strong>{run.run_id}</strong>
                <span>{formatDate(run.created_at)}</span>
                <span>{run.research_goal}</span>
                <div className="metric-row">
                  <span>{run.mode}</span>
                  <span>{formatProgress(run)} complete</span>
                  {run.report_exists ? <span className="status-badge status-done">Report ready</span> : null}
                  {run.evidence_exists ? <span className="status-badge status-done">Evidence ready</span> : null}
                </div>
                <details className="debug-details run-debug-details">
                  <summary>Run details</summary>
                  <dl className="detail-list">
                    <div>
                      <dt>Run dir</dt>
                      <dd>{run.run_dir}</dd>
                    </div>
                    <div>
                      <dt>Report</dt>
                      <dd>{run.report_exists ? "available" : "not available"}</dd>
                    </div>
                    <div>
                      <dt>Evidence</dt>
                      <dd>{run.evidence_exists ? "available" : "not available"}</dd>
                    </div>
                    <div>
                      <dt>Evaluation</dt>
                      <dd>{run.evaluation_exists ? "available" : "not available"}</dd>
                    </div>
                    <div>
                      <dt>Screenshots</dt>
                      <dd>{run.screenshot_count}</dd>
                    </div>
                  </dl>
                </details>
              </div>
              <div className="artifact-strip">
                <StatusBadge status={run.status} />
                {isActive ? <span className="status-badge status-running">Active</span> : null}
                {isSelected && !isActive ? <span className="status-badge status-done">Viewing</span> : null}
                {onSelectRun ? (
                  <button type="button" onClick={() => onSelectRun(run.id)}>
                    Open
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
