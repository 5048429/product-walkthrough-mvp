import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isNetworkError, ProdwalkApiError, prodwalkApi } from "../api/client";
import { openRunEventStream, type RunEventConnectionState } from "../api/sse";
import { mockConsoleData } from "../api/mockConsoleData";
import { mockArtifacts } from "../mock/artifacts";
import type {
  AgentExecution,
  AgentStatus,
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
} from "../types/contracts";
import { formatApiError, toConsoleStatus, toRunStatus } from "../types/contracts";

const ACTIVE_RUN_KEY = "prodwalk.activeRunId";
const terminalRunStatuses = new Set<RunStatus>(["succeeded", "failed", "canceled"]);
const terminalEventTypes = new Set(["run.completed", "run.failed", "run.canceled"]);
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
  mode: RunMode;
  concurrency: number;
  reportLanguage: string;
  browserMaxSteps: number;
  verificationMode: VerificationMode;
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
  historyRun: boolean;
  historyReport: boolean;
  historyEvidence: boolean;
  historyEvaluation: boolean;
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
  historyRun: string | null;
  historyReport: string | null;
  historyEvidence: string | null;
  historyEvaluation: string | null;
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
    return `${error.code}: ${error.message}`;
  }

  return error instanceof Error ? error.message : "Unknown API error.";
}

function shouldUseMockFallback(error: unknown): boolean {
  return isNetworkError(error);
}

function buildMockRun(status: ConsoleStatus): RunDetail | null {
  if (status === "idle") {
    return null;
  }

  const completedAt = status === "done" || status === "failed" ? "2026-06-16T08:31:16Z" : null;
  const base = mockConsoleData.activeRun;
  const progress =
    status === "done"
      ? {
          ...base.progress,
          completed_scenarios: base.progress.total_scenarios,
        }
      : status === "failed"
        ? {
            ...base.progress,
            completed_scenarios: 0,
            failed_scenarios: 1,
          }
        : status === "blocked"
          ? {
              ...base.progress,
              completed_scenarios: 1,
              failed_scenarios: 0,
            }
          : base.progress;

  return {
    ...base,
    status: toRunStatus(status),
    completed_at: completedAt,
    progress,
    error:
      status === "failed"
        ? "Mock adapter reported a simulated failure."
        : status === "blocked"
          ? "Manual verification required before continuing browser-use flow."
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
      Boolean(event.artifact_ids?.some((id) => ["art_evidence_json", "art_report_md", "art_evaluation_json"].includes(id)))
    );
  }

  return false;
}

