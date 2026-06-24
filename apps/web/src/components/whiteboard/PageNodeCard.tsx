import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { PageNode } from "../../types/contracts";

export interface PageNodeCardData extends Record<string, unknown> {
  node: PageNode;
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

function compactPurpose(page: PageNode): string {
  if (page.purpose) {
    return page.purpose;
  }

  if (page.key_functions.length) {
    return page.key_functions[0];
  }

  return "页面结构已记录，等待更多 walkthrough 证据补全。";
}

export function PageNodeCard({ data, selected }: NodeProps<PageMapFlowNode>) {
  const page = data.node;
  const evidenceCount = page.evidence_ids.length;
  const issueCount = page.issues.length;
  const screenshotCount = page.screenshot_evidence.length;
  const pageEvidenceCount = page.page_evidence.length;
  const subtitle = page.route ?? page.metadata.normalized_route ?? shortUrl(page.url);
  const controls = Array.from(new Set([...page.key_controls, ...page.page_evidence.flatMap((item) => item.controls)])).slice(0, 2);
  const pageEvidenceScreenshotCount = page.page_evidence.reduce(
    (count, item) => count + item.screenshot_artifact_ids.length + item.screenshot_paths.length,
    0,
  );
  const hasVisualEvidence = screenshotCount > 0 || pageEvidenceScreenshotCount > 0 || Boolean(page.primary_screenshot_artifact_id);

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
      <div className="page-node-viewport">
        <div className="page-node-status-row">
          <span className={`page-status-dot page-status-dot-${page.status}`} aria-hidden="true" />
          <span>{statusLabels[page.status]}</span>
          <span>{typeLabels[page.page_type]}</span>
        </div>
        <strong title={page.name}>{page.name}</strong>
        <p title={compactPurpose(page)}>{compactPurpose(page)}</p>
        <div className="page-node-control-row" aria-label="关键控件">
          {controls.length ? controls.map((control) => <span key={control}>{control}</span>) : <span>{typeLabels[page.page_type]}</span>}
        </div>
      </div>
      <div className="page-node-meta">
        <span>{page.visit_count || 0} 次访问</span>
        <span>{evidenceCount} 条证据</span>
        {pageEvidenceCount ? <span className="page-node-page-evidence">{pageEvidenceCount} 组页面采集</span> : null}
        {hasVisualEvidence ? <span>{screenshotCount || 1} 张截图</span> : null}
        {issueCount ? <span className="page-node-issue">{issueCount} 个问题</span> : null}
      </div>
    </article>
  );
}
