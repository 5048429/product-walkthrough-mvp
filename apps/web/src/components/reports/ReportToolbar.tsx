import { StatusBadge } from "../StatusBadge";
import { ArtifactLink } from "../common/ArtifactLink";
import type { Artifact, ConsoleStatus, ReportResponse } from "../../types/contracts";

interface ReportToolbarProps {
  report: ReportResponse | null;
  artifacts?: Artifact[];
  status: ConsoleStatus;
  copyState: "idle" | "copied" | "failed";
  onCopyMarkdown: () => void;
  onDownloadMarkdown: () => void;
}

function formatGeneratedAt(value: string | null | undefined): string {
  if (!value) {
    return "Not generated";
  }

  return new Date(value).toLocaleString();
}

function copyButtonLabel(copyState: ReportToolbarProps["copyState"]): string {
  if (copyState === "copied") {
    return "Copied";
  }

  if (copyState === "failed") {
    return "Copy failed";
  }

  return "Copy Markdown";
}

export function ReportToolbar({
  report,
  artifacts,
  status,
  copyState,
  onCopyMarkdown,
  onDownloadMarkdown,
}: ReportToolbarProps) {
  const resolvedArtifacts = artifacts ?? report?.artifacts ?? [];
  const canCopy = Boolean(report?.markdown.trim());
  const canDownload = canCopy;

  return (
    <div className="report-toolbar" aria-label="Report actions">
      <div className="toolbar-meta">
        <StatusBadge status={status} />
        <span>{formatGeneratedAt(report?.generated_at)}</span>
      </div>

      <div className="toolbar-meta report-primary-actions">
        <button type="button" onClick={onCopyMarkdown} disabled={!canCopy}>
          {copyButtonLabel(copyState)}
        </button>
        <details className="toolbar-details">
          <summary>More</summary>
          <div className="artifact-strip">
            <button type="button" onClick={onDownloadMarkdown} disabled={!canDownload}>
              Download report.md
            </button>
            <ArtifactLink
              artifactId={report?.markdown_artifact_id}
              artifacts={resolvedArtifacts}
              runId={report?.run_id}
              label="Open report source"
              disabledReason={report ? undefined : "Report artifact is not ready"}
            />
            <ArtifactLink
              artifactId={report?.evaluation_artifact_id}
              artifacts={resolvedArtifacts}
              runId={report?.run_id}
              label="Open evaluation JSON"
              disabledReason={report?.evaluation_artifact_id ? undefined : "Evaluation artifact is unavailable"}
            />
          </div>
        </details>
      </div>
    </div>
  );
}