export function useProdwalkConsole() {
  const [source, setSource] = useState<ConsoleDataSource>("api");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
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
  const [historyArtifacts, setHistoryArtifacts] = useState<Artifact[]>([]);
  const [historyReport, setHistoryReport] = useState<ReportResponse | null>(null);
  const [historyEvidence, setHistoryEvidence] = useState<EvidenceResponse | null>(null);
  const [historyEvaluation, setHistoryEvaluation] = useState<EvaluationResponse | null>(null);
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
    historyRun: false,
    historyReport: false,
    historyEvidence: false,
    historyEvaluation: false,
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
    historyRun: null,
    historyReport: null,
    historyEvidence: null,
    historyEvaluation: null,
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
      setHistoryArtifacts([]);
      setHistoryReport(null);
      setHistoryEvidence(null);
      setHistoryEvaluation(null);
      setConnectionState("closed");
      updateLoading({
        initial: false,
        runHistory: false,
        activeRun: false,
        start: false,
        report: false,
        evidence: false,
        evaluation: false,
        historyRun: false,
        historyReport: false,
        historyEvidence: false,
        historyEvaluation: false,
      });
      updateErrors({
        initial: reason,
        start: null,
        runHistory: null,
        activeRun: null,
        report: null,
        evidence: null,
        evaluation: null,
        historyRun: null,
        historyReport: null,
        historyEvidence: null,
        historyEvaluation: null,
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
      updateLoading({ report: true, evidence: true, evaluation: true });
      updateErrors({ report: null, evidence: null, evaluation: null });

      const [reportResult, evidenceResult, evaluationResult] = await Promise.allSettled([
        prodwalkApi.getReport(runId),
        prodwalkApi.getEvidence(runId),
        prodwalkApi.getEvaluation(runId),
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

      updateLoading({ report: false, evidence: false, evaluation: false });
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
    updateErrors({
      historyRun: null,
      historyReport: null,
      historyEvidence: null,
      historyEvaluation: null,
    });
    updateLoading({
      historyRun: false,
      historyReport: false,
      historyEvidence: false,
      historyEvaluation: false,
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
      updateLoading({
        historyRun: true,
        historyReport: true,
        historyEvidence: true,
        historyEvaluation: true,
      });
      updateErrors({
        historyRun: null,
        historyReport: null,
        historyEvidence: null,
        historyEvaluation: null,
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
        });
        return;
      } finally {
        updateLoading({ historyRun: false });
      }

      const canReadReport = run.report_exists || run.artifact_ids.includes("art_report_md");
      const canReadEvidence = run.evidence_exists || run.artifact_ids.includes("art_evidence_json");
      const canReadEvaluation = run.evaluation_exists || run.artifact_ids.includes("art_evaluation_json");

      if (!canReadReport) {
        updateErrors({ historyReport: unavailableArtifactMessage("report.md") });
      }
      if (!canReadEvidence) {
        updateErrors({ historyEvidence: unavailableArtifactMessage("evidence.json") });
      }
      if (!canReadEvaluation) {
        updateErrors({ historyEvaluation: unavailableArtifactMessage("evaluation.json") });
      }

      const [artifactResult, reportResult, evidenceResult, evaluationResult] = await Promise.allSettled([
        prodwalkApi.getArtifacts(runId),
        canReadReport ? prodwalkApi.getReport(runId) : Promise.resolve(null),
        canReadEvidence ? prodwalkApi.getEvidence(runId) : Promise.resolve(null),
        canReadEvaluation ? prodwalkApi.getEvaluation(runId) : Promise.resolve(null),
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

      updateLoading({
        historyReport: false,
        historyEvidence: false,
        historyEvaluation: false,
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

      const run = await loadRun(runId);

      if (!run) {
        return;
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

      if (terminalRunStatuses.has(run.status) || run.artifact_ids.some((id) => ["art_report_md", "art_evidence_json", "art_evaluation_json"].includes(id))) {
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
    async (options: StartRunOptions) => {
      updateErrors({ start: null });

      if (options.mode !== "mock") {
        updateErrors({ start: "Browser-use runs are gated until the backend exposes the browser-use API path." });
        return;
      }

      if (source === "mock") {
        activateMockFallback("Mock fallback preview is active because the API is not connected.", "running");
        return;
      }

      const planPath = selectedPlan?.path ?? selectedPlanId;

      if (!planPath) {
        updateErrors({ start: "Select a local plan before starting a run." });
        return;
      }

      updateLoading({ start: true });

      const request: RunCreateRequest = {
        config_path: planPath,
        plan: null,
        mode: "mock",
        out: "runs",
        concurrency: options.concurrency,
        report_language: options.reportLanguage,
        browser_model: null,
        browser_max_steps: options.browserMaxSteps,
        browser_timeout_sec: 600,
        browser_user_data_dir: null,
        browser_storage_state: null,
        verification_mode: options.verificationMode,
        verification_timeout_sec: 300,
        verification_success_url_contains: [],
        verification_login_url_contains: "/auth/login",
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
            mode: "mock",
            concurrency: options.concurrency,
            report_language: options.reportLanguage,
            browser_model: null,
            browser_max_steps: options.browserMaxSteps,
            browser_timeout_sec: 600,
            verification_mode: options.verificationMode,
          },
          artifact_ids: [],
          error: null,
        });
        setEvents([]);
        setArtifacts([]);
        setReport(null);
        setEvidence(null);
        setEvaluation(null);
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
      selectedPlanId,
      setActiveRunIdAndStore,
      source,
      updateErrors,
      updateLoading,
    ],
  );

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
        updateErrors({
          historyRun: null,
          historyReport: summary.report_exists ? null : unavailableArtifactMessage("report.md"),
          historyEvidence: summary.evidence_exists ? null : unavailableArtifactMessage("evidence.json"),
          historyEvaluation: summary.evaluation_exists ? null : unavailableArtifactMessage("evaluation.json"),
        });
        updateLoading({
          historyRun: false,
          historyReport: false,
          historyEvidence: false,
          historyEvaluation: false,
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
  const viewedArtifacts = viewingHistory ? historyArtifacts : artifacts;
  const viewedReportError = viewingHistory ? errors.historyReport : errors.report;
  const viewedEvidenceError = viewingHistory ? errors.historyEvidence : errors.evidence;
  const viewedEvaluationError = viewingHistory ? errors.historyEvaluation : errors.evaluation;
  const viewedReportLoading = viewingHistory ? loading.historyReport : loading.report;
  const viewedEvidenceLoading = viewingHistory ? loading.historyEvidence : loading.evidence;
  const viewedEvaluationLoading = viewingHistory ? loading.historyEvaluation : loading.evaluation;

  return {
    source,
    health,
    plans,
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
    viewedArtifacts,
    viewedReport,
    viewedEvidence,
    viewedEvaluation,
    consoleStatus,
    connectionState,
    loading,
    errors,
    mockStatus,
    startRun,
    selectRun,
    clearHistorySelection,
    refreshRunHistory,
    setSelectedPlanId,
    setMockPreviewStatus,
    retryApi,
    reportError: errors.report,
    evidenceError: errors.evidence,
    viewedReportError,
    viewedEvidenceError,
    viewedEvaluationError,
    viewedReportLoading,
    viewedEvidenceLoading,
    viewedEvaluationLoading,
    runError: formatApiError(activeRun?.error) ?? errors.activeRun,
  };
}
