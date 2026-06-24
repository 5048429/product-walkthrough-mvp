import { ArtifactLink } from "../common/ArtifactLink";
import { EmptyState } from "../common/EmptyState";
import { ScreenshotPreview } from "../evidence/ScreenshotPreview";
import type { Artifact, PageInsight, PageNode, ScreenshotEvidence, WalkthroughMapResponse } from "../../types/contracts";

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
      <TagList title="主要控件" items={node.key_controls} empty="暂无控件信息。" />

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
