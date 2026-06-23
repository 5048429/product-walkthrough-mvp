export type RunStatus =
  | "queued"
  | "starting"
  | "running"
  | "awaiting_verification"
  | "blocked"
  | "timeout"
  | "finalizing"
  | "succeeded"
  | "failed"
  | "canceling"
  | "canceled";

export type AgentStatus =
  | "pending"
  | "running"
  | "waiting"
  | "succeeded"
  | "failed"
  | "skipped"
  | "canceled";

export type AgentType =
  | "director"
  | "planner"
  | "walker"
  | "evidence_extractor"
  | "product_analyst"
  | "competitive_analyst"
  | "reviewer"
  | "report_writer"
  | "evaluator"
  | "auth_session";

export type ArtifactType =
  | "run_manifest"
  | "plan_json"
  | "events_jsonl"
  | "agents_json"
  | "artifacts_json"
  | "evidence_json"
  | "report_markdown"
  | "evaluation_json"
  | "screenshot"
  | "browser_history"
  | "log_text";

export type EventLevel = "debug" | "info" | "warn" | "error";

export type RunEventType =
  | "run.created"
  | "plan.loaded"
  | "run.started"
  | "stage.started"
  | "stage.completed"
  | "agent.started"
  | "agent.status_changed"
  | "agent.completed"
  | "agent.failed"
  | "scenario.started"
  | "scenario.step.started"
  | "scenario.step.completed"
  | "scenario.completed"
  | "evidence.created"
  | "screenshot.archived"
  | "finding.created"
  | "artifact.created"
  | "report.generated"
  | "evaluation.generated"
  | "auth_session.started"
  | "auth_session.awaiting_user"
  | "auth_session.completed"
  | "auth_session.failed"
  | "run.retry_started"
  | "run.awaiting_verification"
  | "run.blocked"
  | "run.finalizing"
  | "run.completed"
  | "run.failed"
  | "run.timeout"
  | "run.canceled";

export type ConsoleStatus =
  | "idle"
  | "running"
  | "awaiting_verification"
  | "done"
  | "blocked"
  | "failed"
  | "timeout";

export type RunMode = "mock" | "browser-use" | "unknown";

export type VerificationMode = "off" | "auto";

export type AuthSessionStatus =
  | "created"
  | "running"
  | "awaiting_user"
  | "succeeded"
  | "failed"
  | "timeout"
  | "canceled";

export type AuthReadinessStatus = "auth_not_ready" | "awaiting_manual_login" | "auth_ready";

export interface RunProgress {
  total_scenarios: number;
  completed_scenarios: number;
  failed_scenarios: number;
}

export interface RunParams {
  mode: RunMode;
  concurrency: number;
  report_language: string;
  browser_model?: string | null;
  browser_max_steps?: number;
  browser_timeout_sec?: number;
  browser_user_data_dir?: string | null;
  browser_storage_state?: string | null;
  auth_session_id?: string | null;
  auth_status?: AuthReadinessStatus;
  verification_mode?: VerificationMode;
  verification_timeout_sec?: number;
  verification_success_url_contains?: string[];
  verification_login_url_contains?: string;
}

export interface RunSummary {
  id: string;
  run_id: string;
  status: RunStatus;
  mode: RunMode;
  research_goal: string;
  run_dir: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress: RunProgress;
  report_exists: boolean;
  evidence_exists: boolean;
  evaluation_exists: boolean;
  screenshot_count: number;
  metadata: Record<string, unknown>;
}

export interface RunDetail extends RunSummary {
  params: RunParams;
  artifact_ids: string[];
  error: ApiErrorLike | null;
}

export interface RunCreateRequest {
  config_path: string | null;
  plan: unknown | null;
  mode: RunMode;
  out: string;
  concurrency: number;
  report_language: string;
  browser_model: string | null;
  browser_max_steps: number;
  browser_timeout_sec: number;
  browser_user_data_dir: string | null;
  browser_storage_state: string | null;
  auth_session_id?: string | null;
  verification_mode: VerificationMode;
  verification_timeout_sec: number;
  verification_success_url_contains: string[];
  verification_login_url_contains: string;
}

