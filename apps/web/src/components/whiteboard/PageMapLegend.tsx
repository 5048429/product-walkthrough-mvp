import type { PageNode, WalkthroughMapResponse } from "../../types/contracts";

interface PageMapLegendProps {
  map: WalkthroughMapResponse;
  visibleNodes: PageNode[];
}

const statusLabels: Record<PageNode["status"], string> = {
  visited: "已访问",
  blocked: "受阻",
  discovered: "已发现",
  external: "外部",
  error: "异常",
};

export function PageMapLegend({ map, visibleNodes }: PageMapLegendProps) {
  const counts = visibleNodes.reduce(
    (acc, node) => {
      acc[node.status] += 1;
      return acc;
    },
    {
      visited: 0,
      blocked: 0,
      discovered: 0,
      external: 0,
      error: 0,
    } satisfies Record<PageNode["status"], number>,
  );

  return (
    <div className="page-map-legend" aria-label="页面地图图例">
      <div>
        <span className="section-title">地图概览</span>
        <strong>
          {visibleNodes.length}/{map.summary.node_count || map.nodes.length} 页面
        </strong>
        <span>{map.summary.edge_count || map.edges.length} 条关系</span>
      </div>
      <div className="page-map-legend-statuses">
        {Object.entries(counts).map(([status, count]) => (
          <span key={status} className={`page-map-legend-pill page-map-legend-${status}`}>
            <i aria-hidden="true" />
            {statusLabels[status as PageNode["status"]]} {count}
          </span>
        ))}
      </div>
    </div>
  );
}
