import type {
  AgentExecution,
  AgentStatus,
  AuthReadinessStatus,
  AuthSessionConfirmRequest,
  AuthSessionCreateRequest,
  AuthSessionDetail,
  AuthSessionDetailResponse,
  AuthSessionStatus,
  Artifact,
  ArtifactResponse,
  ArtifactType,
  CursorListResponse,
  EdgeKind,
  EvaluationResponse,
  EvidenceResponse,
  EventLevel,
  EventListResponse,
  HealthResponse,
  ListResponse,
  PlanDetailResponse,
  PlanSummary,
  PageInsight,
  PageNodeStatus,
  PageType,
  ReportResponse,
  RetryAfterVerificationRequest,
  RetryAfterVerificationResponse,
  RunMode,
  RunActionResponse,
  RunClearResponse,
  RunCreateRequest,
  RunCreateResponse,
  RunDetailResponse,
  RunEvent,
  RunParams,
  RunStatus,
  RunSummary,
  ScreenshotEvidence,
  VerificationConfirmRequest,
  WalkthroughMapResponse,
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
  "walkthrough_map",
  "screenshot",
  "browser_history",
  "log_text",
]);

const pageTypes = new Set<PageType>([
  "dashboard",
  "list",
  "detail",
  "settings",
  "form",
  "auth",
  "error",
  "external",
  "unknown",
]);

const pageNodeStatuses = new Set<PageNodeStatus>(["visited", "blocked", "discovered", "external", "error"]);

const edgeKinds = new Set<EdgeKind>(["navigation", "menu", "button", "link", "redirect", "form_submit", "inferred"]);

const pageInsightKinds = new Set<PageInsight["kind"]>(["purpose", "function", "control", "issue", "observation"]);

const pageInsightSources = new Set<PageInsight["source"]>([
  "browser_step",
  "browser_run_summary",
  "report",
  "evaluation",
  "heuristic",
]);

const pageInsightSeverities = new Set<NonNullable<PageInsight["severity"]>>(["info", "low", "medium", "high"]);

const eventLevels = new Set<EventLevel>(["debug", "info", "warn", "error"]);

const authSessionStatuses = new Set<AuthSessionStatus>([
  "created",
  "running",
  "awaiting_user",
  "succeeded",
  "failed",
  "timeout",
  "canceled",
]);

const authReadinessStatuses = new Set<AuthReadinessStatus>([
  "auth_not_ready",
  "awaiting_manual_login",
  "auth_ready",
]);

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

function asNullableRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
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

function normalizePageType(value: unknown): PageType {
  return typeof value === "string" && pageTypes.has(value as PageType) ? (value as PageType) : "unknown";
}

function normalizePageNodeStatus(value: unknown): PageNodeStatus {
  return typeof value === "string" && pageNodeStatuses.has(value as PageNodeStatus) ? (value as PageNodeStatus) : "discovered";
}

function normalizeEdgeKind(value: unknown): EdgeKind {
  return typeof value === "string" && edgeKinds.has(value as EdgeKind) ? (value as EdgeKind) : "inferred";
}

function normalizePageInsightKind(value: unknown): PageInsight["kind"] {
  return typeof value === "string" && pageInsightKinds.has(value as PageInsight["kind"])
    ? (value as PageInsight["kind"])
    : "observation";
}

