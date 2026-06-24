import { useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { EmptyState } from "../common/EmptyState";
import type { PageEdge, PageNode, WalkthroughMapResponse } from "../../types/contracts";
import { PageNodeCard, type PageMapFlowNode } from "./PageNodeCard";
import { getPageMapLayout } from "./pageMapLayout";
import { getPageEdgeRelation, pageEdgeRelationColors, pageEdgeRelationLabels } from "./pageMapRelations";

interface WhiteboardCanvasProps {
  map: WalkthroughMapResponse;
  nodes: PageNode[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

const nodeTypes: NodeTypes = {
  pageNode: PageNodeCard,
};

function makeFlowEdges(edges: PageEdge[], visibleIds: Set<string>, nodesById: Map<string, PageNode>): Edge[] {
  return edges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge) => {
      const target = nodesById.get(edge.target);
      const relation = getPageEdgeRelation(edge, target);
      const color = pageEdgeRelationColors[relation];
      const lowConfidence = edge.kind === "inferred" || edge.confidence < 0.5;

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label || pageEdgeRelationLabels[relation],
        type: "smoothstep",
        className: `page-map-edge page-map-edge-${relation}`,
        interactionWidth: 18,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
        },
        style: {
          stroke: color,
          strokeWidth: relation === "blocked" ? 2.7 : 2.25,
          strokeDasharray: lowConfidence || relation === "external" ? "8 6" : undefined,
        },
        labelStyle: {
          fill: color,
          fontSize: 11,
          fontWeight: 760,
        },
        labelBgStyle: {
          fill: "#ffffff",
          fillOpacity: 0.92,
        },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 6,
      };
    });
}

export function WhiteboardCanvas({ map, nodes, selectedNodeId, onSelectNode }: WhiteboardCanvasProps) {
  const visibleIds = useMemo(() => new Set(nodes.map((node) => node.id)), [nodes]);
  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const positions = useMemo(() => getPageMapLayout(nodes, map.edges, map.layout), [map.edges, map.layout, nodes]);
  const flowNodes = useMemo<PageMapFlowNode[]>(
    () =>
      nodes.map((node) => ({
        id: node.id,
        type: "pageNode",
        position: positions[node.id] ?? { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: { node },
        selected: node.id === selectedNodeId,
        draggable: false,
      })),
    [nodes, positions, selectedNodeId],
  );
  const flowEdges = useMemo(() => makeFlowEdges(map.edges, visibleIds, nodesById), [map.edges, nodesById, visibleIds]);

  if (!nodes.length) {
    return (
      <div className="whiteboard-canvas-empty">
        <EmptyState title="没有匹配的页面" message="调整筛选条件后再查看页面关系。" compact />
      </div>
    );
  }

  return (
    <div className="whiteboard-canvas" aria-label="页面地图画布">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18, minZoom: 0.5, maxZoom: 1.2 }}
        minZoom={0.35}
        maxZoom={1.4}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) => onSelectNode(node.id)}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#d6dee9" gap={28} size={1} />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </div>
  );
}
