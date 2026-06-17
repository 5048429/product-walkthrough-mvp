import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { StatusBadge } from "../StatusBadge";
import type { ConsoleStatus, EvaluationResponse, RunSummary } from "../../types/contracts";

interface EvaluationSummaryProps {
  evaluation: EvaluationResponse | null;
  run: RunSummary | null;
  status: ConsoleStatus;
  loading?: boolean;
  error?: string | null;
  viewingHistory?: boolean;
}

function formatScore(value: number): string {
  return value <= 1 ? `${Math.round(value * 100)}%` : String(value);
}

function formatScoreLabel(key: string): string {
  return key.replaceAll("_", " ");
}

export function EvaluationSummary({
  evaluation,
  run,
  status,
  loading = false,
  error,
  viewingHistory = false,
}: EvaluationSummaryProps) {
  return (
    <section className="panel compact-panel" aria-labelledby="evaluation-summary-title">
      <div className="panel-header">
        <div>
          <h2 id="evaluation-summary-title">Evaluation</h2>
          <p>
            {run
              ? `${viewingHistory ? "Historical" : "Active"} run / ${evaluation?.artifact_id ?? "evaluation.json"}`
              : "No run selected"}
          </p>
        </div>
        <StatusBadge status={status} />
      </div>

      {loading && !evaluation ? (
        <EmptyState title="Loading evaluation" message="Reading evaluation.json from the API." compact />
      ) : null}
      {error && !evaluation ? (
        <ErrorState
          title="Evaluation unavailable"
          message="evaluation.json is missing or unreadable for this run."
          details={error}
          compact
        />
      ) : null}
      {!loading && !error && !evaluation ? (
        <EmptyState
          title="No evaluation selected"
          message="Start a run or select a historical run with evaluation.json."
          compact
        />
      ) : null}

      {evaluation ? (
        <>
          <div className="score-display">{formatScore(evaluation.overall_score)}</div>
          <dl className="score-list">
            {Object.entries(evaluation.scores).map(([key, value]) => (
              <div key={key}>
                <dt>{formatScoreLabel(key)}</dt>
                <dd>{formatScore(value)}</dd>
              </div>
            ))}
          </dl>
          {evaluation.notes.length > 0 ? (
            <ul className="notes-list">
              {evaluation.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No notes" message="The evaluation artifact did not include reviewer notes." compact />
          )}
        </>
      ) : null}
    </section>
  );
}
