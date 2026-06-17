import { useEffect, useMemo, useState } from "react";
import { ArtifactLink } from "../common/ArtifactLink";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { EvidenceItemCard } from "./EvidenceItemCard";
import { scrollEvidenceIntoView } from "./evidenceFocus";
import { ScreenshotPreview } from "./ScreenshotPreview";
import {
  EVIDENCE_FOCUS_EVENT,
  type Artifact,
  type ConsoleStatus,
  type EvidenceFocusRequest,
  type EvidenceItem,
  type EvidenceResponse,
  type WalkthroughResult,
} from "../../types/contracts";

type EvidenceGroupBy = "product" | "scenario" | "kind" | "status";

interface EvidenceListProps {
  evidence: EvidenceResponse | null;
  artifacts?: Artifact[];
  status?: ConsoleStatus;
  error?: string | null;
  loading?: boolean;
  initialGroupBy?: EvidenceGroupBy;
}

const groupOptions: EvidenceGroupBy[] = ["product", "scenario", "kind", "status"];
const allFilter = "all";

function inferStatus(evidence: EvidenceResponse | null, status?: ConsoleStatus): ConsoleStatus {
  if (status) {
    return status;
  }

  return evidence?.evidence.length ? "done" : "idle";
}

function getResultForEvidence(item: EvidenceItem, results: WalkthroughResult[]): WalkthroughResult | undefined {
  return results.find((result) => result.product === item.product && result.scenario_id === item.scenario_id);
}

function getItemStatus(item: EvidenceItem, results: WalkthroughResult[]): string {
  if (item.status) {
    return item.status;
  }

  if (item.errors?.length) {
    return "friction";
  }

  return getResultForEvidence(item, results)?.status ?? "completed";
}

