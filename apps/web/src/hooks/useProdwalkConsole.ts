import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isNetworkError, ProdwalkApiError, prodwalkApi } from "../api/client";
import { openRunEventStream, type RunEventConnectionState } from "../api/sse";
import { mockConsoleData } from "../api/mockConsoleData";
import { mockArtifacts } from "../mock/artifacts";
import type {
  AgentExecution,
  AgentStatus,
  AuthReadinessStatus,
  AuthSessionDetail,
  Artifact,
  ConsoleStatus,
  EvaluationResponse,
  EvidenceResponse,
  HealthResponse,
  PlanDetailResponse,
  PlanSummary,
  ReportResponse,
  RunCreateRequest,
  RunDetail,
  RunEvent,
  RunMode,
  RunStatus,
  RunSummary,
  VerificationMode,
  WalkthroughMapResponse,
} from "../types/contracts";
import { formatApiError, toConsoleStatus, toRunStatus } from "../types/contracts";

const ACTIVE_RUN_KEY = "prodwalk.activeRunId";
const terminalRunStatuses = new Set<RunStatus>([
  "succeeded",
  "blocked",
  "timeout",
  "failed",
  "canceled",
]);
const stopAllowedRunStatuses = new Set<RunStatus>([
  "queued",
  "starting",
  "running",
  "awaiting_verification",
  "finalizing",
  "canceling",
]);
const terminalEventTypes = new Set([
  "run.completed",
  "run.awaiting_verification",
  "run.blocked",
  "run.timeout",
  "run.failed",
  "run.canceled",
]);
const artifactEventTypes = new Set(["artifact.created", "screenshot.archived", "report.generated", "evaluation.generated"]);
const agentStatuses = new Set<AgentStatus>([
  "pending",
  "running",
  "waiting",
  "succeeded",
  "failed",
  "skipped",
  "canceled",
]);

export type ConsoleDataSource = "api" | "mock";

export interface StartRunOptions {
  targetUrl?: string | null;
  targetName?: string | null;
  targetCredentialsRef?: string | null;
  mode?: RunMode;
  concurrency?: number;
  reportLanguage?: string;
  browserMaxSteps?: number;
  browserTimeoutSec?: number;
  browserDiscoverAllPages?: boolean | null;
  browserDiscoveryMaxPages?: number | null;
  browserDiscoveryMaxDepth?: number | null;
  browserUserDataDir?: string | null;
  browserStorageState?: string | null;
  authSessionId?: string | null;
  verificationMode?: VerificationMode;
  verificationTimeoutSec?: number;
  verificationSuccessUrlContains?: string[];
  verificationLoginUrlContains?: string;
}

export interface ConsoleLoadingState {
  initial: boolean;
  planDetail: boolean;
  start: boolean;
  runHistory: boolean;
  activeRun: boolean;
  report: boolean;
  evidence: boolean;
  evaluation: boolean;
  map: boolean;
  historyRun: boolean;
  historyReport: boolean;
  historyEvidence: boolean;
  historyEvaluation: boolean;
  historyMap: boolean;
  verification: boolean;
}

export interface ConsoleErrorState {
  initial: string | null;
  planDetail: string | null;
  start: string | null;
  runHistory: string | null;
  activeRun: string | null;
  report: string | null;
  evidence: string | null;
  evaluation: string | null;
  map: string | null;
  historyRun: string | null;
  historyReport: string | null;
  historyEvidence: string | null;
  historyEvaluation: string | null;
  historyMap: string | null;
  verification: string | null;
}

function readStoredActiveRunId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_RUN_KEY);
  } catch {
    return null;
  }
}

function storeActiveRunId(runId: string | null): void {
  try {
    if (runId) {
      window.localStorage.setItem(ACTIVE_RUN_KEY, runId);
    } else {
      window.localStorage.removeItem(ACTIVE_RUN_KEY);
    }
  } catch {
    // Local storage is a convenience for reload recovery, not a hard dependency.
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ProdwalkApiError) {
    return formatApiError({
      code: error.code,
      message: error.message,
      details: error.details,
    }) ?? `${error.code}: ${error.message}`;
  }

  return error instanceof Error ? error.message : "Unknown API error.";
}

function firstProductAuthTarget(plan: unknown): { url: string; credentialsRef: string | null; successMarkers: string[] } | null {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) {
    return null;
  }

  const products = (plan as { products?: unknown }).products;
  if (!Array.isArray(products)) {
    return null;
  }

  for (const product of products) {
    if (!product || typeof product !== "object" || Array.isArray(product)) {
      continue;
    }

    const record = product as { url?: unknown; credentials_ref?: unknown };
    if (typeof record.url !== "string" || !record.url.trim()) {
      continue;
    }

    const url = record.url.trim();
    let successMarkers: string[] = [];
    try {
      const parsed = new URL(url);
      if (parsed.pathname && parsed.pathname !== "/") {
        successMarkers = [parsed.pathname];
      }
    } catch {
      successMarkers = [];
    }

    return {
      url,
      credentialsRef: typeof record.credentials_ref === "string" && record.credentials_ref.trim()
        ? record.credentials_ref.trim()
        : null,
      successMarkers,
    };
  }

  return null;
}

function normalizeTargetUrlForRequest(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error("请输入要走查的网站 URL。");
  }
  if (/\s/.test(trimmed)) {
    throw new Error("网站 URL 不能包含空格。");
  }

  const hasScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed);
  const schemeLike = trimmed.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):(.*)$/);
  if (schemeLike && !hasScheme && !/^\d+(?:\/|$)/.test(schemeLike[2])) {
    throw new Error("网站 URL 只支持 http 或 https。");
  }

  const candidate = hasScheme ? trimmed : `https://${trimmed}`;
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error("请输入有效的网站 URL，例如 https://example.com。");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("网站 URL 只支持 http 或 https。");
  }
  if (!parsed.hostname) {
    throw new Error("网站 URL 需要包含有效域名。");
  }
  if (parsed.username || parsed.password) {
    throw new Error("网站 URL 不要包含账号或密码，请使用登录准备流程保存登录态。");
  }

  return parsed.toString();
}

function successMarkersForUrl(url: string): string[] {
  try {
    const parsed = new URL(url);
    return parsed.pathname && parsed.pathname !== "/" ? [parsed.pathname] : [];
  } catch {
    return [];
  }
}

function authReadinessFromSession(session: AuthSessionDetail | null): AuthReadinessStatus {
  return session?.auth_status ?? "auth_not_ready";
}

function shouldUseMockFallback(error: unknown): boolean {
  return isNetworkError(error);
}

function buildMockRun(status: ConsoleStatus): RunDetail | null {
  if (status === "idle") {
    return null;
  }

  const completedAt =
    status === "done" ||
    status === "awaiting_verification" ||
    status === "blocked" ||
    status === "failed" ||
    status === "timeout"
      ? "2026-06-16T08:31:16Z"
      : null;
  const base = mockConsoleData.activeRun;
  const progress = (() => {
    if (status === "done") {
      return {
        ...base.progress,
        completed_scenarios: base.progress.total_scenarios,
      };
    }

    if (status === "failed") {
      return {
        ...base.progress,
        completed_scenarios: 0,
        failed_scenarios: 1,
      };
    }

    if (status === "awaiting_verification" || status === "blocked") {
      return {
        ...base.progress,
        completed_scenarios: 1,
        failed_scenarios: 0,
      };
    }

    if (status === "timeout") {
      return {
        ...base.progress,
        completed_scenarios: 1,
        failed_scenarios: 1,
      };
    }

    return base.progress;
  })();

  return {
    ...base,
    status: toRunStatus(status),
    completed_at: completedAt,
    progress,
    error:
      status === "failed"
        ? "Mock adapter reported a simulated failure."
        : status === "timeout"
          ? "Mock browser-use preview timed out while waiting for a walkthrough result."
        : status === "awaiting_verification"
          ? "Manual verification required before browser-use can be acknowledged."
        : status === "blocked"
          ? "Mock adapter reported an environment blocker."
          : null,
  };
}

