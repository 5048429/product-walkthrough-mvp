import type { PageNode, WalkthroughMapResponse } from "../../types/contracts";
import {
  getPageEdgeRelation,
  pageEdgeRelationColors,
  pageEdgeRelationLabels,
  type PageEdgeRelation,
} from "./pageMapRelations";

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
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
  const nodesById = new Map(map.nodes.map((node) => [node.id, node]));
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
  const relationCounts = map.edges.reduce(
    (acc, edge) => {
      if (!visibleNodeIds.has(edge.source) || !visibleNodeIds.has(edge.target)) {
        return acc;
      }

      const relation = getPageEdgeRelation(edge, nodesById.get(edge.target));
      acc[relation] += 1;
      return acc;
    },
    {
      navigation: 0,
      detail: 0,
      external: 0,
      blocked: 0,
      inferred: 0,
    } satisfies Record<PageEdgeRelation, number>,
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
      <div className="page-map-relation-legend" aria-label="关系类型">
        {(Object.entries(relationCounts) as Array<[PageEdgeRelation, number]>).map(([relation, count]) => (
          <span key={relation}>
            <i style={{ borderTopColor: pageEdgeRelationColors[relation] }} aria-hidden="true" />
            {pageEdgeRelationLabels[relation]} {count}
          </span>
        ))}
      </div>
    </div>
  );
}
