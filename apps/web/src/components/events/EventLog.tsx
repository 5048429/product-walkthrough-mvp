import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { RunEventConnectionState } from "../../api/sse";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { StatusBadge } from "../StatusBadge";
import { EVIDENCE_FOCUS_EVENT, type EventLevel, type EvidenceFocusRequest, type RunEvent } from "../../types/contracts";
import { labelAgentType, labelEventType, labelStatus } from "../../i18n/zh";

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
      title="定位引用该产物的证据"
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
      title="定位这条证据"
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
    return "模拟数据";
  }

  switch (state) {
    case "connecting":
      return "事件流连接中";
    case "open":
      return "事件流已连接";
    case "error":
      return "事件流已断开";
    case "closed":
      return "事件流已关闭";
    default:
      return "事件流待连接";
  }
}

function labelAgentFilter(value: string): string {
  return labelAgentType(value) || value;
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
          <h2 id="event-log-title">实时事件日志</h2>
          <p>
            显示 {filteredEvents.length}/{events.length} 条事件，{getConnectionCopy(connectionState, source)}。
          </p>
        </div>
        <div className="event-header-actions">
          <span className={`connection-pill connection-${connectionState}`}>{getConnectionCopy(connectionState, source)}</span>
          <button type="button" className={autoScroll ? "selected" : ""} onClick={() => setAutoScroll((value) => !value)}>
            自动滚动{autoScroll ? "开" : "关"}
          </button>
        </div>
      </div>

      {connectionState === "error" ? (
        <ErrorState
          title="事件流已断开"
          message="控制台会保留已收到的事件；API 恢复后 EventSource 会自动重连。"
          compact
        />
      ) : null}
      {error ? <ErrorState title="事件不可用" message={error} compact /> : null}

      <div className="filter-row" aria-label="事件筛选">
        <label className="field">
          <span>级别</span>
          <select value={level} onChange={(event) => setLevel(event.target.value as EventLevel | "all")}>
            {levels.map((item) => (
              <option key={item} value={item}>
                {item === "all" ? "全部" : labelStatus(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>事件类型</span>
          <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
            <option value="all">全部</option>
            {eventTypes.map((item) => (
              <option key={item} value={item}>
                {labelEventType(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Agent</span>
          <select value={agent} onChange={(event) => setAgent(event.target.value)}>
            <option value="all">全部</option>
            {agents.map((item) => (
              <option key={item} value={item}>
                {labelAgentFilter(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>状态</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">全部</option>
            {statuses.map((item) => (
              <option key={item} value={item}>
                {labelStatus(item)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="event-stream" role="log">
        {filteredEvents.length === 0 ? (
          loading ? (
            <EmptyState title="正在读取事件" message="先读取已持久化事件，再打开实时事件流。" compact />
          ) : (
            <div className="active-summary">
              <div className="section-title">暂无事件</div>
              <p className="empty-copy">
                {activeRunId ? "当前筛选下没有匹配事件。" : "启动或选择一个任务后，这里会显示事件流。"}
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
                  <strong title={event.type}>{labelEventType(event.type)}</strong>
                  <time dateTime={event.ts}>{new Date(event.ts).toLocaleTimeString()}</time>
                </div>
                <p>{event.message}</p>
                <div className="event-foot">
                  <span>Agent：{event.agent_type ? labelAgentType(event.agent_type) : getAgentFilterValue(event)}</span>
                  <span>状态：{event.status ? labelStatus(event.status) : "--"}</span>
                  <span>产品：{event.product ?? "全部"}</span>
                  <span>场景：{event.scenario_id ?? "--"}</span>
                  <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
                    产物：{" "}
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
