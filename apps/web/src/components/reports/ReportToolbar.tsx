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
    return "尚未生成";
  }

  return new Date(value).toLocaleString();
}

function copyButtonLabel(copyState: ReportToolbarProps["copyState"]): string {
  if (copyState === "copied") {
    return "已复制";
  }

  if (copyState === "failed") {
    return "复制失败";
  }

  return "复制 Markdown";
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
    <div className="report-toolbar" aria-label="报告操作">
      <div className="toolbar-meta">
        <StatusBadge status={status} />
        <span>{formatGeneratedAt(report?.generated_at)}</span>
      </div>

      <div className="toolbar-meta report-primary-actions">
        <button type="button" onClick={onCopyMarkdown} disabled={!canCopy}>
          {copyButtonLabel(copyState)}
        </button>
        <details className="toolbar-details">
          <summary>更多</summary>
          <div className="artifact-strip">
            <button type="button" onClick={onDownloadMarkdown} disabled={!canDownload}>
              下载 report.md
            </button>
            <ArtifactLink
              artifactId={report?.markdown_artifact_id}
              artifacts={resolvedArtifacts}
              runId={report?.run_id}
              label="打开报告源文件"
              disabledReason={report ? undefined : "报告产物尚未就绪"}
            />
            <ArtifactLink
              artifactId={report?.evaluation_artifact_id}
              artifacts={resolvedArtifacts}
              runId={report?.run_id}
              label="打开评分 JSON"
              disabledReason={report?.evaluation_artifact_id ? undefined : "评分产物不可用"}
            />
          </div>
        </details>
      </div>
    </div>
  );
}
