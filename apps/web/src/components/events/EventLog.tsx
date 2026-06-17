import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { RunEventConnectionState } from "../../api/sse";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { StatusBadge } from "../StatusBadge";
import { EVIDENCE_FOCUS_EVENT, type EventLevel, type EvidenceFocusRequest, type RunEvent } from "../../types/contracts";

const levels: Array<EventLevel | "all"> = ["all", "debug", "info", "warn", "error"];

interface EventLogProps {
  events: RunEvent[];
  activeRunId?: string | null;
  connectionState?: RunEventConnectionState;
  loading?: boolean;
  error?: string | null;
  source?: "api" | "mock";
}

function uniqueValues(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort();
}

function getAgentFilterValue(event: RunEvent): string {
  return event.agent_id ?? event.agent_type ?? "run";
}

const tokenButtonStyle = {
  minHeight: 0,
  padding: "2px 8px",
} satisfies CSSProperties;

function focusEvidence(detail: EvidenceFocusRequest): void {
  window.dispatchEvent(new CustomEvent<EvidenceFocusRequest>(EVIDENCE_FOCUS_EVENT, { detail }));
}

function isEvidenceIdKey(key: string): boolean {
  const normalizedKey = key.toLowerCase();
  return normalizedKey.includes("evidence") && normalizedKey.includes("id");
}

function ArtifactToken({ event, artifactId }: { event: RunEvent; artifactId: string }) {
  return (
    <button
      type="button"
      className="artifact-link"
      style={tokenButtonStyle}
      onClick={() => focusEvidence({ runId: event.run_id, artifactId, sourceEventId: event.id })}
      title="Locate evidence that references this artifact"
    >
      {artifactId}
    </button>
  );
}

function EvidenceToken({ event, evidenceId }: { event: RunEvent; evidenceId: string }) {
  return (
    <button
      type="button"
      className="artifact-link"
      style={tokenButtonStyle}
      onClick={() => focusEvidence({ runId: event.run_id, evidenceId, sourceEventId: event.id })}
      title="Locate this evidence item"
    >
      {evidenceId}
    </button>
  );
}

function renderPayloadValue(event: RunEvent, key: string, value: unknown): ReactNode {
  if (isEvidenceIdKey(key) && typeof value === "string") {
    return <EvidenceToken event={event} evidenceId={value} />;
  }

  if (isEvidenceIdKey(key) && Array.isArray(value)) {
    const evidenceIds = value.filter((item): item is string => typeof item === "string");

    if (evidenceIds.length) {
      return evidenceIds.map((evidenceId) => <EvidenceToken key={evidenceId} event={event} evidenceId={evidenceId} />);
    }
  }

  return String(value);
}

function PayloadSummary({ event }: { event: RunEvent }) {
  if (!event.payload) {
    return null;
  }

  const compactEntries = Object.entries(event.payload).slice(0, 3);

  if (compactEntries.length === 0) {
    return null;
  }

  return (
    <div className="event-foot">
      {compactEntries.map(([key, value]) => (
        <span key={key}>
          {key}: {renderPayloadValue(event, key, value)}
        </span>
      ))}
    </div>
  );
}

function getConnectionCopy(state: RunEventConnectionState | undefined, source: "api" | "mock" | undefined): string {
  if (source === "mock") {
    return "mock fallback";
  }

  switch (state) {
    case "connecting":
      return "SSE connecting";
    case "open":
      return "SSE open";
    case "error":
      return "SSE disconnected";
    case "closed":
      return "SSE closed";
    default:
      return "SSE idle";
  }
}

export function EventLog({
  events,
  activeRunId,
  connectionState = "idle",
  loading = false,
  error,
  source = "api",
}: EventLogProps) {
  const [level, setLevel] = useState<EventLevel | "all">("all");
  const [eventType, setEventType] = useState("all");
  const [agent, setAgent] = useState("all");
  const [status, setStatus] = useState("all");
  const [autoScroll, setAutoScroll] = useState(true);

  const eventTypes = useMemo(() => uniqueValues(events.map((event) => event.type)), [events]);
  const agents = useMemo(() => uniqueValues(events.map(getAgentFilterValue)), [events]);
  const statuses = useMemo(() => uniqueValues(events.map((event) => event.status)), [events]);

  const filteredEvents = useMemo(() => {
    return events
      .filter((event) => level === "all" || event.level === level)
      .filter((event) => eventType === "all" || event.type === eventType)
      .filter((event) => agent === "all" || getAgentFilterValue(event) === agent)
      .filter((event) => status === "all" || event.status === status);
  }, [agent, eventType, events, level, status]);

  return (
    <section className="panel event-panel" aria-labelledby="event-log-title">
      <div className="panel-header">
        <div>
          <h2 id="event-log-title">Live Event Log</h2>
          <p>
            {filteredEvents.length} of {events.length} events shown. {getConnectionCopy(connectionState, source)}.
          </p>
        </div>
        <div className="event-header-actions">
          <span className={`connection-pill connection-${connectionState}`}>{getConnectionCopy(connectionState, source)}</span>
          <button type="button" className={autoScroll ? "selected" : ""} onClick={() => setAutoScroll((value) => !value)}>
            Auto-scroll {autoScroll ? "on" : "off"}
          </button>
        </div>
      </div>

      {connectionState === "error" ? (
        <ErrorState
          title="Event stream disconnected"
          message="The console keeps the events it already received. Reconnect is handled by EventSource when the API becomes reachable."
          compact
        />
      ) : null}
      {error ? <ErrorState title="Events unavailable" message={error} compact /> : null}

      <div className="filter-row" aria-label="Event level filters">
        <label className="field">
          <span>Level</span>
          <select value={level} onChange={(event) => setLevel(event.target.value as EventLevel | "all")}>
            {levels.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Event type</span>
          <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
            <option value="all">all</option>
            {eventTypes.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Agent</span>
          <select value={agent} onChange={(event) => setAgent(event.target.value)}>
            <option value="all">all</option>
            {agents.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Status</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">all</option>
            {statuses.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="event-stream" role="log">
        {filteredEvents.length === 0 ? (
          loading ? (
            <EmptyState title="Loading events" message="Reading persisted events before opening the live stream." compact />
          ) : (
            <div className="active-summary">
              <div className="section-title">No events</div>
              <p className="empty-copy">
                {activeRunId ? "No event matches the current filters." : "Start or select a run to open its event stream."}
              </p>
            </div>
          )
        ) : (
          filteredEvents.map((event) => (
            <article key={event.id} className="event-row">
              <div className="event-meta">
                <span>#{event.seq}</span>
                <StatusBadge status={event.level} />
              </div>
              <div>
                <div className="event-title">
                  <strong>{event.type}</strong>
                  <time dateTime={event.ts}>{new Date(event.ts).toLocaleTimeString()}</time>
                </div>
                <p>{event.message}</p>
                <div className="event-foot">
                  <span>agent: {getAgentFilterValue(event)}</span>
                  <span>status: {event.status ?? "--"}</span>
                  <span>product: {event.product ?? "all"}</span>
                  <span>scenario: {event.scenario_id ?? "--"}</span>
                  <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
                    artifacts:{" "}
                    {event.artifact_ids?.length
                      ? event.artifact_ids.map((artifactId) => <ArtifactToken key={artifactId} event={event} artifactId={artifactId} />)
                      : "--"}
                  </span>
                </div>
                <PayloadSummary event={event} />
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
