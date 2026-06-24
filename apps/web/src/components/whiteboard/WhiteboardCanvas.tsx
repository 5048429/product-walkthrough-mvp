import { useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { EmptyState } from "../common/EmptyState";
import type { PageEdge, PageNode, WalkthroughMapResponse } from "../../types/contracts";
import { PageNodeCard, type PageMapFlowNode } from "./PageNodeCard";
import { getPageMapLayout } from "./pageMapLayout";

interface WhiteboardCanvasProps {
  map: WalkthroughMapResponse;
  nodes: PageNode[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

const nodeTypes: NodeTypes = {
  pageNode: PageNodeCard,
};

const edgeColorByKind: Record<PageEdge["kind"], string> = {
  navigation: "#56708d",
  menu: "#1f5ed2",
  button: "#087657",
  link: "#6b7280",
  redirect: "#946100",
  form_submit: "#8b5cf6",
  inferred: "#9aa8ba",
};

function makeFlowEdges(edges: PageEdge[], visibleIds: Set<string>): Edge[] {
  return edges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge) => {
      const color = edge.confidence < 0.5 ? "#9aa8ba" : edgeColorByKind[edge.kind];

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label || edge.kind.replaceAll("_", " "),
        type: "smoothstep",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
        },
        style: {
          stroke: color,
          strokeWidth: edge.confidence < 0.5 ? 1.4 : 1.8,
          strokeDasharray: edge.kind === "inferred" || edge.confidence < 0.5 ? "6 5" : undefined,
        },
        labelStyle: {
          fill: "#344256",
          fontSize: 11,
          fontWeight: 650,
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
  const positions = useMemo(() => getPageMapLayout(nodes, map.edges, map.layout), [map.edges, map.layout, nodes]);
  const flowNodes = useMemo<PageMapFlowNode[]>(
    () =>
      nodes.map((node) => ({
        id: node.id,
        type: "pageNode",
        position: positions[node.id] ?? { x: 0, y: 0 },
        data: { node },
        selected: node.id === selectedNodeId,
        draggable: false,
      })),
    [nodes, positions, selectedNodeId],
  );
  const flowEdges = useMemo(() => makeFlowEdges(map.edges, visibleIds), [map.edges, visibleIds]);

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
        <Background color="#d6dee9" gap={24} size={1} />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </div>
  );
}
