import type {
  AgentExecution,
  AgentStatus,
  Artifact,
  ArtifactResponse,
  ArtifactType,
  CursorListResponse,
  EvaluationResponse,
  EvidenceResponse,
  EventLevel,
  EventListResponse,
  HealthResponse,
  ListResponse,
  PlanDetailResponse,
  PlanSummary,
  ReportResponse,
  RunMode,
  RunActionResponse,
  RunCreateRequest,
  RunCreateResponse,
  RunDetailResponse,
  RunEvent,
  RunParams,
  RunStatus,
  RunSummary,
  VerificationConfirmRequest,
  WalkthroughResult,
} from "../types/contracts";
import { apiPath, runApiPath } from "./paths";

const runStatuses = new Set<RunStatus>([
  "queued",
  "starting",
  "running",
  "awaiting_verification",
  "blocked",
  "timeout",
  "finalizing",
  "succeeded",
  "failed",
  "canceling",
  "canceled",
]);

const agentStatuses = new Set<AgentStatus>([
  "pending",
  "running",
  "waiting",
  "succeeded",
  "failed",
  "skipped",
  "canceled",
]);

const artifactTypes = new Set<ArtifactType>([
  "run_manifest",
  "plan_json",
  "events_jsonl",
  "agents_json",
  "artifacts_json",
  "evidence_json",
  "report_markdown",
  "evaluation_json",
  "screenshot",
  "browser_history",
  "log_text",
]);

const eventLevels = new Set<EventLevel>(["debug", "info", "warn", "error"]);

export class ProdwalkApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;
  requestId?: string;

  constructor(message: string, status: number, code = "REQUEST_FAILED", details?: Record<string, unknown>, requestId?: string) {
    super(message);
    this.name = "ProdwalkApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof ProdwalkApiError && error.status === 0;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
      ...init,
    });
  } catch (error) {
    throw new ProdwalkApiError(error instanceof Error ? error.message : "Unable to reach Prodwalk API.", 0, "NETWORK_ERROR");
  }

  if (!response.ok) {
    throw await buildApiError(response);
  }

  return response.json() as Promise<T>;
}

