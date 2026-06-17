import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { StatusBadge } from "../StatusBadge";
import type { RunSummary } from "../../types/contracts";
import { toConsoleStatus } from "../../types/contracts";

interface RecentRunsListProps {
  runs: RunSummary[];
  loading?: boolean;
  error?: string | null;
  onSelectRun?: (runId: string) => void;
}

export function RecentRunsList({ runs, loading = false, error, onSelectRun }: RecentRunsListProps) {
  return (
    <section className="panel compact-panel" aria-labelledby="recent-runs-title">
      <div className="panel-header">
        <div>
          <h2 id="recent-runs-title">Recent Runs</h2>
          <p>{loading ? "Loading run history..." : `${runs.length} local runs available.`}</p>
        </div>
      </div>

      {error ? <ErrorState title="Run history unavailable" message={error} compact /> : null}

      <div className="run-list">
        {runs.length === 0 && !loading ? (
          <EmptyState title="No runs yet" message="Start a mock run to create the first run directory." compact />
        ) : null}
        {runs.map((run) => {
          const content = (
            <>
              <div>
                <strong>{run.id}</strong>
                <span>{run.research_goal}</span>
              </div>
              <StatusBadge status={toConsoleStatus(run.status)} />
            </>
          );

          return onSelectRun ? (
            <button key={run.id} type="button" className="run-row run-row-button" onClick={() => onSelectRun(run.id)}>
              {content}
            </button>
          ) : (
            <article key={run.id} className="run-row">
              {content}
            </article>
          );
        })}
      </div>
    </section>
  );
}
