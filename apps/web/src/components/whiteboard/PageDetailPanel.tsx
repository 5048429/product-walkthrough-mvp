import { ArtifactLink } from "../common/ArtifactLink";
import { EmptyState } from "../common/EmptyState";
import { ScreenshotPreview } from "../evidence/ScreenshotPreview";
import type {
  Artifact,
  PageEvidence,
  PageEvidenceArtifactRef,
  PageInsight,
  PageNode,
  ScreenshotEvidence,
  WalkthroughMapResponse,
} from "../../types/contracts";

interface PageDetailPanelProps {
  map: WalkthroughMapResponse;
  node: PageNode | null;
  artifacts: Artifact[];
  onFocusEvidence: (evidenceId: string, artifactId?: string | null) => void;
}

const pageTypeLabels: Record<PageNode["page_type"], string> = {
  dashboard: "看板",
  list: "列表",
  detail: "详情",
  settings: "设置",
  form: "表单",
  auth: "登录/验证",
  error: "错误页",
  external: "外部页",
  unknown: "未知",
};

const insightLabels: Record<PageInsight["kind"], string> = {
  purpose: "用途",
  function: "功能",
  control: "控件",
  issue: "问题",
  observation: "观察",
};

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function screenshotToArtifact(runId: string, shot: ScreenshotEvidence, artifacts: Artifact[]): Artifact | null {
  if (shot.artifact_id) {
    const existing = artifacts.find((artifact) => artifact.id === shot.artifact_id);
    if (existing) {
      return existing;
    }
  }

  if (!shot.artifact_id && !shot.content_url && !shot.screenshot_url) {
    return null;
  }

  return {
    id: shot.artifact_id ?? shot.id,
    run_id: runId,
    type: "screenshot",
    title: shot.title || "Screenshot",
    path: shot.path ?? "",
    media_type: "image/png",
    size_bytes: 0,
    created_at: shot.captured_at ?? "",
    metadata: {
      content_url: shot.content_url ?? undefined,
      screenshot_url: shot.screenshot_url ?? undefined,
    },
  };
}

function normalizeArtifactPath(path: string | null): string | null {
  return path ? path.replace(/\\/g, "/") : null;
}

function artifactForRef(runId: string, ref: PageEvidenceArtifactRef, artifacts: Artifact[]): Artifact | null {
  if (ref.artifact_id) {
    const existing = artifacts.find((artifact) => artifact.id === ref.artifact_id);
    if (existing) {
      return existing;
    }
  }

  const refPath = normalizeArtifactPath(ref.path);
  const existingByPath = refPath
    ? artifacts.find((artifact) => normalizeArtifactPath(artifact.path) === refPath || normalizeArtifactPath(artifact.path)?.endsWith(`/${refPath}`))
    : null;
  if (existingByPath) {
    return existingByPath;
  }

  if (!ref.content_url && !ref.path) {
    return null;
  }

  return {
    id: ref.artifact_id ?? `${ref.kind}-${ref.path ?? ref.label}`,
    run_id: runId,
    type: "log_text",
    title: ref.label,
    path: ref.path ?? "",
    media_type: "application/octet-stream",
    size_bytes: 0,
    created_at: "",
    metadata: {
      content_url: ref.content_url ?? undefined,
      path_url: ref.content_url ?? undefined,
    },
  };
}

function artifactIdForPath(path: string | null, artifacts: Artifact[]): string | null {
  const normalized = normalizeArtifactPath(path);
  if (!normalized) {
    return null;
  }

  return (
    artifacts.find((artifact) => {
      const artifactPath = normalizeArtifactPath(artifact.path);
      return artifactPath === normalized || artifactPath?.endsWith(`/${normalized}`);
    })?.id ?? null
  );
}

function artifactIdsForPaths(paths: string[], artifacts: Artifact[]): string[] {
  return unique(paths.map((path) => artifactIdForPath(path, artifacts)).filter((artifactId): artifactId is string => Boolean(artifactId)));
}