export interface AgentExecution {
  id: string;
  run_id: string;
  type: AgentType;
  status: AgentStatus;
  label: string;
  product: string | null;
  scenario_id: string | null;
  current_step: number | null;
  started_at: string | null;
  updated_at?: string | null;
  completed_at: string | null;
  metrics: Record<string, unknown>;
  error: ApiErrorLike | null;
}

export interface Artifact {
  id: string;
  run_id: string;
  type: ArtifactType;
  title: string;
  path: string;
  media_type: string;
  size_bytes: number;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface RunEvent {
  id: string;
  run_id: string;
  seq: number;
  ts: string;
  type: RunEventType | string;
  level: EventLevel;
  message: string;
  agent_id?: string | null;
  agent_type?: AgentType | null;
  product?: string | null;
  scenario_id?: string | null;
  step_index?: number | null;
  status?: string | null;
  payload?: Record<string, unknown>;
  artifact_ids?: string[];
}

export interface PlanSummary {
  id: string;
  name?: string;
  path: string;
  title: string;
  product_count: number;
  scenario_count: number;
  report_language: string;
}

export interface PlanDetailResponse {
  id: string;
  name?: string;
  path: string;
  plan: unknown;
}

export interface EvidenceItem {
  id: string;
  product: string;
  product_kind?: "owned" | "competitor" | string;
  scenario_id: string;
  scenario_title?: string;
  kind: "observation" | "browser_run" | "browser_step" | "finding" | string;
  status?: "pending" | "running" | "completed" | "blocked" | "failed" | "skipped" | string;
  title: string;
  summary: string;
  url: string | null;
  step_index?: number | null;
  action?: string | null;
  screenshot_artifact_id: string | null;
  screenshot_artifact_ids?: string[];
  artifact_ids?: string[];
  finding_ids?: string[];
  errors?: string[];
  final_output?: string | null;
  data?: Record<string, unknown>;
  confidence: number;
  created_at: string;
}

export const EVIDENCE_FOCUS_EVENT = "prodwalk:evidence-focus";

export interface EvidenceFocusRequest {
  runId?: string | null;
  evidenceId?: string | null;
  artifactId?: string | null;
  sourceEventId?: string | null;
}

export interface WalkthroughResult {
  product: string;
  product_kind: "owned" | "competitor" | string;
  scenario_id: string;
  scenario_title: string;
  status: string;
  steps: Array<Record<string, unknown>>;
}

export interface EvidenceResponse {
  run_id: string;
  artifact_id: string;
  created_at: string | null;
  report_language: string | null;
  results: WalkthroughResult[];
  evidence: EvidenceItem[];
  artifacts?: Artifact[];
  plan?: unknown;
  scenarios?: Array<Record<string, unknown>>;
}

export interface Evaluation {
  overall_score: number;
  scores: Record<string, number>;
  notes: string[];
}

export interface EvaluationResponse extends Evaluation {
  run_id: string;
  artifact_id: string;
}

export interface ReportResponse {
  run_id: string;
  language: string | null;
  markdown_artifact_id: string;
  evaluation_artifact_id: string | null;
  markdown: string;
  evaluation: Evaluation | null;
  generated_at: string | null;
  artifacts?: Artifact[];
}

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
  };
}

export interface HealthResponse {
  ok: boolean;
  service: string;
  version: string;
  time: string;
}

export type ApiErrorLike =
  | string
  | {
      message?: string;
      code?: string;
      type?: string;
      details?: unknown;
      [key: string]: unknown;
    };

function stringifyErrorDetail(value: unknown): string | null {
  if (!value) {
    return null;
  }

  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => stringifyErrorDetail(item)).filter(Boolean).join("; ") || null;
  }

  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const errors = stringifyErrorDetail(record.errors);
    const reason = stringifyErrorDetail(record.reason);
    const message = stringifyErrorDetail(record.message);
    const type = stringifyErrorDetail(record.type);
    const path = stringifyErrorDetail(record.path);
    const compact = [type, message ?? reason, path].filter(Boolean).join(": ");

    return errors ?? (compact || JSON.stringify(record));
  }

  return String(value);
}