async function buildApiError(response: Response): Promise<ProdwalkApiError> {
  const fallbackMessage = `Prodwalk API request failed: ${response.status} ${response.statusText}`;

  try {
    const payload = (await response.json()) as {
      error?: {
        code?: string;
        message?: string;
        details?: Record<string, unknown>;
        request_id?: string;
      };
    };

    if (payload.error) {
      return new ProdwalkApiError(
        payload.error.message ?? fallbackMessage,
        response.status,
        payload.error.code ?? "REQUEST_FAILED",
        payload.error.details,
        payload.error.request_id,
      );
    }
  } catch {
    // Fall through to the plain HTTP error.
  }

  return new ProdwalkApiError(fallbackMessage, response.status);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function normalizeRunStatus(value: unknown): RunStatus {
  return typeof value === "string" && runStatuses.has(value as RunStatus) ? (value as RunStatus) : "failed";
}

function normalizeRunMode(value: unknown): RunMode {
  if (value === "mock" || value === "browser-use") {
    return value;
  }

  return value === "browser-use-local" ? "browser-use" : "unknown";
}

function normalizeAgentStatus(value: unknown): AgentStatus {
  return typeof value === "string" && agentStatuses.has(value as AgentStatus) ? (value as AgentStatus) : "pending";
}

function normalizeArtifactType(value: unknown): ArtifactType {
  return typeof value === "string" && artifactTypes.has(value as ArtifactType) ? (value as ArtifactType) : "log_text";
}

function normalizeEventLevel(value: unknown): EventLevel {
  return typeof value === "string" && eventLevels.has(value as EventLevel) ? (value as EventLevel) : "info";
}

function normalizeRunSummary(value: unknown): RunSummary {
  const raw = asRecord(value);
  const progress = asRecord(raw.progress);
  const runId = asString(raw.id, asString(raw.run_id));

  return {
    id: runId,
    run_id: runId,
    status: normalizeRunStatus(raw.status),
    mode: normalizeRunMode(raw.mode),
    research_goal: asString(raw.research_goal, "Untitled run"),
    run_dir: asString(raw.run_dir, "runs/"),
    created_at: asString(raw.created_at),
    started_at: asNullableString(raw.started_at),
    completed_at: asNullableString(raw.completed_at),
    progress: {
      total_scenarios: asNumber(progress.total_scenarios),
      completed_scenarios: asNumber(progress.completed_scenarios),
      failed_scenarios: asNumber(progress.failed_scenarios),
    },
    report_exists: asBoolean(raw.report_exists),
    evidence_exists: asBoolean(raw.evidence_exists),
    evaluation_exists: asBoolean(raw.evaluation_exists),
    screenshot_count: asNumber(raw.screenshot_count),
  };
}

function normalizeRunParams(value: unknown): RunParams {
  const raw = asRecord(value);
  const verificationMode = raw.verification_mode === "auto" || raw.verification_mode === "manual" ? "auto" : "off";

  return {
    mode: normalizeRunMode(raw.mode),
    concurrency: asNumber(raw.concurrency, 3),
    report_language: asString(raw.report_language, "zh"),
    browser_model: asNullableString(raw.browser_model),
    browser_max_steps: asNumber(raw.browser_max_steps, 25),
    browser_timeout_sec: asNumber(raw.browser_timeout_sec, 600),
    browser_user_data_dir: asNullableString(raw.browser_user_data_dir),
    browser_storage_state: asNullableString(raw.browser_storage_state),
    verification_mode: verificationMode,
    verification_timeout_sec: asNumber(raw.verification_timeout_sec, 300),
    verification_success_url_contains: asStringArray(raw.verification_success_url_contains),
    verification_login_url_contains: asString(raw.verification_login_url_contains, "/auth/login"),
  };
}

function normalizeRunDetailResponse(value: unknown): RunDetailResponse {
  const raw = asRecord(value);
  const run = asRecord(raw.run);
  const summary = normalizeRunSummary(run);

  return {
    run: {
      ...summary,
      params: normalizeRunParams(run.params),
      artifact_ids: asStringArray(run.artifact_ids),
      error: typeof run.error === "string" ? run.error : run.error ? asRecord(run.error) : null,
    },
  };
}

function normalizeRunCreateResponse(value: unknown): RunCreateResponse {
  const raw = asRecord(value);

  return {
    run: normalizeRunSummary(raw.run),
    run_id: asNullableString(raw.run_id) ?? undefined,
    status: typeof raw.status === "string" ? raw.status : undefined,
    created_at: asNullableString(raw.created_at) ?? undefined,
    events_url: asNullableString(raw.events_url) ?? undefined,
    report_url: asNullableString(raw.report_url) ?? undefined,
    evidence_url: asNullableString(raw.evidence_url) ?? undefined,
    evaluation_url: asNullableString(raw.evaluation_url) ?? undefined,
  };
}

function normalizePlanSummary(value: unknown): PlanSummary {
  const raw = asRecord(value);

  return {
    id: asString(raw.id),
    name: asNullableString(raw.name) ?? undefined,
    path: asString(raw.path, asString(raw.id)),
    title: asString(raw.title, "Untitled plan"),
    product_count: asNumber(raw.product_count),
    scenario_count: asNumber(raw.scenario_count),
    report_language: asString(raw.report_language, "zh"),
  };
}

function normalizePlanDetailResponse(value: unknown): PlanDetailResponse {
  const raw = asRecord(value);

  return {
    id: asString(raw.id),
    name: asNullableString(raw.name) ?? undefined,
    path: asString(raw.path, asString(raw.id)),
    plan: raw.plan ?? null,
  };
}

function normalizeAgent(value: unknown): AgentExecution {
  const raw = asRecord(value);

  return {
    id: asString(raw.id),
    run_id: asString(raw.run_id),
    type: asString(raw.type, "director") as AgentExecution["type"],
    status: normalizeAgentStatus(raw.status),
    label: asString(raw.label, asString(raw.type, "Agent")),
    product: asNullableString(raw.product),
    scenario_id: asNullableString(raw.scenario_id),
    current_step: asNullableNumber(raw.current_step),
    started_at: asNullableString(raw.started_at),
    updated_at: asNullableString(raw.updated_at),
    completed_at: asNullableString(raw.completed_at),
    metrics: asRecord(raw.metrics),
    error: typeof raw.error === "string" ? raw.error : raw.error ? asRecord(raw.error) : null,
  };
}

function normalizeArtifact(value: unknown): Artifact {
  const raw = asRecord(value);

  return {
    id: asString(raw.id),
    run_id: asString(raw.run_id),
    type: normalizeArtifactType(raw.type),
    title: asString(raw.title, asString(raw.id, "artifact")),
    path: asString(raw.path),
    media_type: asString(raw.media_type, "application/octet-stream"),
    size_bytes: asNumber(raw.size_bytes),
    created_at: asString(raw.created_at),
    metadata: asRecord(raw.metadata),
  };
}

function normalizeRunEvent(value: unknown): RunEvent {
  const raw = asRecord(value);

  return {
    id: asString(raw.id),
    run_id: asString(raw.run_id),
    seq: asNumber(raw.seq),
    ts: asString(raw.ts),
    type: asString(raw.type, "run.event"),
    level: normalizeEventLevel(raw.level),
    message: asString(raw.message),
    agent_id: asNullableString(raw.agent_id),
    agent_type: asNullableString(raw.agent_type) as RunEvent["agent_type"],
    product: asNullableString(raw.product),
    scenario_id: asNullableString(raw.scenario_id),
    step_index: asNullableNumber(raw.step_index),
    status: asNullableString(raw.status),
    payload: asRecord(raw.payload),
    artifact_ids: asStringArray(raw.artifact_ids),
  };
}

function normalizeWalkthroughResult(value: unknown): WalkthroughResult {
  const raw = asRecord(value);

  return {
    product: asString(raw.product, "Unknown product"),
    product_kind: asString(raw.product_kind, "unknown"),
    scenario_id: asString(raw.scenario_id, "unknown_scenario"),
    scenario_title: asString(raw.scenario_title, asString(raw.scenario_id, "Unknown scenario")),
    status: asString(raw.status, "completed"),
    steps: Array.isArray(raw.steps) ? raw.steps.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [],
  };
}

function normalizeEvidenceItem(value: unknown, responseCreatedAt: string | null): EvidenceResponse["evidence"][number] {
  const raw = asRecord(value);
  const data = asRecord(raw.data);
  const scenarioId = asString(raw.scenario_id, asString(data.scenario_id, "unknown_scenario"));
  const title = asString(raw.title, asString(raw.kind, "Evidence item"));

  return {
    id: asString(raw.id, `ev-${Math.random().toString(36).slice(2)}`),
    product: asString(raw.product, asString(data.product, "Unknown product")),
    product_kind: asNullableString(raw.product_kind) ?? undefined,
    scenario_id: scenarioId,
    scenario_title: asNullableString(raw.scenario_title) ?? asNullableString(data.scenario_title) ?? undefined,
    kind: asString(raw.kind, "observation"),
    status: asNullableString(raw.status) ?? undefined,
    title,
    summary: asString(raw.summary, asString(raw.final_output, title)),
    url: asNullableString(raw.url) ?? asNullableString(data.url),
    step_index: asNullableNumber(raw.step_index),
    action: asNullableString(raw.action),
    screenshot_artifact_id: asNullableString(raw.screenshot_artifact_id),
    screenshot_artifact_ids: asStringArray(raw.screenshot_artifact_ids),
    artifact_ids: asStringArray(raw.artifact_ids),
    finding_ids: asStringArray(raw.finding_ids),
    errors: asStringArray(raw.errors),
    final_output: asNullableString(raw.final_output),
    data: Object.keys(data).length ? data : undefined,
    confidence: asNumber(raw.confidence),
    created_at: asString(raw.created_at, responseCreatedAt ?? ""),
  };
}

function normalizeEvaluation(value: unknown): EvaluationResponse {
  const raw = asRecord(value);

  return {
    run_id: asString(raw.run_id),
    artifact_id: asString(raw.artifact_id, "art_evaluation_json"),
    overall_score: asNumber(raw.overall_score),
    scores: Object.fromEntries(
      Object.entries(asRecord(raw.scores)).filter((entry): entry is [string, number] => typeof entry[1] === "number"),
    ),
    notes: asStringArray(raw.notes),
  };
}

function normalizeReport(value: unknown): ReportResponse {
  const raw = asRecord(value);
  const evaluation = raw.evaluation ? normalizeEvaluation({ ...asRecord(raw.evaluation), run_id: raw.run_id, artifact_id: raw.evaluation_artifact_id }) : null;

  return {
    run_id: asString(raw.run_id),
    language: asNullableString(raw.language),
    markdown_artifact_id: asString(raw.markdown_artifact_id, "art_report_md"),
    evaluation_artifact_id: asNullableString(raw.evaluation_artifact_id),
    markdown: asString(raw.markdown),
    evaluation,
    generated_at: asNullableString(raw.generated_at),
    artifacts: Array.isArray(raw.artifacts) ? raw.artifacts.map(normalizeArtifact) : undefined,
  };
}

function normalizeEvidence(value: unknown): EvidenceResponse {
  const raw = asRecord(value);
  const createdAt = asNullableString(raw.created_at);

  return {
    run_id: asString(raw.run_id),
    artifact_id: asString(raw.artifact_id, "art_evidence_json"),
    created_at: createdAt,
    report_language: asNullableString(raw.report_language),
    results: Array.isArray(raw.results) ? raw.results.map(normalizeWalkthroughResult) : [],
    evidence: Array.isArray(raw.evidence) ? raw.evidence.map((item) => normalizeEvidenceItem(item, createdAt)) : [],
    artifacts: Array.isArray(raw.artifacts) ? raw.artifacts.map(normalizeArtifact) : undefined,
    plan: raw.plan,
    scenarios: Array.isArray(raw.scenarios)
      ? raw.scenarios.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      : undefined,
  };
}

export const prodwalkApi = {
  getHealth: async () => requestJson<HealthResponse>(apiPath("/health")),

  getPlans: async () => {
    const response = await requestJson<ListResponse<unknown>>(apiPath("/plans"));
    return { items: response.items.map(normalizePlanSummary) };
  },

  getPlan: async (planId: string) =>
    normalizePlanDetailResponse(await requestJson<unknown>(apiPath(`/plans/${encodeURIComponent(planId)}`))),

  createRun: async (body: RunCreateRequest) =>
    normalizeRunCreateResponse(await requestJson<unknown>(apiPath("/runs"), {
      method: "POST",
      body: JSON.stringify(body),
    })),

  listRuns: async (limit = 20) => {
    const response = await requestJson<CursorListResponse<unknown>>(apiPath(`/runs?limit=${limit}`));
    return {
      items: response.items.map(normalizeRunSummary),
      next_cursor: response.next_cursor,
    };
  },

  getRun: async (runId: string) => normalizeRunDetailResponse(await requestJson<unknown>(runApiPath(runId))),

  cancelRun: async (runId: string, reason = "User canceled from console") =>
    requestJson<RunActionResponse>(runApiPath(runId, "/cancel"), {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  confirmVerification: async (runId: string, body: VerificationConfirmRequest) =>
    requestJson<RunActionResponse>(runApiPath(runId, "/verification/confirm"), {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getAgents: async (runId: string) => {
    const response = await requestJson<ListResponse<unknown>>(runApiPath(runId, "/agents"));
    return { items: response.items.map(normalizeAgent) };
  },

  getEvents: async (runId: string, afterSeq = 0, limit = 100) => {
    const response = await requestJson<EventListResponse>(runApiPath(runId, `/events?after_seq=${afterSeq}&limit=${limit}`));
    return {
      items: response.items.map(normalizeRunEvent),
      last_seq: response.last_seq,
    };
  },

  getArtifacts: async (runId: string) => {
    const response = await requestJson<ListResponse<unknown>>(runApiPath(runId, "/artifacts"));
    return { items: response.items.map(normalizeArtifact) };
  },

  getArtifact: async (runId: string, artifactId: string) =>
    requestJson<ArtifactResponse>(runApiPath(runId, `/artifacts/${encodeURIComponent(artifactId)}`)).then((response) => ({
      artifact: normalizeArtifact(response.artifact),
    })),

  getReport: async (runId: string) => normalizeReport(await requestJson<unknown>(runApiPath(runId, "/report"))),

  getEvidence: async (runId: string) => normalizeEvidence(await requestJson<unknown>(runApiPath(runId, "/evidence"))),

  getEvaluation: async (runId: string) => normalizeEvaluation(await requestJson<unknown>(runApiPath(runId, "/evaluation"))),
};
