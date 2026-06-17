export const DEFAULT_API_BASE_URL = "http://localhost:8000";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_PRODWALK_API_BASE_URL || DEFAULT_API_BASE_URL;

export function apiPath(path: string): string {
  const base = API_BASE_URL.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const apiPrefix = base.endsWith("/api") ? "" : "/api";

  return `${base}${apiPrefix}${normalizedPath}`;
}

export function runApiPath(runId: string, path = ""): string {
  const normalizedPath = path.startsWith("/") || path.length === 0 ? path : `/${path}`;

  return apiPath(`/runs/${encodeURIComponent(runId)}${normalizedPath}`);
}

export function backendUrl(urlOrPath: string): string {
  if (/^(?:https?:|data:|blob:|mailto:)/i.test(urlOrPath) || urlOrPath.startsWith("#")) {
    return urlOrPath;
  }

  const base = API_BASE_URL.replace(/\/+$/, "");
  const baseWithoutApi = base.endsWith("/api") ? base.slice(0, -4) : base;

  if (urlOrPath.startsWith("/")) {
    return `${baseWithoutApi}${urlOrPath}`;
  }

  if (urlOrPath.startsWith("api/")) {
    return `${baseWithoutApi}/${urlOrPath}`;
  }

  return apiPath(urlOrPath);
}

function encodePathSegments(path: string): string {
  return path
    .split("/")
    .filter((segment) => segment.length > 0)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export function runArtifactContentUrl(runId: string, artifactId: string): string {
  return runApiPath(runId, `/artifacts/${encodeURIComponent(artifactId)}/content`);
}

export function runArtifactPathUrl(runId: string, artifactPath: string): string {
  return runApiPath(runId, `/artifacts/${encodePathSegments(artifactPath)}`);
}
