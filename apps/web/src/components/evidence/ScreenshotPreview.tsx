import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { API_BASE_URL, apiPath, runApiPath } from "../../api/paths";
import { ArtifactLink } from "../common/ArtifactLink";
import type { Artifact } from "../../types/contracts";

interface ScreenshotPreviewProps {
  artifactId?: string | null;
  artifact?: Artifact | null;
  artifacts?: Artifact[];
  runId?: string | null;
  alt?: string;
  variant?: "card" | "detail";
}

type ImageState = "missing" | "loading" | "loaded" | "failed";

function metadataString(artifact: Artifact | null | undefined, key: string): string | null {
  const value = artifact?.metadata?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function resolveArtifact(artifact: Artifact | null | undefined, artifactId: string | null | undefined, artifacts: Artifact[] | undefined): Artifact | null {
  if (artifact) {
    return artifact;
  }

  if (!artifactId) {
    return null;
  }

  return artifacts?.find((item) => item.id === artifactId) ?? null;
}

function toApiUrl(value: string): string {
  if (/^https?:\/\//i.test(value)) {
    return value;
  }

  const base = API_BASE_URL.replace(/\/+$/, "");

  if (value.startsWith("/api/")) {
    return base.endsWith("/api") ? `${base}${value.slice(4)}` : `${base}${value}`;
  }

  if (value.startsWith("/")) {
    return apiPath(value);
  }

  return apiPath(`/${value}`);
}

function getScreenshotUrl(artifact: Artifact | null, artifactId: string | null, runId: string | null): string | null {
  const metadataUrl =
    metadataString(artifact, "content_url") ??
    metadataString(artifact, "path_url") ??
    metadataString(artifact, "screenshot_url");

  if (metadataUrl) {
    return toApiUrl(metadataUrl);
  }

  const resolvedRunId = runId ?? artifact?.run_id ?? null;
  const resolvedArtifactId = artifact?.id ?? artifactId;

  if (!resolvedRunId || !resolvedArtifactId) {
    return null;
  }

  return runApiPath(resolvedRunId, `/artifacts/${encodeURIComponent(resolvedArtifactId)}/content`);
}

function isImageArtifact(artifact: Artifact | null): boolean {
  if (!artifact) {
    return true;
  }

  return artifact.type === "screenshot" || artifact.media_type.toLowerCase().startsWith("image/");
}

export function ScreenshotPreview({
  artifactId,
  artifact,
  artifacts,
  runId,
  alt = "Evidence screenshot",
  variant = "card",
}: ScreenshotPreviewProps) {
  const resolvedArtifact = resolveArtifact(artifact, artifactId, artifacts);
  const resolvedArtifactId = resolvedArtifact?.id ?? artifactId ?? null;
  const resolvedRunId = runId ?? resolvedArtifact?.run_id ?? null;
  const baseSrc = useMemo(
    () => getScreenshotUrl(resolvedArtifact, resolvedArtifactId, resolvedRunId),
    [resolvedArtifact, resolvedArtifactId, resolvedRunId],
  );
  const [imageState, setImageState] = useState<ImageState>(baseSrc ? "loading" : "missing");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    setImageState(baseSrc ? "loading" : "missing");
    setRetryCount(0);
  }, [baseSrc]);

  const src = useMemo(() => {
    if (!baseSrc) {
      return null;
    }

    if (retryCount === 0) {
      return baseSrc;
    }

    return `${baseSrc}${baseSrc.includes("?") ? "&" : "?"}retry=${retryCount}`;
  }, [baseSrc, retryCount]);

  const placeholderStyle = {
    minHeight: variant === "detail" ? 180 : 92,
    padding: 4,
    overflow: "hidden",
    placeContent: "center",
  } satisfies CSSProperties;
  const imageStyle = {
    display: imageState === "failed" ? "none" : "block",
    width: "100%",
    maxHeight: variant === "detail" ? 260 : 116,
    objectFit: "contain",
    borderRadius: 6,
  } satisfies CSSProperties;

  if (!resolvedArtifactId) {
    return (
      <div className="screenshot-placeholder" style={placeholderStyle}>
        <span>Missing screenshot</span>
        <strong>Evidence kept</strong>
      </div>
    );
  }

  if (!isImageArtifact(resolvedArtifact)) {
    return (
      <div className="screenshot-placeholder" style={placeholderStyle}>
        <span>Unsupported artifact media</span>
        <ArtifactLink artifact={resolvedArtifact} artifactId={resolvedArtifactId} runId={resolvedRunId} label="Open screenshot artifact" />
      </div>
    );
  }

  return (
    <div className="screenshot-placeholder" style={placeholderStyle}>
      {src && imageState !== "failed" ? (
        <a href={src} target="_blank" rel="noreferrer" aria-label="Open screenshot artifact">
          <img src={src} alt={alt} style={imageStyle} onLoad={() => setImageState("loaded")} onError={() => setImageState("failed")} />
        </a>
      ) : null}
      {imageState === "loading" ? <span>Loading screenshot</span> : null}
      {imageState === "failed" ? (
        <>
          <span>Screenshot failed to load</span>
          <ArtifactLink artifact={resolvedArtifact} artifactId={resolvedArtifactId} runId={resolvedRunId} label="Open artifact" />
          <button type="button" onClick={() => setRetryCount((count) => count + 1)}>
            Retry
          </button>
        </>
      ) : null}
      {imageState === "missing" ? (
        <>
          <span>Screenshot URL unavailable</span>
          <ArtifactLink artifact={resolvedArtifact} artifactId={resolvedArtifactId} runId={resolvedRunId} label="Open screenshot artifact" />
        </>
      ) : null}
    </div>
  );
}