function normalizeStatusClass(status: string): string {
  if (status === "completed" || status === "succeeded") {
    return "done";
  }

  if (status === "blocked" || status === "awaiting_verification" || status === "friction" || status === "waiting") {
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

function getScreenshotArtifactIds(item: EvidenceItem): string[] {
  if (item.screenshot_artifact_ids?.length) {
    return item.screenshot_artifact_ids;
  }

  return item.screenshot_artifact_id ? [item.screenshot_artifact_id] : [];
}

function getLinkedArtifactIds(item: EvidenceItem): string[] {
  return Array.from(new Set([...(item.artifact_ids ?? []), ...getScreenshotArtifactIds(item)]));
}

function itemReferencesArtifact(item: EvidenceItem, artifactId: string): boolean {
  return getLinkedArtifactIds(item).includes(artifactId);
}

function getGroupKey(item: EvidenceItem, groupBy: EvidenceGroupBy, results: WalkthroughResult[]): string {
  if (groupBy === "product") {
    return item.product;
  }

  if (groupBy === "scenario") {
    return item.scenario_title ?? item.scenario_id;
  }

  if (groupBy === "kind") {
    return item.kind.replaceAll("_", " ");
  }

  return getItemStatus(item, results);
}

function groupEvidence(
  items: EvidenceItem[],
  groupBy: EvidenceGroupBy,
  results: WalkthroughResult[],
): Array<[string, EvidenceItem[]]> {
  const groups = new Map<string, EvidenceItem[]>();

  for (const item of items) {
    const key = getGroupKey(item, groupBy, results);
    const group = groups.get(key) ?? [];
    group.push(item);
    groups.set(key, group);
  }

  return Array.from(groups.entries());
}

function getState(status: ConsoleStatus, hasEvidence: boolean, error?: string | null) {
  if (error && !hasEvidence) {
    return {
      kind: "error" as const,
      title: "Evidence artifact unavailable",
      message: error,
      tone: "failed" as const,
    };
  }

  if (status === "idle") {
    return {
      kind: "empty" as const,
      title: "No evidence selected",
      message: "Select or start a run before inspecting collected evidence.",
    };
  }

  if (status === "running" && !hasEvidence) {
    return {
      kind: "empty" as const,
      title: "Evidence collection running",
      message: "Evidence will appear here as walker and extractor stages emit items.",
    };
  }

  if (status === "blocked" && !hasEvidence) {
    return {
      kind: "error" as const,
      title: "Evidence blocked",
      message: "The run is blocked before evidence.json was written.",
      tone: "blocked" as const,
    };
  }

  if (status === "failed" && !hasEvidence) {
    return {
      kind: "error" as const,
      title: "Evidence read failed",
      message: "The run failed before recoverable evidence was available.",
      tone: "failed" as const,
    };
  }

  return {
    kind: "ready" as const,
    title: "",
    message: "",
  };
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function itemMatchesSearch(item: EvidenceItem, query: string): boolean {
  const normalizedQuery = query.trim().toLowerCase();

  if (!normalizedQuery) {
    return true;
  }

  return [item.title, item.summary, item.url ?? "", item.id]
    .join(" ")
    .toLowerCase()
    .includes(normalizedQuery);
}

function findFocusedItem(detail: EvidenceFocusRequest, items: EvidenceItem[]): EvidenceItem | null {
  if (detail.evidenceId) {
    const byId = items.find((item) => item.id === detail.evidenceId);
    if (byId) {
      return byId;
    }
  }

  if (detail.artifactId) {
    return items.find((item) => itemReferencesArtifact(item, detail.artifactId ?? "")) ?? null;
  }

  return null;
}

export function EvidenceList({ evidence, artifacts, status, error, loading = false, initialGroupBy = "product" }: EvidenceListProps) {
  const [groupBy, setGroupBy] = useState<EvidenceGroupBy>(initialGroupBy);
  const [selectedId, setSelectedId] = useState<string | null>(evidence?.evidence[0]?.id ?? null);
  const [query, setQuery] = useState("");
  const [productFilter, setProductFilter] = useState(allFilter);
  const [scenarioFilter, setScenarioFilter] = useState(allFilter);
  const [kindFilter, setKindFilter] = useState(allFilter);
  const [statusFilter, setStatusFilter] = useState(allFilter);
  const items = evidence?.evidence ?? [];
  const results = evidence?.results ?? [];
  const resolvedArtifacts = artifacts ?? evidence?.artifacts ?? [];
  const effectiveStatus = inferStatus(evidence, status);
  const state = getState(effectiveStatus, items.length > 0, error);

  const filterOptions = useMemo(
    () => ({
      products: uniqueSorted(items.map((item) => item.product)),
      scenarios: uniqueSorted(items.map((item) => item.scenario_title ?? item.scenario_id)),
      kinds: uniqueSorted(items.map((item) => item.kind)),
      statuses: uniqueSorted(items.map((item) => getItemStatus(item, results))),
    }),
    [items, results],
  );

  const filteredItems = useMemo(() => {
    return items
      .filter((item) => productFilter === allFilter || item.product === productFilter)
      .filter((item) => scenarioFilter === allFilter || (item.scenario_title ?? item.scenario_id) === scenarioFilter)
      .filter((item) => kindFilter === allFilter || item.kind === kindFilter)
      .filter((item) => statusFilter === allFilter || getItemStatus(item, results) === statusFilter)
      .filter((item) => itemMatchesSearch(item, query));
  }, [items, kindFilter, productFilter, query, results, scenarioFilter, statusFilter]);

  const groups = useMemo(() => groupEvidence(filteredItems, groupBy, results), [filteredItems, groupBy, results]);
  const selectedItem = filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0] ?? null;
  const selectedStatus = selectedItem ? getItemStatus(selectedItem, results) : null;
  const selectedScreenshotIds = selectedItem ? getScreenshotArtifactIds(selectedItem) : [];
  const selectedArtifactIds = selectedItem ? getLinkedArtifactIds(selectedItem) : [];
  const hasActiveFilters =
    Boolean(query.trim()) ||
    productFilter !== allFilter ||
    scenarioFilter !== allFilter ||
    kindFilter !== allFilter ||
    statusFilter !== allFilter;

  useEffect(() => {
    if (items.length === 0) {
      setSelectedId(null);
      return;
    }

    if (!selectedId || !items.some((item) => item.id === selectedId)) {
      setSelectedId(items[0].id);
    }
  }, [items, selectedId]);

  useEffect(() => {
    if (filteredItems.length === 0) {
      return;
    }

    if (!selectedId || !filteredItems.some((item) => item.id === selectedId)) {
      setSelectedId(filteredItems[0].id);
    }
  }, [filteredItems, selectedId]);

  useEffect(() => {
    const handleFocus = (event: Event) => {
      const detail = (event as CustomEvent<EvidenceFocusRequest>).detail;

      if (!detail) {
        return;
      }

      if (detail.runId && evidence?.run_id && detail.runId !== evidence.run_id) {
        return;
      }

      const focusedItem = findFocusedItem(detail, items);

      if (!focusedItem) {
        return;
      }

      setQuery("");
      setProductFilter(allFilter);
      setScenarioFilter(allFilter);
      setKindFilter(allFilter);
      setStatusFilter(allFilter);
      setSelectedId(focusedItem.id);
      scrollEvidenceIntoView(focusedItem.id);
    };

    window.addEventListener(EVIDENCE_FOCUS_EVENT, handleFocus);
    return () => window.removeEventListener(EVIDENCE_FOCUS_EVENT, handleFocus);
  }, [evidence?.run_id, items]);

  const resetFilters = () => {
    setQuery("");
    setProductFilter(allFilter);
    setScenarioFilter(allFilter);
    setKindFilter(allFilter);
    setStatusFilter(allFilter);
  };

  return (
    <section className="panel evidence-panel" aria-labelledby="evidence-title">
      <div className="panel-header">
        <div>
          <h2 id="evidence-title">Evidence</h2>
          <p>
            {evidence
              ? `${evidence.artifact_id} / ${filteredItems.length} of ${items.length} items`
              : "No evidence artifact selected"}
          </p>
        </div>
        <ArtifactLink
          artifactId={evidence?.artifact_id}
          artifacts={resolvedArtifacts}
          runId={evidence?.run_id}
          label="evidence.json"
          disabledReason={evidence ? undefined : "Evidence artifact is not ready"}
        />
      </div>

      <div className="filter-row evidence-group-control" aria-label="Evidence search and filters">
        <label className="field" style={{ flex: "1 1 220px", marginBottom: 0 }}>
          <span>Search</span>
          <input value={query} placeholder="title, summary, URL" onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="field" style={{ flex: "1 1 150px", marginBottom: 0 }}>
          <span>Product</span>
          <select value={productFilter} onChange={(event) => setProductFilter(event.target.value)}>
            <option value={allFilter}>all</option>
            {filterOptions.products.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="field" style={{ flex: "1 1 170px", marginBottom: 0 }}>
          <span>Scenario</span>
          <select value={scenarioFilter} onChange={(event) => setScenarioFilter(event.target.value)}>
            <option value={allFilter}>all</option>
            {filterOptions.scenarios.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="field" style={{ flex: "1 1 130px", marginBottom: 0 }}>
          <span>Kind</span>
          <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
            <option value={allFilter}>all</option>
            {filterOptions.kinds.map((option) => (
              <option key={option} value={option}>
                {option.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label className="field" style={{ flex: "1 1 130px", marginBottom: 0 }}>
          <span>Status</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value={allFilter}>all</option>
            {filterOptions.statuses.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button type="button" disabled={!hasActiveFilters} onClick={resetFilters}>
          Reset
        </button>
      </div>

      <div className="filter-row evidence-group-control" aria-label="Evidence grouping">
        <span className="section-title">Group</span>
        {groupOptions.map((option) => (
          <button key={option} type="button" className={option === groupBy ? "selected" : ""} onClick={() => setGroupBy(option)}>
            {option}
          </button>
        ))}
      </div>

      {loading && items.length === 0 ? (
        <EmptyState title="Loading evidence" message="Reading evidence.json from the API." />
      ) : null}
      {!loading && state.kind === "empty" ? <EmptyState title={state.title} message={state.message} /> : null}
      {state.kind === "error" ? (
        <ErrorState title={state.title} message={state.message} tone={state.tone} details={error ?? undefined} />
      ) : null}

      {items.length > 0 ? (
        <>
          {(effectiveStatus === "running" || effectiveStatus === "blocked" || effectiveStatus === "failed") ? (
            <div className={`partial-banner partial-banner-${effectiveStatus}`}>
              <strong>{effectiveStatus === "running" ? "Partial evidence" : "Recoverable evidence"}</strong>
              <span>
                {effectiveStatus === "running"
                  ? "New items can arrive while the run continues."
                  : "Available evidence remains visible for review."}
              </span>
            </div>
          ) : null}

          {filteredItems.length === 0 ? (
            <EmptyState title="No matching evidence" message="Try a different search or filter combination." compact />
          ) : (
            <div className="evidence-workspace">
              <div className="evidence-list" role="list">
                {groups.map(([group, groupItems]) => (
                  <section key={group} className="evidence-group" aria-label={`${groupBy}: ${group}`}>
                    <div className="evidence-group-heading">
                      <strong>{group}</strong>
                      <span>{groupItems.length}</span>
                    </div>
                    {groupItems.map((item) => (
                      <EvidenceItemCard
                        key={item.id}
                        item={item}
                        result={getResultForEvidence(item, results)}
                        artifacts={resolvedArtifacts}
                        runId={evidence?.run_id}
                        selected={item.id === selectedItem?.id}
                        onSelect={(nextItem) => setSelectedId(nextItem.id)}
                      />
                    ))}
                  </section>
                ))}
              </div>

              <aside className="evidence-detail-panel">
                {selectedItem ? (
                  <>
                    <div className="section-title">Selected Evidence</div>
                    <h3>{selectedItem.title}</h3>
                    <span className={`evidence-status-pill status-${normalizeStatusClass(selectedStatus ?? "completed")}`}>
                      {selectedStatus}
                    </span>
                    <p>{selectedItem.summary}</p>
                    <dl className="detail-list">
                      <div>
                        <dt>ID</dt>
                        <dd>{selectedItem.id}</dd>
                      </div>
                      <div>
                        <dt>Product</dt>
                        <dd>{selectedItem.product}</dd>
                      </div>
                      <div>
                        <dt>Scenario</dt>
                        <dd>{selectedItem.scenario_title ?? selectedItem.scenario_id}</dd>
                      </div>
                      <div>
                        <dt>Kind</dt>
                        <dd>{selectedItem.kind.replaceAll("_", " ")}</dd>
                      </div>
                      <div>
                        <dt>URL</dt>
                        <dd>
                          {selectedItem.url ? (
                            <a href={selectedItem.url} target="_blank" rel="noreferrer">
                              {selectedItem.url}
                            </a>
                          ) : (
                            "--"
                          )}
                        </dd>
                      </div>
                    </dl>
                    {selectedScreenshotIds.length ? (
                      <div className="linked-list">
                        <div className="section-title">Screenshots</div>
                        {selectedScreenshotIds.map((artifactId) => (
                          <ScreenshotPreview
                            key={artifactId}
                            artifactId={artifactId}
                            artifacts={resolvedArtifacts}
                            runId={evidence?.run_id}
                            alt={`${selectedItem.title} screenshot`}
                            variant="detail"
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="linked-list">
                        <div className="section-title">Screenshots</div>
                        <ScreenshotPreview variant="detail" />
                      </div>
                    )}
                    {selectedArtifactIds.length ? (
                      <div className="linked-list">
                        <div className="section-title">Artifacts</div>
                        {selectedArtifactIds.map((artifactId) => (
                          <ArtifactLink
                            key={artifactId}
                            artifactId={artifactId}
                            artifacts={resolvedArtifacts}
                            runId={evidence?.run_id}
                            label={artifactId}
                          />
                        ))}
                      </div>
                    ) : null}
                    {selectedItem.final_output ? <p className="raw-note">{selectedItem.final_output}</p> : null}
                    {selectedItem.finding_ids?.length ? (
                      <div className="linked-list">
                        <div className="section-title">Linked Findings</div>
                        {selectedItem.finding_ids.map((findingId) => (
                          <span key={findingId}>{findingId}</span>
                        ))}
                      </div>
                    ) : null}
                    {selectedItem.data ? (
                      <details className="linked-list">
                        <summary className="section-title">Sanitized Data</summary>
                        <pre style={{ overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12 }}>
                          {JSON.stringify(selectedItem.data, null, 2)}
                        </pre>
                      </details>
                    ) : null}
                  </>
                ) : (
                  <EmptyState title="No evidence selected" message="Choose an evidence item to inspect its details." compact />
                )}
              </aside>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
