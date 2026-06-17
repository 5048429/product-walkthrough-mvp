import { ArtifactLink } from "../common/ArtifactLink";
import { evidenceElementId } from "./evidenceFocus";
import { ScreenshotPreview } from "./ScreenshotPreview";
import type { Artifact, EvidenceItem, WalkthroughResult } from "../../types/contracts";

interface EvidenceItemCardProps {
  item: EvidenceItem;
  result?: WalkthroughResult;
  artifacts?: Artifact[];
  runId?: string | null;
  selected?: boolean;
  onSelect?: (item: EvidenceItem) => void;
}

function getEvidenceStatus(item: EvidenceItem, result?: WalkthroughResult): string {
  if (item.status) {
    return item.status;
  }

  if (item.errors?.length) {
    return "friction";
  }

  return result?.status ?? "completed";
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function normalizeStatusClass(status: string): string {
  if (status === "completed" || status === "succeeded") {
    return "done";
  }

  if (status === "awaiting_verification") {
    return "awaiting_verification";
  }

  if (status === "blocked" || status === "friction") {
    return "blocked";
  }

  if (status === "failed") {
    return "failed";
  }

  if (status === "running") {
    return "running";
  }

  return "idle";
}

export function EvidenceItemCard({ item, result, artifacts, runId, selected = false, onSelect }: EvidenceItemCardProps) {
  const status = getEvidenceStatus(item, result);
  const screenshotIds = item.screenshot_artifact_ids?.length
    ? item.screenshot_artifact_ids
    : item.screenshot_artifact_id
      ? [item.screenshot_artifact_id]
      : [];
  const primaryScreenshotId = screenshotIds[0] ?? null;

  return (
    <article id={evidenceElementId(item.id)} className={`evidence-card ${selected ? "evidence-card-selected" : ""}`.trim()}>
      <button type="button" className="evidence-card-main" onClick={() => onSelect?.(item)}>
        <div className="evidence-card-heading">
          <div>
            <strong>{item.title}</strong>
            <span>
              {item.product} / {item.scenario_title ?? item.scenario_id}
            </span>
          </div>
          <span className={`evidence-status-pill status-${normalizeStatusClass(status)}`}>{status}</span>
        </div>

        <p>{item.summary}</p>

        <dl className="evidence-meta-grid">
          <div>
            <dt>Kind</dt>
            <dd>{item.kind.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt>Confidence</dt>
            <dd>{formatConfidence(item.confidence)}</dd>
          </div>
          <div>
            <dt>Step</dt>
            <dd>{item.step_index ?? "--"}</dd>
          </div>
          <div>
            <dt>Action</dt>
            <dd>{item.action ?? "--"}</dd>
          </div>
        </dl>
      </button>

      <div className="evidence-card-side">
        <ScreenshotPreview artifactId={primaryScreenshotId} artifacts={artifacts} runId={runId} alt={item.title} />
        {screenshotIds.length > 1 ? (
          <div className="artifact-strip">
            {screenshotIds.slice(1).map((artifactId, index) => (
                <ArtifactLink
                  key={artifactId}
                  artifactId={artifactId}
                  artifacts={artifacts}
                  runId={runId}
                  label={`Screenshot ${index + 2}`}
                />
              ))}
          </div>
        ) : null}

        {item.url ? (
          <a className="evidence-url" href={item.url} target="_blank" rel="noreferrer">
            Source URL
          </a>
        ) : (
          <span className="evidence-url evidence-url-disabled">No URL</span>
        )}
      </div>

      {item.errors?.length ? (
        <div className="evidence-error-list">
          {item.errors.map((error) => (
            <span key={error}>{error}</span>
          ))}
        </div>
      ) : null}
    </article>
  );
}