function normalizePageInsightSource(value: unknown): PageInsight["source"] {
  return typeof value === "string" && pageInsightSources.has(value as PageInsight["source"])
    ? (value as PageInsight["source"])
    : "heuristic";
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
    metadata: asRecord(raw.metadata),
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
    auth_session_id: asNullableString(raw.auth_session_id),
    auth_status: normalizeAuthReadinessStatus(raw.auth_status),
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

function normalizeAuthSessionStatus(value: unknown): AuthSessionStatus {
  return typeof value === "string" && authSessionStatuses.has(value as AuthSessionStatus)
    ? (value as AuthSessionStatus)
    : "failed";
}

function normalizeAuthReadinessStatus(value: unknown, sessionStatus?: AuthSessionStatus): AuthReadinessStatus {
  if (typeof value === "string" && authReadinessStatuses.has(value as AuthReadinessStatus)) {
    return value as AuthReadinessStatus;
  }

  if (sessionStatus === "succeeded") {
    return "auth_ready";
  }

  if (sessionStatus === "running" || sessionStatus === "awaiting_user") {
    return "awaiting_manual_login";
  }

  return "auth_not_ready";
}

function normalizeAuthSession(value: unknown): AuthSessionDetail {
  const raw = asRecord(value);
  const status = normalizeAuthSessionStatus(raw.status);

  return {
    id: asString(raw.id, asString(raw.session_id)),
    session_id: asString(raw.session_id, asString(raw.id)),
    run_id: asNullableString(raw.run_id),
    status,
    auth_status: normalizeAuthReadinessStatus(raw.auth_status, status),
    url: asString(raw.url),
    credentials_ref: asNullableString(raw.credentials_ref),
    browser_user_data_dir_configured: asBoolean(raw.browser_user_data_dir_configured),
    browser_storage_state_configured: asBoolean(raw.browser_storage_state_configured),
    storage_state_saved: asBoolean(raw.storage_state_saved),
    success_url_contains: asStringArray(raw.success_url_contains),
    login_url_contains: asString(raw.login_url_contains, "/auth/login"),
    timeout_sec: asNumber(raw.timeout_sec, 300),
    created_at: asString(raw.created_at),
    updated_at: asString(raw.updated_at),
    completed_at: asNullableString(raw.completed_at),
    retry_run_id: asNullableString(raw.retry_run_id),
    error: typeof raw.error === "string" ? raw.error : asNullableRecord(raw.error),
    message: asNullableString(raw.message),
  };
}

function normalizeAuthSessionResponse(value: unknown): AuthSessionDetailResponse {
  const raw = asRecord(value);
  return { session: normalizeAuthSession(raw.session) };
}

function normalizeRetryAfterVerificationResponse(value: unknown): RetryAfterVerificationResponse {
  const raw = asRecord(value);
  return {
    run_id: asString(raw.run_id),
    retry_run_id: asString(raw.retry_run_id),
    parent_run_id: asNullableString(raw.parent_run_id),
    retry_of_run_id: asNullableString(raw.retry_of_run_id),
    status: typeof raw.status === "string" ? raw.status : "queued",
    accepted: asBoolean(raw.accepted),
    session: raw.session ? normalizeAuthSession(raw.session) : null,
    message: asNullableString(raw.message),
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

function normalizeScreenshotEvidence(value: unknown): ScreenshotEvidence {
  const raw = asRecord(value);

  return {
    id: asString(raw.id, asString(raw.artifact_id, `shot-${Math.random().toString(36).slice(2)}`)),
    artifact_id: asNullableString(raw.artifact_id),
    title: asString(raw.title, asString(raw.path, "Screenshot")),
    path: asNullableString(raw.path),
    content_url: asNullableString(raw.content_url),
    screenshot_url: asNullableString(raw.screenshot_url),
    evidence_id: asNullableString(raw.evidence_id),
    step_index: asNullableNumber(raw.step_index),
    captured_at: asNullableString(raw.captured_at),
    is_primary: asBoolean(raw.is_primary),
  };
}

function normalizePageInsight(value: unknown): PageInsight {
  const raw = asRecord(value);
  const severity =
    typeof raw.severity === "string" && pageInsightSeverities.has(raw.severity as NonNullable<PageInsight["severity"]>)
      ? (raw.severity as NonNullable<PageInsight["severity"]>)
      : undefined;

  return {
    id: asString(raw.id, `ins-${Math.random().toString(36).slice(2)}`),
    kind: normalizePageInsightKind(raw.kind),
    title: asString(raw.title, asString(raw.kind, "Observation")),
    summary: asString(raw.summary),
    severity,
    confidence: asNumber(raw.confidence),
    evidence_ids: asStringArray(raw.evidence_ids),
    source: normalizePageInsightSource(raw.source),
  };
}

function normalizePageNode(value: unknown): WalkthroughMapResponse["nodes"][number] {
  const raw = asRecord(value);
  const metadata = asRecord(raw.metadata);

  return {
    id: asString(raw.id, `page-${Math.random().toString(36).slice(2)}`),
    product: asString(raw.product, "Unknown product"),
    scenario_ids: asStringArray(raw.scenario_ids),
    name: asString(raw.name, asString(raw.title, "Untitled page")),
    title: asNullableString(raw.title),
    url: asNullableString(raw.url),
    route: asNullableString(raw.route),
    canonical_url: asNullableString(raw.canonical_url),
    page_type: normalizePageType(raw.page_type),
    status: normalizePageNodeStatus(raw.status),
    purpose: asString(raw.purpose),
    key_functions: asStringArray(raw.key_functions),
    key_controls: asStringArray(raw.key_controls),
    issues: Array.isArray(raw.issues) ? raw.issues.map(normalizePageInsight) : [],
    observations: Array.isArray(raw.observations) ? raw.observations.map(normalizePageInsight) : [],
    screenshot_evidence: Array.isArray(raw.screenshot_evidence) ? raw.screenshot_evidence.map(normalizeScreenshotEvidence) : [],
    primary_screenshot_artifact_id: asNullableString(raw.primary_screenshot_artifact_id),
    evidence_ids: asStringArray(raw.evidence_ids),
    event_ids: asStringArray(raw.event_ids),
    first_seen_step: asNullableNumber(raw.first_seen_step),
    last_seen_step: asNullableNumber(raw.last_seen_step),
    visit_count: asNumber(raw.visit_count),
    confidence: asNumber(raw.confidence),
    metadata: {
      ...metadata,
      normalized_route: asNullableString(metadata.normalized_route),
      dynamic_route_pattern: asNullableString(metadata.dynamic_route_pattern),
      discovered_from_node_id: asNullableString(metadata.discovered_from_node_id),
      source_history_artifact_ids: asStringArray(metadata.source_history_artifact_ids),
      raw_titles: asStringArray(metadata.raw_titles),
      raw_urls: asStringArray(metadata.raw_urls),
    },
  };
}

function normalizePageEdge(value: unknown): WalkthroughMapResponse["edges"][number] {
  const raw = asRecord(value);
  const metadata = asRecord(raw.metadata);

  return {
    id: asString(raw.id, `edge-${Math.random().toString(36).slice(2)}`),
    source: asString(raw.source),
    target: asString(raw.target),
    label: asString(raw.label),
    kind: normalizeEdgeKind(raw.kind),
    action: asNullableString(raw.action),
    from_step_index: asNullableNumber(raw.from_step_index),
    to_step_index: asNullableNumber(raw.to_step_index),
    evidence_ids: asStringArray(raw.evidence_ids),
    event_ids: asStringArray(raw.event_ids),
    confidence: asNumber(raw.confidence),
    metadata: {
      ...metadata,
      source_url: asNullableString(metadata.source_url),
      target_url: asNullableString(metadata.target_url),
      inferred_reason: asNullableString(metadata.inferred_reason),
      occurrence_count: asNumber(metadata.occurrence_count, 0),
    },
  };
}

export function normalizeWalkthroughMap(value: unknown): WalkthroughMapResponse {
  const raw = asRecord(value);
  const nodes = Array.isArray(raw.nodes) ? raw.nodes.map(normalizePageNode) : [];
  const edges = Array.isArray(raw.edges) ? raw.edges.map(normalizePageEdge) : [];
  const summary = asRecord(raw.summary);
  const layout = asRecord(raw.layout);
  const layoutNodes = asRecord(layout.nodes);

  return {
    run_id: asString(raw.run_id),
    artifact_id: asString(raw.artifact_id, "art_walkthrough_map"),
    generated_at: asString(raw.generated_at),
    schema_version: asString(raw.schema_version, "1.0"),
    source_artifact_ids: asStringArray(raw.source_artifact_ids),
    products: Array.isArray(raw.products)
      ? raw.products.map((product) => {
          const productRecord = asRecord(product);
          return {
            name: asString(productRecord.name, "Unknown product"),
            kind: asString(productRecord.kind, "unknown"),
            start_url: asString(productRecord.start_url),
          };
        })
      : [],
    summary: {
      node_count: asNumber(summary.node_count, nodes.length),
      edge_count: asNumber(summary.edge_count, edges.length),
      visited_count: asNumber(summary.visited_count, nodes.filter((node) => node.status === "visited").length),
      blocked_count: asNumber(summary.blocked_count, nodes.filter((node) => node.status === "blocked").length),
      discovered_count: asNumber(summary.discovered_count, nodes.filter((node) => node.status === "discovered").length),
      external_count: asNumber(summary.external_count, nodes.filter((node) => node.status === "external").length),
      screenshot_count: asNumber(
        summary.screenshot_count,
        nodes.reduce((count, node) => count + node.screenshot_evidence.length, 0),
      ),
      confidence: asNumber(summary.confidence),
    },
    nodes,
    edges,
    layout: Object.keys(layout).length
      ? {
          algorithm: asString(layout.algorithm, "layered"),
          nodes: Object.fromEntries(
            Object.entries(layoutNodes).map(([id, position]) => {
              const rawPosition = asRecord(position);
              return [
                id,
                {
                  x: asNumber(rawPosition.x),
                  y: asNumber(rawPosition.y),
                  depth: asNumber(rawPosition.depth),
                },
              ];
            }),
          ),
        }
      : undefined,
    warnings: Array.isArray(raw.warnings)
      ? raw.warnings.map((warning) => {
          const warningRecord = asRecord(warning);
          return {
            code: asString(warningRecord.code, "MAP_WARNING"),
            message: asString(warningRecord.message),
            details: asNullableRecord(warningRecord.details) ?? undefined,
          };
        })
      : [],
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

  deleteRun: async (runId: string) =>
    requestJson<RunActionResponse>(runApiPath(runId), {
      method: "DELETE",
    }),

  clearRuns: async () =>
    requestJson<RunClearResponse>(apiPath("/runs"), {
      method: "DELETE",
    }),

  confirmVerification: async (runId: string, body: VerificationConfirmRequest) =>
    requestJson<RunActionResponse>(runApiPath(runId, "/verification/confirm"), {
      method: "POST",
      body: JSON.stringify(body),
    }),

  createAuthSession: async (body: AuthSessionCreateRequest) =>
    normalizeAuthSessionResponse(await requestJson<unknown>(apiPath("/auth-sessions"), {
      method: "POST",
      body: JSON.stringify(body),
    })),

  getAuthSession: async (sessionId: string) =>
    normalizeAuthSessionResponse(await requestJson<unknown>(apiPath(`/auth-sessions/${encodeURIComponent(sessionId)}`))),

  confirmAuthSession: async (sessionId: string, body: AuthSessionConfirmRequest) =>
    normalizeAuthSessionResponse(await requestJson<unknown>(apiPath(`/auth-sessions/${encodeURIComponent(sessionId)}/confirm`), {
      method: "POST",
      body: JSON.stringify(body),
    })),

  retryRunAfterVerification: async (runId: string, body: RetryAfterVerificationRequest) =>
    normalizeRetryAfterVerificationResponse(await requestJson<unknown>(runApiPath(runId, "/retry-after-verification"), {
      method: "POST",
      body: JSON.stringify(body),
    })),

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

  getWalkthroughMap: async (runId: string) => normalizeWalkthroughMap(await requestJson<unknown>(runApiPath(runId, "/map"))),
};