function InsightList({ title, insights, onFocusEvidence }: {
  title: string;
  insights: PageInsight[];
  onFocusEvidence: (evidenceId: string) => void;
}) {
  if (!insights.length) {
    return null;
  }

  return (
    <section className="page-detail-section">
      <div className="section-title">{title}</div>
      <div className="page-insight-list">
        {insights.map((insight) => (
          <article key={insight.id} className={`page-insight-card page-insight-${insight.severity ?? insight.kind}`}>
            <div>
              <strong>{insight.title || insightLabels[insight.kind]}</strong>
              <span>{Math.round(insight.confidence * 100)}% confidence</span>
            </div>
            <p>{insight.summary || "暂无摘要。"}</p>
            {insight.evidence_ids.length ? (
              <div className="page-evidence-links">
                {insight.evidence_ids.map((evidenceId) => (
                  <button key={evidenceId} type="button" onClick={() => onFocusEvidence(evidenceId)}>
                    {evidenceId}
                  </button>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function TagList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <section className="page-detail-section">
      <div className="section-title">{title}</div>
      {items.length ? (
        <div className="page-tag-list">
          {items.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : (
        <p className="empty-copy">{empty}</p>
      )}
    </section>
  );
}

function ObservationList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return null;
  }

  return (
    <div className="page-evidence-observation">
      <strong>{title}</strong>
      <ul>
        {items.slice(0, 3).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function PageEvidenceCard({
  runId,
  evidence,
  artifacts,
}: {
  runId: string;
  evidence: PageEvidence;
  artifacts: Artifact[];
}) {
  const screenshotArtifactIds = unique([
    ...evidence.screenshot_artifact_ids,
    ...artifactIdsForPaths(evidence.screenshot_paths, artifacts),
  ]);
  const sourceArtifacts = [
    ...evidence.artifacts,
    ...evidence.artifact_ids.map((artifactId) => ({
      kind: "artifact",
      label: artifacts.find((artifact) => artifact.id === artifactId)?.title ?? "采集文件",
      artifact_id: artifactId,
      path: null,
      content_url: null,
    })),
  ];
  const metrics = [
    evidence.controls.length ? `${evidence.controls.length} 个控件` : null,
    evidence.text_observations.length ? `${evidence.text_observations.length} 条文本观察` : null,
    evidence.dom_observations.length ? `${evidence.dom_observations.length} 条 DOM 观察` : null,
    screenshotArtifactIds.length || evidence.screenshot_paths.length ? `${screenshotArtifactIds.length || evidence.screenshot_paths.length} 张采集截图` : null,
    evidence.network_event_count ? `${evidence.network_event_count} 个网络事件` : null,
    evidence.console_message_count ? `${evidence.console_message_count} 条 console` : null,
    evidence.page_error_count ? `${evidence.page_error_count} 个页面错误` : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <article className={`page-evidence-card page-evidence-card-${evidence.status}`}>
      <div className="page-evidence-card-heading">
        <div>
          <strong>{evidence.title ?? "页面采集证据"}</strong>
          <span>{evidence.captured_at ? `采集于 ${evidence.captured_at}` : "Playwright 页面采集"}</span>
        </div>
        <span className={`page-detail-status page-evidence-status-${evidence.status}`}>{evidence.status}</span>
      </div>
      <p>
        {evidence.summary ??
          (evidence.url ? `采集器重新打开页面并记录了可见内容、控件、DOM 线索和截图来源：${evidence.url}` : "采集器记录了页面内容、控件、DOM 线索和截图来源。")}
      </p>
      {metrics.length ? (
        <div className="page-evidence-metric-row">
          {metrics.map((metric) => (
            <span key={metric}>{metric}</span>
          ))}
        </div>
      ) : null}
      {evidence.controls.length ? (
        <div className="page-tag-list page-evidence-controls">
          {evidence.controls.slice(0, 8).map((control) => (
            <span key={control}>{control}</span>
          ))}
        </div>
      ) : null}
      <ObservationList title="可见文本观察" items={evidence.text_observations} />
      <ObservationList title="DOM / 可访问性观察" items={evidence.dom_observations} />
      {screenshotArtifactIds.length ? (
        <div className="page-evidence-source-row">
          <strong>截图来源</strong>
          <div className="page-evidence-links">
            {screenshotArtifactIds.slice(0, 4).map((artifactId) => (
              <ArtifactLink key={artifactId} artifactId={artifactId} artifacts={artifacts} runId={runId} label="打开截图" />
            ))}
          </div>
        </div>
      ) : null}
      {sourceArtifacts.length ? (
        <div className="page-evidence-source-row">
          <strong>采集文件</strong>
          <div className="page-evidence-artifact-list">
            {sourceArtifacts.slice(0, 6).map((ref, index) => (
              <ArtifactLink
                key={`${ref.artifact_id ?? ref.path ?? ref.label}-${index}`}
                artifact={artifactForRef(runId, ref, artifacts)}
                artifactId={ref.artifact_id ?? artifactIdForPath(ref.path, artifacts)}
                artifacts={artifacts}
                runId={runId}
                label={ref.label}
              />
            ))}
          </div>
        </div>
      ) : null}
      {evidence.errors.length ? (
        <div className="page-evidence-error-list">
          {evidence.errors.slice(0, 2).map((error) => (
            <span key={error}>{error}</span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function PageDetailPanel({ map, node, artifacts, onFocusEvidence }: PageDetailPanelProps) {
  if (!node) {
    return (
      <aside className="page-detail-panel">
        <EmptyState title="选择一个页面" message="点击地图中的页面节点后，这里会显示用途、功能、控件、问题和证据。" compact />
      </aside>
    );
  }

  const evidenceIds = unique([
    ...node.evidence_ids,
    ...node.issues.flatMap((insight) => insight.evidence_ids),
    ...node.observations.flatMap((insight) => insight.evidence_ids),
    ...node.screenshot_evidence.map((shot) => shot.evidence_id ?? ""),
  ]);
  const screenshots = node.screenshot_evidence;
  const pageEvidenceScreenshotIds = unique(
    node.page_evidence.flatMap((evidence) => [
      ...evidence.screenshot_artifact_ids,
      ...artifactIdsForPaths(evidence.screenshot_paths, artifacts),
    ]),
  );
  const primaryShot = screenshots.find((shot) => shot.is_primary) ?? screenshots[0] ?? null;
  const otherShots = screenshots.filter((shot) => shot.id !== primaryShot?.id);

  return (
    <aside className="page-detail-panel" aria-label="页面详情">
      <div className="page-detail-heading">
        <div>
          <span className={`page-detail-status page-detail-status-${node.status}`}>{node.status}</span>
          <h2>{node.name}</h2>
          <p>{node.purpose || "这个页面还没有足够的用途摘要。"}</p>
        </div>
        <ArtifactLink artifactId={map.artifact_id} artifacts={artifacts} runId={map.run_id} label="打开地图源文件" />
      </div>

      <dl className="detail-list page-detail-meta">
        <div>
          <dt>页面标题</dt>
          <dd>{node.title ?? "--"}</dd>
        </div>
        <div>
          <dt>页面类型</dt>
          <dd>{pageTypeLabels[node.page_type]}</dd>
        </div>
        <div>
          <dt>Route</dt>
          <dd>{node.route ?? node.metadata.normalized_route ?? "--"}</dd>
        </div>
        <div>
          <dt>访问次数</dt>
          <dd>{node.visit_count}</dd>
        </div>
        <div>
          <dt>URL</dt>
          <dd>
            {node.url ? (
              <a href={node.url} target="_blank" rel="noreferrer">
                {node.url}
              </a>
            ) : (
              "--"
            )}
          </dd>
        </div>
      </dl>

      <TagList title="关键功能" items={node.key_functions} empty="暂无关键功能摘要。" />
      <TagList
        title="主要控件"
        items={unique([...node.key_controls, ...node.page_evidence.flatMap((evidence) => evidence.controls)]).slice(0, 12)}
        empty="暂无控件信息。"
      />

      {node.page_evidence.length ? (
        <section className="page-detail-section">
          <div className="section-title">页面采集证据</div>
          <div className="page-evidence-card-list">
            {node.page_evidence.map((evidence) => (
              <PageEvidenceCard key={evidence.id} runId={map.run_id} evidence={evidence} artifacts={artifacts} />
            ))}
          </div>
        </section>
      ) : null}

      <InsightList title="问题" insights={node.issues} onFocusEvidence={(evidenceId) => onFocusEvidence(evidenceId)} />
      <InsightList title="观察" insights={node.observations} onFocusEvidence={(evidenceId) => onFocusEvidence(evidenceId)} />

      <section className="page-detail-section">
        <div className="section-title">截图</div>
        {primaryShot ? (
          <div className="page-screenshot-stack">
            <ScreenshotPreview
              artifact={screenshotToArtifact(map.run_id, primaryShot, artifacts)}
              artifactId={primaryShot.artifact_id}
              artifacts={artifacts}
              runId={map.run_id}
              alt={`${node.name} screenshot`}
              variant="detail"
            />
            {otherShots.map((shot) => (
              <ScreenshotPreview
                key={shot.id}
                artifact={screenshotToArtifact(map.run_id, shot, artifacts)}
                artifactId={shot.artifact_id}
                artifacts={artifacts}
                runId={map.run_id}
                alt={`${node.name} screenshot ${shot.step_index ?? ""}`}
                variant="card"
              />
            ))}
            {pageEvidenceScreenshotIds
              .filter((artifactId) => artifactId !== primaryShot?.artifact_id && !otherShots.some((shot) => shot.artifact_id === artifactId))
              .slice(0, 3)
              .map((artifactId) => (
                <ScreenshotPreview
                  key={artifactId}
                  artifactId={artifactId}
                  artifacts={artifacts}
                  runId={map.run_id}
                  alt={`${node.name} page evidence screenshot`}
                  variant="card"
                />
              ))}
          </div>
        ) : pageEvidenceScreenshotIds.length ? (
          <div className="page-screenshot-stack">
            {pageEvidenceScreenshotIds.slice(0, 4).map((artifactId, index) => (
              <ScreenshotPreview
                key={artifactId}
                artifactId={artifactId}
                artifacts={artifacts}
                runId={map.run_id}
                alt={`${node.name} page evidence screenshot ${index + 1}`}
                variant={index === 0 ? "detail" : "card"}
              />
            ))}
          </div>
        ) : (
          <ScreenshotPreview variant="detail" />
        )}
      </section>

      <section className="page-detail-section">
        <div className="section-title">Evidence links</div>
        {evidenceIds.length ? (
          <div className="page-evidence-links">
            {evidenceIds.map((evidenceId) => (
              <button
                key={evidenceId}
                type="button"
                onClick={() => onFocusEvidence(evidenceId, node.primary_screenshot_artifact_id)}
              >
                {evidenceId}
              </button>
            ))}
          </div>
        ) : (
          <p className="empty-copy">这个页面暂时没有关联 evidence。</p>
        )}
      </section>
    </aside>
  );
}