function mockDetailFromSummary(summary: RunSummary): RunDetail {
  const artifactIds = [
    summary.evidence_exists ? "art_evidence_json" : null,
    summary.report_exists ? "art_report_md" : null,
    summary.evaluation_exists ? "art_evaluation_json" : null,
  ].filter((id): id is string => Boolean(id));

  return {
    ...summary,
    params: {
      mode: summary.mode,
      concurrency: 3,
      report_language: "zh",
    },
    artifact_ids: artifactIds,
    error: null,
  };
}

function unavailableArtifactMessage(filename: string): string {
  return `${filename} is not available for this run.`;
}

function normalizeAgentStatus(status: string | null | undefined): AgentStatus | null {
  return status && agentStatuses.has(status as AgentStatus) ? (status as AgentStatus) : null;
}

function statusFromAgentEvent(event: RunEvent, current?: AgentExecution): AgentStatus {
  if (event.type === "agent.started") {
    return "running";
  }

  if (event.type === "agent.completed") {
    return normalizeAgentStatus(event.status) ?? "succeeded";
  }

  if (event.type === "agent.failed") {
    return "failed";
  }

  if (event.type === "agent.status_changed") {
    return normalizeAgentStatus(event.status) ?? current?.status ?? "running";
  }

  return normalizeAgentStatus(event.status) ?? current?.status ?? "running";
}

function displayAgentType(event: RunEvent): AgentExecution["type"] {
  return (event.agent_type ?? "director") as AgentExecution["type"];
}

function buildAgentLabel(event: RunEvent): string {
  const type = (event.agent_type ?? "agent").replaceAll("_", " ");
  const parts = [type];

  if (event.product) {
    parts.push(event.product);
  }

  if (event.scenario_id) {
    parts.push(event.scenario_id);
  }

  return parts.join(" / ");
}

function eventAgentId(event: RunEvent): string | null {
  if (event.agent_id) {
    return event.agent_id;
  }

  if (!event.agent_type) {
    return null;
  }

  return ["agent", event.agent_type, event.product, event.scenario_id]
    .filter(Boolean)
    .join("_")
    .replaceAll(/\s+/g, "_")
    .toLowerCase();
}

function mergeMetrics(current: Record<string, unknown>, event: RunEvent): Record<string, unknown> {
  const payload = event.payload ?? {};
  const next = { ...current };

  for (const [key, value] of Object.entries(payload)) {
    if (typeof value === "number" || typeof value === "string" || value === null) {
      next[key] = value;
    }
  }

  if (event.step_index) {
    next.step_count = Math.max(Number(next.step_count ?? 0), event.step_index);
  }

  return next;
}

export function deriveAgentsFromEvents(events: RunEvent[]): AgentExecution[] {
  const agents = new Map<string, AgentExecution>();

  for (const event of events) {
    const id = eventAgentId(event);

    if (!id) {
      continue;
    }

    const current = agents.get(id);
    const status = statusFromAgentEvent(event, current);
    const isTerminal = status === "succeeded" || status === "failed" || status === "skipped" || status === "canceled";

    agents.set(id, {
      id,
      run_id: event.run_id,
      type: current?.type ?? displayAgentType(event),
      status,
      label: current?.label ?? buildAgentLabel(event),
      product: current?.product ?? event.product ?? null,
      scenario_id: current?.scenario_id ?? event.scenario_id ?? null,
      current_step: event.step_index ?? current?.current_step ?? null,
      started_at: current?.started_at ?? (event.type === "agent.started" ? event.ts : null),
      updated_at: event.ts,
      completed_at: isTerminal ? event.ts : current?.completed_at ?? null,
      metrics: mergeMetrics(current?.metrics ?? {}, event),
      error: status === "failed" ? event.payload ?? event.message : current?.error ?? null,
    });
  }

  return Array.from(agents.values()).sort((a, b) => a.id.localeCompare(b.id));
}

function mergeRunEvents(current: RunEvent[], incoming: RunEvent[]): RunEvent[] {
  const bySeq = new Map<number, RunEvent>();

  for (const event of current) {
    bySeq.set(event.seq, event);
  }

  for (const event of incoming) {
    bySeq.set(event.seq, event);
  }

  return Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
}

function statusFromRunEvent(event: RunEvent): RunStatus | null {
  if (event.type === "run.started") {
    return "running";
  }

  if (event.type === "run.finalizing") {
    return "finalizing";
  }

  if (event.type === "run.completed") {
    return "succeeded";
  }

  if (event.type === "run.failed") {
    return "failed";
  }

  if (event.type === "run.timeout") {
    return "timeout";
  }

  if (event.type === "run.canceled") {
    return "canceled";
  }

  if (event.type === "run.blocked") {
    return "blocked";
  }

  if (event.type === "run.awaiting_verification") {
    return "awaiting_verification";
  }

  return null;
}

function applyRunEvent(run: RunDetail | null, event: RunEvent): RunDetail | null {
  if (!run) {
    return run;
  }

  const status = statusFromRunEvent(event);

  if (!status) {
    return run;
  }

  return {
    ...run,
    status,
    started_at: status === "running" && !run.started_at ? event.ts : run.started_at,
    completed_at: terminalRunStatuses.has(status) ? event.ts : run.completed_at,
    error: status === "failed" ? event.payload ?? event.message : run.error,
  };
}

function shouldRefreshRun(event: RunEvent): boolean {
  return event.type.startsWith("run.") || event.type.startsWith("stage.") || artifactEventTypes.has(event.type);
}

function shouldLoadFinalArtifacts(event: RunEvent): boolean {
  if (terminalEventTypes.has(event.type) || event.type === "report.generated" || event.type === "evaluation.generated") {
    return true;
  }

  if (event.type === "artifact.created") {
    const artifactType = event.payload?.artifact_type;
    return (
      artifactType === "evidence_json" ||
      artifactType === "report_markdown" ||
      artifactType === "evaluation_json" ||
      artifactType === "walkthrough_map" ||
      Boolean(event.artifact_ids?.some((id) => ["art_evidence_json", "art_report_md", "art_evaluation_json", "art_walkthrough_map"].includes(id)))
    );
  }

  return false;
}