export interface ListResponse<T> {
  items: T[];
}

export interface CursorListResponse<T> extends ListResponse<T> {
  next_cursor: string | null;
}

export interface RunCreateResponse {
  run: RunSummary;
  run_id?: string;
  status?: RunStatus | string;
  created_at?: string;
  events_url?: string;
  report_url?: string;
  evidence_url?: string;
  evaluation_url?: string;
}

export interface RunDetailResponse {
  run: RunDetail;
}

export interface EventListResponse extends ListResponse<RunEvent> {
  last_seq: number;
}

export interface ArtifactResponse {
  artifact: Artifact;
}

export interface RunActionResponse {
  run_id: string;
  status: RunStatus | string;
  accepted: boolean;
  message?: string | null;
  retry_run_id?: string | null;
}

export interface RunClearResponse {
  deleted_run_ids: string[];
  skipped_run_ids: string[];
  message?: string | null;
}

export interface VerificationConfirmRequest {
  confirmed: boolean;
  note?: string | null;
}

export interface AuthSessionCreateRequest {
  run_id?: string | null;
  url?: string | null;
  credentials_ref?: string | null;
  browser_user_data_dir?: string | null;
  browser_storage_state?: string | null;
  success_url_contains?: string[];
  login_url_contains?: string;
  timeout_sec?: number;
}

export interface AuthSessionConfirmRequest {
  confirmed: boolean;
  note?: string | null;
}

export interface AuthSessionDetail {
  id: string;
  session_id: string;
  run_id: string | null;
  status: AuthSessionStatus;
  auth_status: AuthReadinessStatus;
  url: string;
  credentials_ref: string | null;
  browser_user_data_dir_configured: boolean;
  browser_storage_state_configured: boolean;
  storage_state_saved: boolean;
  success_url_contains: string[];
  login_url_contains: string;
  timeout_sec: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  retry_run_id: string | null;
  error: ApiErrorLike | null;
  message: string | null;
}

export interface AuthSessionDetailResponse {
  session: AuthSessionDetail;
}

export interface RetryAfterVerificationRequest {
  session_id?: string | null;
  note?: string | null;
}

export interface RetryAfterVerificationResponse {
  run_id: string;
  retry_run_id: string;
  parent_run_id?: string | null;
  retry_of_run_id?: string | null;
  status: RunStatus | string;
  accepted: boolean;
  session: AuthSessionDetail | null;
  message: string | null;
}

export function toConsoleStatus(status?: RunStatus | null): ConsoleStatus {
  if (!status) {
    return "idle";
  }

  if (status === "succeeded") {
    return "done";
  }

  if (status === "failed") {
    return "failed";
  }

  if (status === "timeout") {
    return "timeout";
  }

  if (status === "awaiting_verification") {
    return "awaiting_verification";
  }

  if (status === "blocked" || status === "canceled") {
    return "blocked";
  }

  return "running";
}

export function toRunStatus(status: ConsoleStatus): RunStatus {
  if (status === "done") {
    return "succeeded";
  }

  if (status === "awaiting_verification") {
    return "awaiting_verification";
  }

  if (status === "blocked") {
    return "blocked";
  }

  if (status === "failed") {
    return "failed";
  }

  if (status === "timeout") {
    return "timeout";
  }

  if (status === "idle") {
    return "queued";
  }

  return "running";
}

export function formatApiError(error: ApiErrorLike | null | undefined): string | null {
  if (!error) {
    return null;
  }

  if (typeof error === "string") {
    return error;
  }

  const message = typeof error.message === "string" ? error.message : null;
  const code = typeof error.code === "string" ? error.code : null;
  const type = typeof error.type === "string" ? error.type : null;
  const details = stringifyErrorDetail(error.details);

  return [code ?? type, message, details].filter(Boolean).join(": ") || JSON.stringify(error);
}
