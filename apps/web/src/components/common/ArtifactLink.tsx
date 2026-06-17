import type { Artifact } from "../../types/contracts";
import { runApiPath } from "../../api/paths";

interface ArtifactLinkProps {
  artifact?: Artifact | null;
  artifactId?: string | null;
  artifacts?: Artifact[];
  runId?: string | null;
  label?: string;
  disabledReason?: string;
  className?: string;
}

function resolveArtifact(
  artifact: Artifact | null | undefined,
  artifactId: string | null | undefined,
  artifacts: Artifact[] | undefined,
): Artifact | null {
  if (artifact) {
    return artifact;
  }

  if (!artifactId) {
    return null;
  }

  return artifacts?.find((item) => item.id === artifactId) ?? null;
}

export function ArtifactLink({
  artifact,
  artifactId,
  artifacts,
  runId,
  label,
  disabledReason,
  className,
}: ArtifactLinkProps) {
  const resolvedArtifact = resolveArtifact(artifact, artifactId, artifacts);
  const resolvedId = resolvedArtifact?.id ?? artifactId ?? null;
  const resolvedRunId = runId ?? resolvedArtifact?.run_id ?? null;
  const text = label ?? resolvedArtifact?.title ?? resolvedId ?? "Artifact";

  if (!resolvedId || !resolvedRunId || disabledReason) {
    return (
      <span className={`artifact-link artifact-link-disabled ${className ?? ""}`.trim()} title={disabledReason}>
        {text}
      </span>
    );
  }

  const href = runApiPath(resolvedRunId, `/artifacts/${encodeURIComponent(resolvedId)}/content`);

  return (
    <a className={`artifact-link ${className ?? ""}`.trim()} href={href} target="_blank" rel="noreferrer">
      {text}
    </a>
  );
}