export function useProdwalkConsole() {
  const [source, setSource] = useState<ConsoleDataSource>("api");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [selectedPlanDetail, setSelectedPlanDetail] = useState<PlanDetailResponse | null>(null);
  const [recentRuns, setRecentRuns] = useState<RunSummary[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(() => readStoredActiveRunId());
  const [activeRun, setActiveRun] = useState<RunDetail | null>(null);
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState<string | null>(null);
  const [selectedHistoryRun, setSelectedHistoryRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [walkthroughMap, setWalkthroughMap] = useState<WalkthroughMapResponse | null>(null);
  const [loginSession, setLoginSession] = useState<AuthSessionDetail | null>(null);
  const [authSession, setAuthSession] = useState<AuthSessionDetail | null>(null);
  const [verificationSourceRunId, setVerificationSourceRunId] = useState<string | null>(null);
  const [retryRunId, setRetryRunId] = useState<string | null>(null);
  const [historyArtifacts, setHistoryArtifacts] = useState<Artifact[]>([]);
  const [historyReport, setHistoryReport] = useState<ReportResponse | null>(null);
  const [historyEvidence, setHistoryEvidence] = useState<EvidenceResponse | null>(null);
  const [historyEvaluation, setHistoryEvaluation] = useState<EvaluationResponse | null>(null);
  const [historyWalkthroughMap, setHistoryWalkthroughMap] = useState<WalkthroughMapResponse | null>(null);
  const [connectionState, setConnectionState] = useState<RunEventConnectionState>("idle");
  const [mockStatus, setMockStatus] = useState<ConsoleStatus>("running");
  const [loading, setLoading] = useState<ConsoleLoadingState>({
    initial: true,
    planDetail: false,
    start: false,
    runHistory: false,
    activeRun: false,
    report: false,
    evidence: false,
    evaluation: false,
    map: false,
    historyRun: false,
    historyReport: false,
    historyEvidence: false,
    historyEvaluation: false,
    historyMap: false,
    verification: false,
  });
  const [errors, setErrors] = useState<ConsoleErrorState>({
    initial: null,
    planDetail: null,
    start: null,
    runHistory: null,
    activeRun: null,
    report: null,
    evidence: null,
    evaluation: null,
    map: null,
    historyRun: null,
    historyReport: null,
    historyEvidence: null,
    historyEvaluation: null,
    historyMap: null,
    verification: null,
  });

  const eventSeqsRef = useRef(new Set<number>());
  const lastSeqRef = useRef(0);

  const selectedPlan = useMemo(
    () => plans.find((plan) => plan.id === selectedPlanId || plan.path === selectedPlanId),
    [plans, selectedPlanId],
  );

  const consoleStatus = toConsoleStatus(activeRun?.status ?? null);
  const agents = useMemo(() => deriveAgentsFromEvents(events), [events]);
  const hasTerminalRunEvent = useMemo(
    () => events.some((event) => terminalEventTypes.has(event.type)),
    [events],
  );

  const updateLoading = useCallback((patch: Partial<ConsoleLoadingState>) => {
    setLoading((current) => ({ ...current, ...patch }));
  }, []);

  const updateErrors = useCallback((patch: Partial<ConsoleErrorState>) => {
    setErrors((current) => ({ ...current, ...patch }));
  }, []);

  const updateTargetUrl = useCallback(
    (value: string) => {
      const previous = targetUrl.trim();
      const next = value.trim();
      setTargetUrl(value);
      if (previous !== next) {
        setLoginSession(null);
        updateErrors({ start: null, verification: null });
      }
    },
    [targetUrl, updateErrors],
  );

  const setActiveRunIdAndStore = useCallback((runId: string | null) => {
    setActiveRunId(runId);
    storeActiveRunId(runId);
  }, []);

  const activateMockFallback = useCallback(
    (reason: string, nextStatus: ConsoleStatus = "running") => {
      setSource("mock");
      setHealth(null);
      setPlans(mockConsoleData.plans);
      setSelectedPlanId((current) => current || mockConsoleData.plans[0]?.id || "");
      setSelectedPlanDetail(null);
      setRecentRuns(mockConsoleData.recentRuns);
      setMockStatus(nextStatus);
      setActiveRunId(null);
      storeActiveRunId(null);
      setActiveRun(buildMockRun(nextStatus));
      setSelectedHistoryRunId(null);
      setSelectedHistoryRun(null);
      setEvents(mockConsoleData.getEventsForStatus(nextStatus));
      setArtifacts(mockArtifacts);
      setReport(mockConsoleData.report);
      setEvidence(mockConsoleData.evidence);
      setEvaluation(mockConsoleData.report.evaluation ? { ...mockConsoleData.report.evaluation, run_id: mockConsoleData.report.run_id, artifact_id: "art_evaluation_json" } : null);
      setWalkthroughMap(nextStatus === "idle" ? null : mockConsoleData.walkthroughMap);
      setLoginSession(null);
      setAuthSession(null);
      setVerificationSourceRunId(null);
      setRetryRunId(null);
      setHistoryArtifacts([]);
      setHistoryReport(null);
      setHistoryEvidence(null);
      setHistoryEvaluation(null);
      setHistoryWalkthroughMap(null);
      setConnectionState("closed");
      updateLoading({
        initial: false,
        runHistory: false,
        activeRun: false,
        start: false,
        report: false,
        evidence: false,
        evaluation: false,
        map: false,
        historyRun: false,
        historyReport: false,
        historyEvidence: false,
        historyEvaluation: false,
        historyMap: false,
        verification: false,
      });
      updateErrors({
        initial: reason,
        start: null,
        runHistory: null,
        activeRun: null,
        report: null,
        evidence: null,
        evaluation: null,
        map: null,
        historyRun: null,
        historyReport: null,
        historyEvidence: null,
        historyEvaluation: null,
        historyMap: null,
        verification: null,
      });
    },
    [updateErrors, updateLoading],
  );

  const appendEvents = useCallback((incoming: RunEvent[]) => {
    const fresh = incoming.filter((event) => {
      if (eventSeqsRef.current.has(event.seq)) {
        return false;
      }

      eventSeqsRef.current.add(event.seq);
      lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
      return true;
    });

    if (fresh.length === 0) {
      return [];
    }

    setEvents((current) => mergeRunEvents(current, fresh));
    setActiveRun((current) => fresh.reduce(applyRunEvent, current));

    return fresh;
  }, []);

  const loadArtifacts = useCallback(
    async (runId: string) => {
      try {
        const response = await prodwalkApi.getArtifacts(runId);
        setArtifacts(response.items);
      } catch (error) {
        updateErrors({ activeRun: errorMessage(error) });
      }
    },
    [updateErrors],
  );

  const loadRun = useCallback(
    async (runId: string) => {
      updateLoading({ activeRun: true });
      updateErrors({ activeRun: null });

      try {
        const response = await prodwalkApi.getRun(runId);
        setActiveRun(response.run);
        return response.run;
      } catch (error) {
        const message = errorMessage(error);
        updateErrors({ activeRun: message });
        if (error instanceof ProdwalkApiError && error.status === 404) {
          setActiveRunIdAndStore(null);
        }
        return null;
      } finally {
        updateLoading({ activeRun: false });
      }
    },
    [setActiveRunIdAndStore, updateErrors, updateLoading],
  );

  const loadFinalArtifacts = useCallback(
    async (runId: string) => {
      updateLoading({ report: true, evidence: true, evaluation: true, map: true });
      updateErrors({ report: null, evidence: null, evaluation: null, map: null });

      const [reportResult, evidenceResult, evaluationResult, mapResult] = await Promise.allSettled([
        prodwalkApi.getReport(runId),
        prodwalkApi.getEvidence(runId),
        prodwalkApi.getEvaluation(runId),
        prodwalkApi.getWalkthroughMap(runId),
      ]);

      if (reportResult.status === "fulfilled") {
        setReport(reportResult.value);
      } else {
        setReport(null);
        updateErrors({ report: errorMessage(reportResult.reason) });
      }

      if (evidenceResult.status === "fulfilled") {
        setEvidence(evidenceResult.value);
      } else {
        setEvidence(null);
        updateErrors({ evidence: errorMessage(evidenceResult.reason) });
      }

      if (evaluationResult.status === "fulfilled") {
        setEvaluation(evaluationResult.value);
        setReport((current) => (current ? { ...current, evaluation: evaluationResult.value } : current));
      } else {
        setEvaluation(null);
        updateErrors({ evaluation: errorMessage(evaluationResult.reason) });
      }

      if (mapResult.status === "fulfilled") {
        setWalkthroughMap(mapResult.value);
      } else {
        setWalkthroughMap(null);
        updateErrors({ map: errorMessage(mapResult.reason) });
      }

      updateLoading({ report: false, evidence: false, evaluation: false, map: false });
    },
    [updateErrors, updateLoading],
  );

  const refreshRunHistory = useCallback(async () => {
    if (source === "mock") {
      setRecentRuns(mockConsoleData.recentRuns);
      return;
    }

    updateLoading({ runHistory: true });
    updateErrors({ runHistory: null });

    try {
      const response = await prodwalkApi.listRuns(50);
      setRecentRuns(response.items);
    } catch (error) {
      updateErrors({ runHistory: errorMessage(error) });
    } finally {
      updateLoading({ runHistory: false });
    }
  }, [source, updateErrors, updateLoading]);

  const clearHistorySelection = useCallback(() => {
    setSelectedHistoryRunId(null);
    setSelectedHistoryRun(null);
    setHistoryArtifacts([]);
    setHistoryReport(null);
    setHistoryEvidence(null);
    setHistoryEvaluation(null);
    setHistoryWalkthroughMap(null);
    updateErrors({
      historyRun: null,
      historyReport: null,
      historyEvidence: null,
      historyEvaluation: null,
      historyMap: null,
    });
    updateLoading({
      historyRun: false,
      historyReport: false,
      historyEvidence: false,
      historyEvaluation: false,
      historyMap: false,
    });
  }, [updateErrors, updateLoading]);

  const loadHistoryRunBundle = useCallback(
    async (runId: string) => {
      setSelectedHistoryRunId(runId);
      setSelectedHistoryRun(null);
      setHistoryArtifacts([]);
      setHistoryReport(null);
      setHistoryEvidence(null);
      setHistoryEvaluation(null);
      setHistoryWalkthroughMap(null);
      updateLoading({
        historyRun: true,
        historyReport: true,
        historyEvidence: true,
        historyEvaluation: true,
        historyMap: true,
      });
      updateErrors({
        historyRun: null,
        historyReport: null,
        historyEvidence: null,
        historyEvaluation: null,
        historyMap: null,
      });

      let run: RunDetail;

      try {
        const response = await prodwalkApi.getRun(runId);
        run = response.run;
        setSelectedHistoryRun(run);
      } catch (error) {
        updateErrors({ historyRun: errorMessage(error) });
        updateLoading({
          historyRun: false,
          historyReport: false,
          historyEvidence: false,
          historyEvaluation: false,
          historyMap: false,
        });
        return;
      } finally {
        updateLoading({ historyRun: false });
      }

      const canReadReport = run.report_exists || run.artifact_ids.includes("art_report_md");
      const canReadEvidence = run.evidence_exists || run.artifact_ids.includes("art_evidence_json");
      const canReadEvaluation = run.evaluation_exists || run.artifact_ids.includes("art_evaluation_json");
      const canReadMap = run.artifact_ids.includes("art_walkthrough_map") || canReadEvidence;

      if (!canReadReport) {
        updateErrors({ historyReport: unavailableArtifactMessage("report.md") });
      }
      if (!canReadEvidence) {
        updateErrors({ historyEvidence: unavailableArtifactMessage("evidence.json") });
      }
      if (!canReadEvaluation) {
        updateErrors({ historyEvaluation: unavailableArtifactMessage("evaluation.json") });
      }
      if (!canReadMap) {
        updateErrors({ historyMap: unavailableArtifactMessage("walkthrough_map.json") });
      }

      const [artifactResult, reportResult, evidenceResult, evaluationResult, mapResult] = await Promise.allSettled([
        prodwalkApi.getArtifacts(runId),
        canReadReport ? prodwalkApi.getReport(runId) : Promise.resolve(null),
        canReadEvidence ? prodwalkApi.getEvidence(runId) : Promise.resolve(null),
        canReadEvaluation ? prodwalkApi.getEvaluation(runId) : Promise.resolve(null),
        canReadMap ? prodwalkApi.getWalkthroughMap(runId) : Promise.resolve(null),
      ]);

      if (artifactResult.status === "fulfilled") {
        setHistoryArtifacts(artifactResult.value.items);
      } else {
        updateErrors({ historyRun: errorMessage(artifactResult.reason) });
      }

      if (reportResult.status === "fulfilled") {
        setHistoryReport(reportResult.value);
      } else {
        setHistoryReport(null);
        updateErrors({ historyReport: errorMessage(reportResult.reason) });
      }

      if (evidenceResult.status === "fulfilled") {
        setHistoryEvidence(evidenceResult.value);
      } else {
        setHistoryEvidence(null);
        updateErrors({ historyEvidence: errorMessage(evidenceResult.reason) });
      }

      if (evaluationResult.status === "fulfilled") {
        setHistoryEvaluation(evaluationResult.value);
        setHistoryReport((current) => (current && evaluationResult.value ? { ...current, evaluation: evaluationResult.value } : current));
      } else {
        setHistoryEvaluation(null);
        updateErrors({ historyEvaluation: errorMessage(evaluationResult.reason) });
      }

      if (mapResult.status === "fulfilled") {
        setHistoryWalkthroughMap(mapResult.value);
      } else {
        setHistoryWalkthroughMap(null);
        updateErrors({ historyMap: errorMessage(mapResult.reason) });
      }

      updateLoading({
        historyReport: false,
        historyEvidence: false,
        historyEvaluation: false,
        historyMap: false,
      });
    },
    [updateErrors, updateLoading],
  );

  const handleFreshEvents = useCallback(
    (freshEvents: RunEvent[]) => {
      for (const event of freshEvents) {
        if (shouldRefreshRun(event)) {
          void loadRun(event.run_id);
          void loadArtifacts(event.run_id);
        }

        if (shouldLoadFinalArtifacts(event)) {
          void loadFinalArtifacts(event.run_id);
          void refreshRunHistory();
        }
      }
    },
    [loadArtifacts, loadFinalArtifacts, loadRun, refreshRunHistory],
  );

  const loadRunBundle = useCallback(
    async (runId: string) => {
      eventSeqsRef.current = new Set<number>();
      lastSeqRef.current = 0;
      setEvents([]);
      setArtifacts([]);
      setReport(null);
      setEvidence(null);
      setEvaluation(null);
      setWalkthroughMap(null);
      setAuthSession(null);
      setVerificationSourceRunId(null);
      setRetryRunId(null);

      const run = await loadRun(runId);

      if (!run) {
        return;
      }

      const metadataSessionId =
        typeof run.metadata.verification_session_id === "string" ? run.metadata.verification_session_id : null;
      if (metadataSessionId) {
        prodwalkApi
          .getAuthSession(metadataSessionId)
          .then((response) => {
            setAuthSession(response.session);
            setVerificationSourceRunId(response.session.run_id);
            setRetryRunId(response.session.retry_run_id);
          })
          .catch(() => {
            setAuthSession(null);
          });
      }

      const [eventResult, artifactResult] = await Promise.allSettled([
        prodwalkApi.getEvents(runId, 0, 1000),
        prodwalkApi.getArtifacts(runId),
      ]);

      if (eventResult.status === "fulfilled") {
        const fresh = appendEvents(eventResult.value.items);
        handleFreshEvents(fresh);
      } else {
        updateErrors({ activeRun: errorMessage(eventResult.reason) });
      }

      if (artifactResult.status === "fulfilled") {
        setArtifacts(artifactResult.value.items);
      }

      if (
        terminalRunStatuses.has(run.status) ||
        run.artifact_ids.some((id) => ["art_report_md", "art_evidence_json", "art_evaluation_json", "art_walkthrough_map"].includes(id))
      ) {
        void loadFinalArtifacts(runId);
      }
    },
    [appendEvents, handleFreshEvents, loadFinalArtifacts, loadRun, updateErrors],
  );

  const initializeApi = useCallback(async () => {
    updateLoading({ initial: true });
    updateErrors({ initial: null });

    try {
      const [healthResponse, plansResponse, runsResponse] = await Promise.all([
        prodwalkApi.getHealth(),
        prodwalkApi.getPlans(),
        prodwalkApi.listRuns(20),
      ]);

      setSource("api");
      setHealth(healthResponse);
      setPlans(plansResponse.items);
      setSelectedPlanId((current) => current || plansResponse.items[0]?.id || "");
      setRecentRuns(runsResponse.items);
      setConnectionState((current) => (activeRunId && current === "idle" ? "connecting" : current));
      updateErrors({ initial: null });
    } catch (error) {
      if (shouldUseMockFallback(error)) {
        activateMockFallback(`Mock fallback active because the API is unreachable: ${errorMessage(error)}`);
      } else {
        updateErrors({ initial: errorMessage(error) });
        setPlans(mockConsoleData.plans);
        setRecentRuns(mockConsoleData.recentRuns);
      }
    } finally {
      updateLoading({ initial: false });
    }
  }, [activateMockFallback, activeRunId, updateErrors, updateLoading]);

  useEffect(() => {
    void initializeApi();
  }, [initializeApi]);

  useEffect(() => {
    setLoginSession(null);
  }, [selectedPlanId]);

  useEffect(() => {
    if (source !== "api" || !selectedPlanId) {
      return;
    }

    let canceled = false;
    updateLoading({ planDetail: true });
    updateErrors({ planDetail: null });

    prodwalkApi
      .getPlan(selectedPlanId)
      .then((detail) => {
        if (!canceled) {
          setSelectedPlanDetail(detail);
        }
      })
      .catch((error) => {
        if (!canceled) {
          setSelectedPlanDetail(null);
          updateErrors({ planDetail: errorMessage(error) });
        }
      })
      .finally(() => {
        if (!canceled) {
          updateLoading({ planDetail: false });
        }
      });

    return () => {
      canceled = true;
    };
  }, [selectedPlanId, source, updateErrors, updateLoading]);

  useEffect(() => {
    if (source !== "api" || !activeRunId) {
      return;
    }

    void loadRunBundle(activeRunId);
  }, [activeRunId, loadRunBundle, source]);

  useEffect(() => {
    if (
      source !== "api" ||
      !loginSession ||
      !["running", "awaiting_user"].includes(loginSession.status)
    ) {
      return undefined;
    }

    let canceled = false;
    const timer = window.setInterval(() => {
      prodwalkApi
        .getAuthSession(loginSession.session_id)
        .then((response) => {
          if (!canceled) {
            setLoginSession(response.session);
          }
        })
        .catch(() => {
          // Keep the current local state; the next explicit action will surface the API error.
        });
    }, 3000);

    return () => {
      canceled = true;
      window.clearInterval(timer);
    };
  }, [loginSession?.session_id, loginSession?.status, source]);

  useEffect(() => {
    if (
      source !== "api" ||
      !activeRunId ||
      (activeRun && terminalRunStatuses.has(activeRun.status) && hasTerminalRunEvent)
    ) {
      setConnectionState(activeRunId ? "closed" : "idle");
      return undefined;
    }

    let close: (() => void) | null = null;
    close = openRunEventStream({
      runId: activeRunId,
      afterSeq: lastSeqRef.current,
      onConnectionChange: setConnectionState,
      onEvent: (event) => {
        const fresh = appendEvents([event]);
        handleFreshEvents(fresh);
        if (terminalEventTypes.has(event.type)) {
          close?.();
          setConnectionState("closed");
        }
      },
    });

    return () => close?.();
  }, [activeRun?.status, activeRunId, appendEvents, handleFreshEvents, hasTerminalRunEvent, source]);

  const startRun = useCallback(
    async (options: StartRunOptions = {}) => {
      updateErrors({ start: null, verification: null });

      const targetInput = (options.targetUrl ?? targetUrl).trim();
      let requestTargetUrl: string | null = null;
      if (targetInput) {
        try {
          requestTargetUrl = normalizeTargetUrlForRequest(targetInput);
        } catch (error) {
          updateErrors({ start: errorMessage(error) });
          return;
        }
      }

      const planPath = requestTargetUrl ? "" : selectedPlan?.path ?? selectedPlanId;
      if (!requestTargetUrl && !planPath) {
        updateErrors({ start: "请输入网站 URL，或在高级区域选择一个本地走查计划。" });
        return;
      }

      const requestedMode = options.mode && options.mode !== "unknown" ? options.mode : undefined;
      const runMode = requestedMode ?? (requestTargetUrl ? "browser-use" : "mock");

      if (source === "mock") {
        if (runMode === "mock") {
          activateMockFallback("Mock fallback preview is active because the API is not connected.", "running");
        } else {
          updateErrors({ start: "真实全量走查需要连接 FastAPI 后端，请启动后端后再运行。" });
        }
        return;
      }

      const isBrowserUse = runMode === "browser-use";
      const reportLanguage = options.reportLanguage ?? selectedPlan?.report_language ?? "zh";
      const browserMaxSteps = options.browserMaxSteps ?? (requestTargetUrl ? 80 : 25);
      const browserTimeoutSec = options.browserTimeoutSec ?? (requestTargetUrl ? 1800 : 600);
      const browserDiscoverAllPages = isBrowserUse ? options.browserDiscoverAllPages ?? true : null;
      const browserDiscoveryMaxPages = isBrowserUse ? options.browserDiscoveryMaxPages ?? (requestTargetUrl ? 150 : 120) : null;
      const browserDiscoveryMaxDepth = isBrowserUse ? options.browserDiscoveryMaxDepth ?? 4 : null;
      const verificationMode = isBrowserUse ? options.verificationMode ?? "off" : "off";
      const verificationTimeoutSec = options.verificationTimeoutSec ?? 300;
      const verificationSuccessUrlContains = options.verificationSuccessUrlContains ?? [];
      const verificationLoginUrlContains = options.verificationLoginUrlContains || "/auth/login";
      const concurrency = isBrowserUse ? 1 : options.concurrency ?? 3;
      const authSessionId = isBrowserUse ? options.authSessionId?.trim() || null : null;

      if (requestTargetUrl && isBrowserUse && !authSessionId) {
        updateErrors({ start: "请先完成手动登录并确认登录态，再开始全量走查。" });
        return;
      }

      updateLoading({ start: true });

      const request: RunCreateRequest = {
        config_path: requestTargetUrl ? null : planPath,
        plan: null,
        target_url: requestTargetUrl,
        target_name: options.targetName?.trim() || null,
        target_credentials_ref: options.targetCredentialsRef?.trim() || null,
        mode: runMode,
        out: "runs",
        concurrency,
        report_language: reportLanguage,
        browser_model: null,
        browser_max_steps: browserMaxSteps,
        browser_timeout_sec: browserTimeoutSec,
        browser_discover_all_pages: browserDiscoverAllPages,
        browser_discovery_max_pages: browserDiscoveryMaxPages,
        browser_discovery_max_depth: browserDiscoveryMaxDepth,
        browser_user_data_dir: options.browserUserDataDir?.trim() || null,
        browser_storage_state: options.browserStorageState?.trim() || null,
        auth_session_id: authSessionId,
        verification_mode: verificationMode,
        verification_timeout_sec: verificationTimeoutSec,
        verification_success_url_contains: verificationSuccessUrlContains,
        verification_login_url_contains: verificationLoginUrlContains,
      };

      try {
        const response = await prodwalkApi.createRun(request);
        const nextRunId = response.run.id || response.run_id;

        if (!nextRunId) {
          throw new Error("API did not return a run id.");
        }

        clearHistorySelection();
        setActiveRunIdAndStore(nextRunId);
        setActiveRun({
          ...response.run,
          params: {
            mode: runMode,
            concurrency,
            report_language: reportLanguage,
            plan_source: requestTargetUrl ? "target_url" : "plan",
            target_url: requestTargetUrl,
            target_name: request.target_name,
            target_credentials_ref: request.target_credentials_ref,
            browser_model: null,
            browser_max_steps: browserMaxSteps,
            browser_timeout_sec: browserTimeoutSec,
            browser_discover_all_pages: browserDiscoverAllPages,
            browser_discovery_max_pages: browserDiscoveryMaxPages,
            browser_discovery_max_depth: browserDiscoveryMaxDepth,
            browser_user_data_dir: request.browser_user_data_dir,
            browser_storage_state: request.browser_storage_state,
            auth_session_id: request.auth_session_id,
            auth_status: request.auth_session_id ? "auth_ready" : "auth_not_ready",
            verification_mode: verificationMode,
            verification_timeout_sec: verificationTimeoutSec,
            verification_success_url_contains: verificationSuccessUrlContains,
            verification_login_url_contains: verificationLoginUrlContains,
          },
          artifact_ids: [],
          error: null,
        });
        setEvents([]);
        setArtifacts([]);
        setReport(null);
        setEvidence(null);
        setEvaluation(null);
        setWalkthroughMap(null);
        setAuthSession(null);
        setVerificationSourceRunId(null);
        setRetryRunId(null);
        setConnectionState("connecting");
        void refreshRunHistory();
      } catch (error) {
        if (shouldUseMockFallback(error)) {
          activateMockFallback(`Mock fallback active because create run could not reach the API: ${errorMessage(error)}`);
        } else {
          updateErrors({ start: errorMessage(error) });
        }
      } finally {
        updateLoading({ start: false });
      }
    },
    [
      activateMockFallback,
      refreshRunHistory,
      clearHistorySelection,
      selectedPlan?.path,
      selectedPlan?.report_language,
      selectedPlanId,
      setActiveRunIdAndStore,
      source,
      targetUrl,
      updateErrors,
      updateLoading,
    ],
  );

  const startManualLogin = useCallback(async () => {
    updateErrors({ verification: null, start: null });

    if (source === "mock") {
      updateErrors({ verification: "离线预览无法打开真实浏览器，请先连接 FastAPI 后端。" });
      return;
    }

    let target = firstProductAuthTarget(selectedPlanDetail?.plan);
    const targetInput = targetUrl.trim();
    if (targetInput) {
      try {
        const normalizedUrl = normalizeTargetUrlForRequest(targetInput);
        target = {
          url: normalizedUrl,
          credentialsRef: null,
          successMarkers: successMarkersForUrl(normalizedUrl),
        };
      } catch (error) {
        updateErrors({ verification: errorMessage(error) });
        return;
      }
    }

    if (!target) {
      updateErrors({ verification: "请先输入要走查的网站 URL，或在高级区域选择包含产品 URL 的本地计划。" });
      return;
    }

    updateLoading({ verification: true });

    try {
      const response = await prodwalkApi.createAuthSession({
        run_id: null,
        url: target.url,
        credentials_ref: target.credentialsRef,
        browser_user_data_dir: null,
        browser_storage_state: null,
        success_url_contains: target.successMarkers,
        login_url_contains: "/auth/login",
        timeout_sec: 300,
      });
      setLoginSession(response.session);
    } catch (error) {
      updateErrors({ verification: errorMessage(error) });
    } finally {
      updateLoading({ verification: false });
    }
  }, [selectedPlanDetail?.plan, source, targetUrl, updateErrors, updateLoading]);

  const confirmManualLogin = useCallback(async () => {
    updateErrors({ verification: null, start: null });

    if (!loginSession) {
      updateErrors({ verification: "请先打开浏览器手动登录。" });
      return;
    }

    if (loginSession.auth_status === "auth_ready") {
      return;
    }

    updateLoading({ verification: true });

    try {
      const response = await prodwalkApi.confirmAuthSession(loginSession.session_id, {
        confirmed: true,
        note: "Manual login completed before starting a browser-use run.",
      });
      setLoginSession(response.session);
    } catch (error) {
      updateErrors({ verification: errorMessage(error) });
    } finally {
      updateLoading({ verification: false });
    }
  }, [loginSession, updateErrors, updateLoading]);

  const startAuthenticatedRun = useCallback(async () => {
    updateErrors({ verification: null, start: null });

    if (!loginSession || loginSession.auth_status !== "auth_ready") {
      updateErrors({ start: "请先完成手动登录，等状态变为“登录态已就绪”后再开始真实走查。" });
      return;
    }

    if (targetUrl.trim()) {
      try {
        const expectedUrl = normalizeTargetUrlForRequest(targetUrl);
        const sessionUrl = normalizeTargetUrlForRequest(loginSession.url);
        if (expectedUrl !== sessionUrl) {
          updateErrors({ start: `当前登录态属于 ${loginSession.url}，请重新为 ${expectedUrl} 完成登录。` });
          return;
        }
      } catch (error) {
        updateErrors({ start: errorMessage(error) });
        return;
      }
    }

    await startRun({
      targetUrl,
      mode: "browser-use",
      concurrency: 1,
      reportLanguage: selectedPlan?.report_language ?? "zh",
      browserMaxSteps: 80,
      browserTimeoutSec: 1800,
      browserDiscoverAllPages: true,
      browserDiscoveryMaxPages: 150,
      browserDiscoveryMaxDepth: 4,
      authSessionId: loginSession.session_id,
      verificationMode: "auto",
      verificationTimeoutSec: loginSession.timeout_sec || 300,
      verificationSuccessUrlContains: loginSession.success_url_contains,
      verificationLoginUrlContains: loginSession.login_url_contains || "/auth/login",
    });
  }, [loginSession, selectedPlan?.report_language, startRun, targetUrl, updateErrors]);

  const stopActiveRun = useCallback(async () => {
    updateErrors({ activeRun: null });

    if (source === "mock") {
      setMockStatus("blocked");
      setActiveRun((current) => (current ? { ...current, status: "canceled", completed_at: new Date().toISOString() } : current));
      setConnectionState("closed");
      return;
    }

    if (!activeRunId) {
      updateErrors({ activeRun: "当前没有正在运行的任务。" });
      return;
    }

    if (activeRun && !stopAllowedRunStatuses.has(activeRun.status)) {
      updateErrors({ activeRun: "当前任务已经结束，不需要停止。" });
      return;
    }

    updateLoading({ activeRun: true });

    try {
      const response = await prodwalkApi.cancelRun(activeRunId, "User stopped the run from the web console.");
      setActiveRun((current) =>
        current
          ? {
              ...current,
              status: response.status === "canceled" ? "canceled" : current.status,
              completed_at: new Date().toISOString(),
            }
          : current,
      );
      setConnectionState("closed");
      await loadRun(activeRunId);
      void refreshRunHistory();
    } catch (error) {
      updateErrors({ activeRun: errorMessage(error) });
    } finally {
      updateLoading({ activeRun: false });
    }
  }, [activeRun, activeRunId, loadRun, refreshRunHistory, source, updateErrors, updateLoading]);

  const deleteRunRecord = useCallback(
    async (runId: string) => {
      updateErrors({ runHistory: null });

      if (source === "mock") {
        setRecentRuns((current) => current.filter((run) => run.id !== runId));
        if (selectedHistoryRunId === runId) {
          clearHistorySelection();
        }
        return;
      }

      updateLoading({ runHistory: true });

      try {
        await prodwalkApi.deleteRun(runId);
        if (activeRunId === runId) {
          setActiveRunIdAndStore(null);
          setActiveRun(null);
          setEvents([]);
          setArtifacts([]);
          setReport(null);
          setEvidence(null);
          setEvaluation(null);
          setWalkthroughMap(null);
          setConnectionState("idle");
        }
        if (selectedHistoryRunId === runId) {
          clearHistorySelection();
        }
        await refreshRunHistory();
      } catch (error) {
        updateErrors({ runHistory: errorMessage(error) });
      } finally {
        updateLoading({ runHistory: false });
      }
    },
    [
      activeRunId,
      clearHistorySelection,
      refreshRunHistory,
      selectedHistoryRunId,
      setActiveRunIdAndStore,
      source,
      updateErrors,
      updateLoading,
    ],
  );

  const clearRunRecords = useCallback(async () => {
    updateErrors({ runHistory: null });

    if (source === "mock") {
      setRecentRuns([]);
      clearHistorySelection();
      return;
    }

    updateLoading({ runHistory: true });

    try {
      const response = await prodwalkApi.clearRuns();
      if (activeRunId && response.deleted_run_ids.includes(activeRunId)) {
        setActiveRunIdAndStore(null);
        setActiveRun(null);
        setEvents([]);
        setArtifacts([]);
        setReport(null);
        setEvidence(null);
        setEvaluation(null);
        setWalkthroughMap(null);
        setConnectionState("idle");
      }
      if (selectedHistoryRunId && response.deleted_run_ids.includes(selectedHistoryRunId)) {
        clearHistorySelection();
      }
      if (response.skipped_run_ids.length > 0) {
        updateErrors({ runHistory: `已清除历史记录；${response.skipped_run_ids.length} 个运行中的任务被保留。` });
      }
      await refreshRunHistory();
    } catch (error) {
      updateErrors({ runHistory: errorMessage(error) });
    } finally {
      updateLoading({ runHistory: false });
    }
  }, [
    activeRunId,
    clearHistorySelection,
    refreshRunHistory,
    selectedHistoryRunId,
    setActiveRunIdAndStore,
    source,
    updateErrors,
    updateLoading,
  ]);

  const confirmVerification = useCallback(async () => {
    updateErrors({ verification: null });

    if (source === "mock") {
      setMockStatus("running");
      setActiveRun((current) => (current ? { ...current, status: "running", error: null } : current));
      setEvents(mockConsoleData.getEventsForStatus("running"));
      return;
    }

    if (!activeRunId) {
      updateErrors({ verification: "No active run is waiting for verification." });
      return;
    }

    updateLoading({ verification: true });

    try {
      const response = await prodwalkApi.confirmVerification(activeRunId, {
        confirmed: true,
        note: "Confirmed from the web console.",
      });

      setActiveRun((current) =>
        current
          ? {
              ...current,
              status:
                response.status === "awaiting_verification" ||
                response.status === "blocked" ||
                response.status === "running" ||
                response.status === "failed" ||
                response.status === "timeout" ||
                response.status === "canceled" ||
                response.status === "succeeded"
                  ? response.status
                  : current.status,
              error:
                response.status === "blocked"
                  ? {
                      code: "VERIFICATION_RECORDED_BUT_BLOCKED",
                      message: "Verification was recorded, but the backend no longer has a waiting browser task to continue.",
                    }
                  : current.error,
            }
          : current,
      );

      if (response.status === "blocked") {
        updateErrors({
          verification:
            "Verification was recorded, but the backend reported this run as blocked. Check Details for the latest auth-session event.",
        });
      }

      const eventResult = await prodwalkApi.getEvents(activeRunId, lastSeqRef.current, 100);
      const fresh = appendEvents(eventResult.items);
      handleFreshEvents(fresh);
      void loadRun(activeRunId);
      void refreshRunHistory();
    } catch (error) {
      updateErrors({ verification: errorMessage(error) });
    } finally {
      updateLoading({ verification: false });
    }
  }, [
    activeRunId,
    appendEvents,
    handleFreshEvents,
    loadRun,
    refreshRunHistory,
    source,
    updateErrors,
    updateLoading,
  ]);

  const startAuthSession = useCallback(async () => {
    updateErrors({ verification: null });

    if (source === "mock") {
      updateErrors({ verification: "Mock preview cannot open a visible browser auth session." });
      return;
    }

    if (!activeRun || activeRun.status !== "awaiting_verification") {
      updateErrors({ verification: "当前 run 不在等待人工验证状态，不能创建 auth-session。" });
      return;
    }

    updateLoading({ verification: true });

    try {
      const response = await prodwalkApi.createAuthSession({
        run_id: activeRun.id,
        url: null,
        credentials_ref: null,
        browser_user_data_dir: activeRun.params.browser_user_data_dir ?? null,
        browser_storage_state: activeRun.params.browser_storage_state ?? null,
        success_url_contains: activeRun.params.verification_success_url_contains ?? [],
        login_url_contains: activeRun.params.verification_login_url_contains ?? "/auth/login",
        timeout_sec: activeRun.params.verification_timeout_sec ?? 300,
      });
      setAuthSession(response.session);
      setVerificationSourceRunId(response.session.run_id);
      setRetryRunId(response.session.retry_run_id);

      const eventResult = await prodwalkApi.getEvents(activeRun.id, lastSeqRef.current, 100);
      const fresh = appendEvents(eventResult.items);
      handleFreshEvents(fresh);
      void loadRun(activeRun.id);
      void loadArtifacts(activeRun.id);
      void refreshRunHistory();
    } catch (error) {
      updateErrors({ verification: errorMessage(error) });
    } finally {
      updateLoading({ verification: false });
    }
  }, [
    activeRun,
    appendEvents,
    handleFreshEvents,
    loadArtifacts,
    loadRun,
    refreshRunHistory,
    source,
    updateErrors,
    updateLoading,
  ]);

  const completeAuthSessionAndRetry = useCallback(async () => {
    updateErrors({ verification: null });

    if (source === "mock") {
      setMockStatus("running");
      setActiveRun((current) => (current ? { ...current, status: "running", error: null } : current));
      setEvents(mockConsoleData.getEventsForStatus("running"));
      return;
    }

    if (!authSession) {
      updateErrors({ verification: "请先开始人工验证会话。" });
      return;
    }

    updateLoading({ verification: true });

    try {
      const confirmed =
        authSession.status === "succeeded"
          ? authSession
          : (
              await prodwalkApi.confirmAuthSession(authSession.session_id, {
                confirmed: true,
                note: "Confirmed from the web console.",
              })
            ).session;
      setAuthSession(confirmed);
      setVerificationSourceRunId(confirmed.run_id);

      if (!confirmed.run_id) {
        updateErrors({ verification: "这个登录会话不属于暂停中的任务，请用“开始真实走查”启动新任务。" });
        return;
      }

      const retryResponse = await prodwalkApi.retryRunAfterVerification(confirmed.run_id, {
        session_id: confirmed.session_id,
        note: "Retry after manual verification from the web console.",
      });
      const nextRetryRunId = retryResponse.retry_run_id;
      setRetryRunId(nextRetryRunId);
      setAuthSession(retryResponse.session ?? confirmed);

      clearHistorySelection();
      setActiveRunIdAndStore(nextRetryRunId);
      setEvents([]);
      setArtifacts([]);
      setReport(null);
      setEvidence(null);
      setEvaluation(null);
      setWalkthroughMap(null);
      setConnectionState("connecting");
      void loadRunBundle(nextRetryRunId);
      void refreshRunHistory();
    } catch (error) {
      updateErrors({ verification: errorMessage(error) });
    } finally {
      updateLoading({ verification: false });
    }
  }, [
    authSession,
    clearHistorySelection,
    loadRunBundle,
    refreshRunHistory,
    setActiveRunIdAndStore,
    source,
    updateErrors,
    updateLoading,
  ]);

  const selectRun = useCallback(
    (runId: string) => {
      if (runId === activeRunId) {
        clearHistorySelection();
        return;
      }

      if (source === "mock") {
        const summary = mockConsoleData.recentRuns.find((run) => run.id === runId) ?? mockConsoleData.recentRuns[0];
        if (!summary) {
          return;
        }
        const detail = mockDetailFromSummary(summary);
        const evaluationPayload = summary.evaluation_exists && mockConsoleData.report.evaluation
          ? { ...mockConsoleData.report.evaluation, run_id: summary.id, artifact_id: "art_evaluation_json" }
          : null;

        setSelectedHistoryRunId(summary.id);
        setSelectedHistoryRun(detail);
        setHistoryArtifacts(mockArtifacts.map((artifact) => ({ ...artifact, run_id: summary.id })));
        setHistoryReport(summary.report_exists ? { ...mockConsoleData.report, run_id: summary.id, evaluation: evaluationPayload } : null);
        setHistoryEvidence(summary.evidence_exists ? { ...mockConsoleData.evidence, run_id: summary.id } : null);
        setHistoryEvaluation(evaluationPayload);
        setHistoryWalkthroughMap(summary.evidence_exists ? { ...mockConsoleData.walkthroughMap, run_id: summary.id } : null);
        updateErrors({
          historyRun: null,
          historyReport: summary.report_exists ? null : unavailableArtifactMessage("report.md"),
          historyEvidence: summary.evidence_exists ? null : unavailableArtifactMessage("evidence.json"),
          historyEvaluation: summary.evaluation_exists ? null : unavailableArtifactMessage("evaluation.json"),
          historyMap: summary.evidence_exists ? null : unavailableArtifactMessage("walkthrough_map.json"),
        });
        updateLoading({
          historyRun: false,
          historyReport: false,
          historyEvidence: false,
          historyEvaluation: false,
          historyMap: false,
        });
        return;
      }

      void loadHistoryRunBundle(runId);
    },
    [activeRunId, clearHistorySelection, loadHistoryRunBundle, source, updateErrors, updateLoading],
  );

  const setMockPreviewStatus = useCallback(
    (status: ConsoleStatus) => {
      if (source !== "mock") {
        return;
      }

      clearHistorySelection();
      setMockStatus(status);
      setActiveRun(buildMockRun(status));
      setEvents(mockConsoleData.getEventsForStatus(status));
      setReport(status === "idle" ? null : mockConsoleData.report);
      setEvidence(status === "idle" ? null : mockConsoleData.evidence);
      setEvaluation(status === "idle" || !mockConsoleData.report.evaluation ? null : { ...mockConsoleData.report.evaluation, run_id: mockConsoleData.report.run_id, artifact_id: "art_evaluation_json" });
      setWalkthroughMap(status === "idle" ? null : mockConsoleData.walkthroughMap);
      setArtifacts(status === "idle" ? [] : mockArtifacts);
      setConnectionState(status === "idle" ? "idle" : "closed");
    },
    [clearHistorySelection, source],
  );

  const retryApi = useCallback(() => {
    clearHistorySelection();
    setSource("api");
    setActiveRunId(readStoredActiveRunId());
    void initializeApi();
  }, [clearHistorySelection, initializeApi]);

  const viewingHistory = Boolean(selectedHistoryRunId && selectedHistoryRunId !== activeRunId);
  const viewedRun = viewingHistory ? selectedHistoryRun : activeRun;
  const viewedStatus = viewedRun ? toConsoleStatus(viewedRun.status) : "idle";
  const viewedReport = viewingHistory ? historyReport : report;
  const viewedEvidence = viewingHistory ? historyEvidence : evidence;
  const viewedEvaluation = viewingHistory ? historyEvaluation : evaluation;
  const viewedMap = viewingHistory ? historyWalkthroughMap : walkthroughMap;
  const viewedArtifacts = viewingHistory ? historyArtifacts : artifacts;
  const viewedReportError = viewingHistory ? errors.historyReport : errors.report;
  const viewedEvidenceError = viewingHistory ? errors.historyEvidence : errors.evidence;
  const viewedEvaluationError = viewingHistory ? errors.historyEvaluation : errors.evaluation;
  const viewedMapError = viewingHistory ? errors.historyMap : errors.map;
  const viewedReportLoading = viewingHistory ? loading.historyReport : loading.report;
  const viewedEvidenceLoading = viewingHistory ? loading.historyEvidence : loading.evidence;
  const viewedEvaluationLoading = viewingHistory ? loading.historyEvaluation : loading.evaluation;
  const viewedMapLoading = viewingHistory ? loading.historyMap : loading.map;

  return {
    source,
    health,
    plans,
    targetUrl,
    selectedPlan,
    selectedPlanId,
    selectedPlanDetail,
    recentRuns,
    activeRun,
    activeRunId,
    selectedHistoryRun,
    selectedHistoryRunId,
    viewingHistory,
    viewedRun,
    viewedStatus,
    agents,
    events,
    artifacts,
    report,
    evidence,
    evaluation,
    walkthroughMap,
    historyWalkthroughMap,
    loginSession,
    loginAuthStatus: authReadinessFromSession(loginSession),
    authSession,
    verificationSourceRunId,
    retryRunId,
    viewedArtifacts,
    viewedReport,
    viewedEvidence,
    viewedEvaluation,
    viewedMap,
    consoleStatus,
    connectionState,
    loading,
    errors,
    mockStatus,
    startRun,
    startManualLogin,
    confirmManualLogin,
    startAuthenticatedRun,
    stopActiveRun,
    deleteRunRecord,
    clearRunRecords,
    confirmVerification,
    startAuthSession,
    completeAuthSessionAndRetry,
    selectRun,
    clearHistorySelection,
    refreshRunHistory,
    setTargetUrl: updateTargetUrl,
    setSelectedPlanId,
    setMockPreviewStatus,
    retryApi,
    reportError: errors.report,
    evidenceError: errors.evidence,
    viewedReportError,
    viewedEvidenceError,
    viewedEvaluationError,
    viewedMapError,
    viewedReportLoading,
    viewedEvidenceLoading,
    viewedEvaluationLoading,
    viewedMapLoading,
    runError: formatApiError(activeRun?.error),
  };
}
