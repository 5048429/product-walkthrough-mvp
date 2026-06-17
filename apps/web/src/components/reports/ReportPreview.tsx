import { useMemo, useState } from "react";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { ReportMarkdown, extractHeadings } from "./ReportMarkdown";
import { ReportToolbar } from "./ReportToolbar";
import type { Artifact, ConsoleStatus, ReportResponse } from "../../types/contracts";

interface ReportPreviewProps {
  report: ReportResponse | null;
  artifacts?: Artifact[];
  status?: ConsoleStatus;
  error?: string | null;
  evaluationError?: string | null;
  loading?: boolean;
}

function inferStatus(report: ReportResponse | null, status?: ConsoleStatus): ConsoleStatus {
  if (status) {
    return status;
  }

  return report?.markdown.trim() ? "done" : "idle";
}

function formatScore(value: number): string {
  return value <= 1 ? `${Math.round(value * 100)}%` : String(value);
}

function getReportState(
  status: ConsoleStatus,
  hasMarkdown: boolean,
  error: string | null | undefined,
): { kind: "ready" | "empty" | "error"; title: string; message: string; tone?: "failed" | "blocked" } {
  if (error && !hasMarkdown) {
    return {
      kind: "error",
      title: "Report artifact unavailable",
      message: error,
      tone: "failed",
    };
  }

  if (status === "idle") {
    return {
      kind: "empty",
      title: "Report not ready",
      message: "Select or start a run before opening the report preview.",
    };
  }

  if (status === "running" && !hasMarkdown) {
    return {
      kind: "empty",
      title: "Report is still running",
      message: "The report writer has not produced report.md yet. This preview will show the artifact when it arrives.",
    };
  }

  if (status === "awaiting_verification" && !hasMarkdown) {
    return {
      kind: "error",
      title: "Report waiting for verification",
      message: "The browser-use run is waiting for manual verification acknowledgement before a final report is available.",
      tone: "blocked",
    };
  }

  if (status === "blocked" && !hasMarkdown) {
    return {
      kind: "error",
      title: "Report blocked",
      message: "The run is blocked before report.md was generated. Partial evidence remains reviewable.",
      tone: "blocked",
    };
  }

  if (status === "failed" && !hasMarkdown) {
    return {
      kind: "error",
      title: "Report read failed",
      message: "The run failed before a readable Markdown report was available.",
      tone: "failed",
    };
  }

  if (!hasMarkdown) {
    return {
      kind: "empty",
      title: "Empty report.md",
      message: "The run has a report response, but the Markdown body is empty.",
    };
  }

  return {
    kind: "ready",
    title: "",
    message: "",
  };
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back to the legacy selection path below.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "0";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, value.length);

  try {
    const copied = document.execCommand("copy");

    if (!copied) {
      throw new Error("Browser copy command was rejected.");
    }
  } finally {
    document.body.removeChild(textarea);
  }
}

function downloadMarkdown(markdown: string): void {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "report.md";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
}

export function ReportPreview({ report, artifacts, status, error, evaluationError, loading = false }: ReportPreviewProps) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const markdown = report?.markdown ?? "";
  const hasMarkdown = markdown.trim().length > 0;
  const effectiveStatus = inferStatus(report, status);
  const state = getReportState(effectiveStatus, hasMarkdown, error);
  const headings = useMemo(() => extractHeadings(markdown), [markdown]);
  const resolvedArtifacts = artifacts ?? report?.artifacts ?? [];

  async function handleCopyMarkdown() {
    if (!hasMarkdown) {
      return;
    }

    try {
      await copyText(markdown);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }

    window.setTimeout(() => setCopyState("idle"), 1800);
  }

  function handleDownloadMarkdown() {
    if (!hasMarkdown) {
      return;
    }

    downloadMarkdown(markdown);
  }

  return (
    <section className="panel report-panel" aria-labelledby="report-preview-title">
      <div className="panel-header report-header">
        <div>
          <h2 id="report-preview-title">Report Preview</h2>
          <p>{report ? `Markdown report / ${report.language ?? "default language"}` : "No report selected"}</p>
        </div>
      </div>

      <ReportToolbar
        report={report}
        artifacts={resolvedArtifacts}
        status={effectiveStatus}
        copyState={copyState}
        onCopyMarkdown={handleCopyMarkdown}
        onDownloadMarkdown={handleDownloadMarkdown}
      />

      {loading && !hasMarkdown ? (
        <EmptyState title="Loading report" message="Reading report.md and evaluation.json from the API." />
      ) : null}
      {!loading && state.kind === "empty" ? <EmptyState title={state.title} message={state.message} /> : null}
      {state.kind === "error" ? (
        <ErrorState title={state.title} message={state.message} tone={state.tone} details={error ?? undefined} />
      ) : null}
      {evaluationError && hasMarkdown ? (
        <ErrorState
          title="Evaluation unavailable"
          message="The Markdown report remains available while evaluation.json is missing or unreadable."
          details={evaluationError}
          compact
        />
      ) : null}
      {error && hasMarkdown ? (
        <ErrorState
          title="Report refresh issue"
          message="A cached or partial Markdown report is visible, but the latest report request returned an error."
          details={error}
          compact
        />
      ) : null}

      {hasMarkdown ? (
        <div className="report-layout">
          <article className="markdown-preview" aria-label="Markdown report">
            {loading ? (
              <div className="partial-banner partial-banner-running">
                <strong>Refreshing report</strong>
                <span>Reading the latest report.md from the API.</span>
              </div>
            ) : null}
            {effectiveStatus === "running" ||
            effectiveStatus === "awaiting_verification" ||
            effectiveStatus === "blocked" ||
            effectiveStatus === "failed" ? (
              <div className={`partial-banner partial-banner-${effectiveStatus}`}>
                <strong>{effectiveStatus === "running" ? "Partial report" : "Partial artifact retained"}</strong>
                <span>
                  {effectiveStatus === "running"
                    ? "The run is still active; this preview may update when report generation completes."
                    : effectiveStatus === "awaiting_verification"
                      ? "The report remains visible while browser-use waits for manual verification acknowledgement."
                      : "The report remains visible even though the run did not finish cleanly."}
                </span>
              </div>
            ) : null}
            <ReportMarkdown markdown={markdown} artifacts={resolvedArtifacts} runId={report?.run_id} />
          </article>

          <aside className="evaluation-panel">
            <div className="section-title">Outline</div>
            {headings.length > 0 ? (
              <ol className="outline-list">
                {headings.map((heading) => (
                  <li key={heading.id} className={`outline-level-${heading.level}`}>
                    <a href={`#${heading.id}`}>{heading.text}</a>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState
                title="No headings"
                message="The Markdown report does not include outline headings yet."
                compact
              />
            )}

            <div className="section-title evaluation-title">Evaluation</div>
            {report?.evaluation ? (
              <>
                <div className="score-display">{formatScore(report.evaluation.overall_score)}</div>
                <dl className="score-list">
                  {Object.entries(report.evaluation.scores).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{formatScore(value)}</dd>
                    </div>
                  ))}
                </dl>
                <ul className="notes-list">
                  {report.evaluation.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </>
            ) : (
              <EmptyState
                title="Evaluation unavailable"
                message="Report Markdown can still be reviewed while evaluation.json is missing."
                compact
              />
            )}
          </aside>
        </div>
      ) : null}
    </section>
  );
}
