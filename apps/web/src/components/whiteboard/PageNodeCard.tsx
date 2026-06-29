import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { useEffect, useState } from "react";
import { backendUrl, runApiPath } from "../../api/paths";
import type { PageNode, ScreenshotEvidence } from "../../types/contracts";

export interface PageNodeCardData extends Record<string, unknown> {
  node: PageNode;
  runId: string;
}

export type PageMapFlowNode = Node<PageNodeCardData, "pageNode">;

const statusLabels: Record<PageNode["status"], string> = {
  visited: "已访问",
  blocked: "受阻",
  discovered: "已发现",
  external: "外部",
  error: "异常",
};

const typeLabels: Record<PageNode["page_type"], string> = {
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

function shortUrl(url: string | null): string {
  if (!url) {
    return "--";
  }

  try {
    const parsed = new URL(url);
    return parsed.hostname;
  } catch {
    return url;
  }
}

function routeLabel(page: PageNode): string {
  return page.route ?? page.metadata.normalized_route ?? shortUrl(page.url);
}

function primaryScreenshot(page: PageNode): ScreenshotEvidence | null {
  return page.screenshot_evidence.find((shot) => shot.is_primary) ?? page.screenshot_evidence[0] ?? null;
}

function screenshotUrl(shot: ScreenshotEvidence | null, runId: string): string | null {
  if (!shot) {
    return null;
  }

  const directUrl = shot.screenshot_url ?? shot.content_url;
  if (directUrl) {
    return backendUrl(directUrl);
  }

  if (shot.artifact_id) {
    return runApiPath(runId, `/artifacts/${encodeURIComponent(shot.artifact_id)}/content`);
  }

  if (shot.path) {
    const filename = shot.path.split(/[\\/]/).filter(Boolean).pop();
    return filename ? runApiPath(runId, `/screenshots/${encodeURIComponent(filename)}`) : null;
  }

  return null;
}

export function PageNodeCard({ data, selected }: NodeProps<PageMapFlowNode>) {
  const page = data.node;
  const shot = primaryScreenshot(page);
  const imageSrc = screenshotUrl(shot, data.runId);
  const [imageFailed, setImageFailed] = useState(false);
  const subtitle = routeLabel(page);
  const statusText = statusLabels[page.status] ?? page.status;
  const typeText = typeLabels[page.page_type] ?? page.page_type;
  const issueCount = page.issues.length;

  useEffect(() => {
    setImageFailed(false);
  }, [imageSrc]);

  return (
    <article className={`page-node-card page-node-card-${page.status} ${selected ? "page-node-card-selected" : ""}`.trim()}>
      <Handle id="target-left" type="target" position={Position.Left} className="page-node-handle page-node-handle-left" />
      <Handle id="source-left" type="source" position={Position.Left} className="page-node-handle page-node-handle-left" />
      <Handle id="target-right" type="target" position={Position.Right} className="page-node-handle page-node-handle-right" />
      <Handle id="source-right" type="source" position={Position.Right} className="page-node-handle page-node-handle-right" />
      <Handle id="target-top" type="target" position={Position.Top} className="page-node-handle page-node-handle-top" />
      <Handle id="source-top" type="source" position={Position.Top} className="page-node-handle page-node-handle-top" />
      <Handle id="target-bottom" type="target" position={Position.Bottom} className="page-node-handle page-node-handle-bottom" />
      <Handle id="source-bottom" type="source" position={Position.Bottom} className="page-node-handle page-node-handle-bottom" />

      <div className="page-node-browser-bar">
        <span className="page-node-window-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="page-node-url" title={subtitle}>
          {subtitle}
        </span>
      </div>

      <div className="page-node-screenshot-viewport">
        {imageSrc && !imageFailed ? (
          <img
            src={imageSrc}
            alt={`${page.name} screenshot`}
            loading="lazy"
            draggable={false}
            onError={() => setImageFailed(true)}
          />
        ) : (
          <div className="page-node-screenshot-empty">
            <span className={`page-status-dot page-status-dot-${page.status}`} aria-hidden="true" />
            <strong>{page.name}</strong>
            <span>{imageSrc ? "截图加载失败" : typeText}</span>
          </div>
        )}

        <div className="page-node-shot-overlay">
          <strong title={page.name}>{page.name}</strong>
          <span>
            {statusText} / {typeText}
          </span>
        </div>

        {issueCount ? <span className="page-node-shot-issue">{issueCount}</span> : null}
      </div>
    </article>
  );
}
