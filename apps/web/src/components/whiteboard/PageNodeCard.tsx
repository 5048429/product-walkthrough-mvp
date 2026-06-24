import type { Node, NodeProps } from "@xyflow/react";
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

export function PageNodeCard({ data, selected }: NodeProps<PageMapFlowNode>) {
  const page = data.node;
  const evidenceCount = page.evidence_ids.length;
  const issueCount = page.issues.length;
  const screenshotCount = page.screenshot_evidence.length;
  const subtitle = page.route ?? page.metadata.normalized_route ?? shortUrl(page.url);

  return (
    <article className={`page-node-card page-node-card-${page.status} ${selected ? "page-node-card-selected" : ""}`.trim()}>
      <div className="page-node-status-row">
        <span className={`page-status-dot page-status-dot-${page.status}`} aria-hidden="true" />
        <span>{statusLabels[page.status]}</span>
        <span>{typeLabels[page.page_type]}</span>
      </div>
      <strong title={page.name}>{page.name}</strong>
      <span className="page-node-route" title={subtitle}>
        {subtitle}
      </span>
      <div className="page-node-meta">
        <span>{page.visit_count || 0} 次访问</span>
        <span>{evidenceCount} 条证据</span>
        {screenshotCount ? <span>{screenshotCount} 张截图</span> : null}
      </div>
      {issueCount ? <span className="page-node-issue">{issueCount} 个问题</span> : null}
    </article>
  );
}
