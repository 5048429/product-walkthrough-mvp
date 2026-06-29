import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { EmptyState } from "../common/EmptyState";
import type { PageEdge, PageEntry, PageNode, WalkthroughMapResponse } from "../../types/contracts";
import { PageNodeCard, type PageMapFlowNode } from "./PageNodeCard";
import { getPageMapLayout, type PageMapPosition } from "./pageMapLayout";
import { getPageEdgeRelation, pageEdgeRelationColors, pageEdgeRelationLabels } from "./pageMapRelations";

interface WhiteboardCanvasProps {
  map: WalkthroughMapResponse;
  nodes: PageNode[];
  selectedNodeId: string | null;
  showUncoveredEntries: boolean;
  onSelectNode: (nodeId: string) => void;
}

const nodeTypes: NodeTypes = {
  pageNode: PageNodeCard,
  pageEntry: PageEntryNodeCard,
};

interface PageEntryNodeData extends Record<string, unknown> {
  entry: PageEntry;
}

type PageEntryFlowNode = Node<PageEntryNodeData, "pageEntry">;

interface LayoutBox {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

const pageNodeWidth = 344;
const pageNodeHeight = 226;
const entryNodeWidth = 210;
const entryNodeHeight = 56;
const entryNodeGap = 64;
const collisionPadding = 18;

const entryStatusLabels: Record<string, string> = {
  unvisited: "未访问入口",
  unsafe: "高风险入口",
  blocked: "受阻入口",
};

function PageEntryNodeCard({ data }: NodeProps<PageEntryFlowNode>) {
  const entry = data.entry;

  return (
    <article className={`page-entry-node page-entry-node-${entry.status}`}>
      <Handle id="target-left" type="target" position={Position.Left} className="page-node-handle page-node-handle-left" />
      <strong title={entry.label}>{entry.label}</strong>
      <span>{entryStatusLabels[entry.status] ?? entry.kind}</span>
    </article>
  );
}

function edgeHandles(edge: PageEdge, positions: Record<string, PageMapPosition>) {
  const source = positions[edge.source];
  const target = positions[edge.target];

  if (!source || !target) {
    return { sourceHandle: "source-right", targetHandle: "target-left" };
  }

  const dx = target.x - source.x;
  const dy = target.y - source.y;
  if (Math.abs(dy) > Math.abs(dx) * 0.72) {
    return dy >= 0
      ? { sourceHandle: "source-bottom", targetHandle: "target-top" }
      : { sourceHandle: "source-top", targetHandle: "target-bottom" };
  }

  return dx >= 0
    ? { sourceHandle: "source-right", targetHandle: "target-left" }
    : { sourceHandle: "source-left", targetHandle: "target-right" };
}

function makeFlowEdges(
  edges: PageEdge[],
  visibleIds: Set<string>,
  nodesById: Map<string, PageNode>,
  positions: Record<string, PageMapPosition>,
): Edge[] {
  return edges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge) => {
      const target = nodesById.get(edge.target);
      const relation = getPageEdgeRelation(edge, target);
      const color = pageEdgeRelationColors[relation];
      const lowConfidence = edge.kind === "inferred" || edge.confidence < 0.5;
      const handles = edgeHandles(edge, positions);

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        ...handles,
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

function entryNodeId(sourceNodeId: string, entry: PageEntry): string {
  return `entry-${sourceNodeId}-${entry.id}`;
}

function isGhostEntry(entry: PageEntry): boolean {
  return !entry.target_node_id && ["unvisited", "unsafe", "blocked"].includes(entry.status);
}

function visibleGhostEntries(node: PageNode, selectedNodeId: string | null, showUncoveredEntries: boolean): PageEntry[] {
  if (!showUncoveredEntries || node.id !== selectedNodeId) {
    return [];
  }

  return node.entries.filter(isGhostEntry).slice(0, 5);
}

function boxesOverlap(a: LayoutBox, b: LayoutBox, padding = 0): boolean {
  return !(
    a.x + a.width + padding <= b.x ||
    b.x + b.width + padding <= a.x ||
    a.y + a.height + padding <= b.y ||
    b.y + b.height + padding <= a.y
  );
}

function boxesOverlapHorizontally(a: LayoutBox, b: LayoutBox, padding = 0): boolean {
  return !(a.x + a.width + padding <= b.x || b.x + b.width + padding <= a.x);
}

function candidateEntryY(sourcePosition: PageMapPosition, entryIndex: number, entryCount: number): number {
  const groupHeight = entryCount * entryNodeHeight + Math.max(0, entryCount - 1) * (entryNodeGap - entryNodeHeight);
  return sourcePosition.y + pageNodeHeight / 2 - groupHeight / 2 + entryIndex * entryNodeGap;
}

function firstEntryLaneX(sourcePosition: PageMapPosition, pageBoxes: LayoutBox[]): number {
  const laneStep = entryNodeWidth + 56;
  let x = sourcePosition.x + pageNodeWidth + 72;

  while (
    pageBoxes.some((box) =>
      boxesOverlapHorizontally({ id: "entry-lane", x, y: 0, width: entryNodeWidth, height: entryNodeHeight }, box, collisionPadding),
    )
  ) {
    x += laneStep;
  }

  return x;
}

function resolveEntryPosition(
  id: string,
  baseX: number,
  baseY: number,
  occupiedBoxes: LayoutBox[],
): { x: number; y: number } {
  const laneStep = entryNodeWidth + 56;

  for (let laneIndex = 0; laneIndex < 10; laneIndex += 1) {
    const x = baseX + laneIndex * laneStep;

    for (let verticalStep = 0; verticalStep < 18; verticalStep += 1) {
      const direction = verticalStep % 2 === 0 ? 1 : -1;
      const distance = Math.ceil(verticalStep / 2) * entryNodeGap;
      const y = baseY + direction * distance;
      const candidate = { id, x, y, width: entryNodeWidth, height: entryNodeHeight };

      if (!occupiedBoxes.some((box) => boxesOverlap(candidate, box, collisionPadding))) {
        occupiedBoxes.push(candidate);
        return { x, y };
      }
    }
  }

  const fallbackY = occupiedBoxes.reduce((bottom, box) => Math.max(bottom, box.y + box.height), baseY);
  const fallback = {
    id,
    x: baseX + 10 * laneStep,
    y: fallbackY + entryNodeGap,
    width: entryNodeWidth,
    height: entryNodeHeight,
  };
  occupiedBoxes.push(fallback);
  return { x: fallback.x, y: fallback.y };
}

function makeEntryFlowNodes(
  nodes: PageNode[],
  positions: Record<string, PageMapPosition>,
  selectedNodeId: string | null,
  showUncoveredEntries: boolean,
): PageEntryFlowNode[] {
  const result: PageEntryFlowNode[] = [];
  const pageBoxes: LayoutBox[] = nodes
    .map((node) => {
      const position = positions[node.id];
      return position
        ? { id: node.id, x: position.x, y: position.y, width: pageNodeWidth, height: pageNodeHeight }
        : null;
    })
    .filter((box): box is LayoutBox => Boolean(box));
  const occupiedBoxes: LayoutBox[] = [...pageBoxes];

  for (const node of nodes) {
    const sourcePosition = positions[node.id];
    if (!sourcePosition) {
      continue;
    }

    const entries = visibleGhostEntries(node, selectedNodeId, showUncoveredEntries);
    if (!entries.length) {
      continue;
    }

    const baseX = firstEntryLaneX(sourcePosition, pageBoxes);
    entries.forEach((entry, index) => {
      const id = entryNodeId(node.id, entry);
      const baseY = candidateEntryY(sourcePosition, index, entries.length);
      const position = resolveEntryPosition(id, baseX, baseY, occupiedBoxes);

      result.push({
        id,
        type: "pageEntry",
        position,
        className: "page-entry-flow-node",
        data: { entry },
        draggable: false,
        selectable: false,
      });
    });
  }

  return result;
}

function makeEntryFlowEdges(nodes: PageNode[], selectedNodeId: string | null, showUncoveredEntries: boolean): Edge[] {
  return nodes.flatMap((node) =>
    visibleGhostEntries(node, selectedNodeId, showUncoveredEntries)
      .map((entry) => {
        const color = entry.status === "unsafe" ? "#b86b00" : "#7b8798";

        return {
          id: `edge-${entryNodeId(node.id, entry)}`,
          source: node.id,
          target: entryNodeId(node.id, entry),
          sourceHandle: "source-right",
          targetHandle: "target-left",
          label: entry.kind === "destructive" ? "unsafe action" : "available entry",
          type: "smoothstep",
          className: `page-map-edge page-map-edge-entry page-map-edge-entry-${entry.status}`,
          interactionWidth: 14,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color,
          },
          style: {
            stroke: color,
            strokeWidth: 1.8,
            strokeDasharray: "6 6",
          },
          labelStyle: {
            fill: color,
            fontSize: 10,
            fontWeight: 740,
          },
          labelBgStyle: {
            fill: "#ffffff",
            fillOpacity: 0.92,
          },
          labelBgPadding: [5, 2] as [number, number],
          labelBgBorderRadius: 5,
        };
      }),
  );
}

export function WhiteboardCanvas({ map, nodes, selectedNodeId, showUncoveredEntries, onSelectNode }: WhiteboardCanvasProps) {
  const visibleIds = useMemo(() => new Set(nodes.map((node) => node.id)), [nodes]);
  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const positions = useMemo(() => getPageMapLayout(nodes, map.edges, map.layout), [map.edges, map.layout, nodes]);
  const flowNodes = useMemo(
    () => {
      const pageNodes: PageMapFlowNode[] = nodes.map((node) => ({
        id: node.id,
        type: "pageNode",
        position: positions[node.id] ?? { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: { node, runId: map.run_id },
        selected: node.id === selectedNodeId,
        draggable: false,
      }));

      return [...pageNodes, ...makeEntryFlowNodes(nodes, positions, selectedNodeId, showUncoveredEntries)];
    },
    [map.run_id, nodes, positions, selectedNodeId, showUncoveredEntries],
  );
  const flowEdges = useMemo(
    () => [
      ...makeFlowEdges(map.edges, visibleIds, nodesById, positions),
      ...makeEntryFlowEdges(nodes, selectedNodeId, showUncoveredEntries),
    ],
    [map.edges, nodes, nodesById, positions, selectedNodeId, showUncoveredEntries, visibleIds],
  );

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
        onNodeClick={(_, node) => {
          if (node.type === "pageNode") {
            onSelectNode(node.id);
          }
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#d6dee9" gap={28} size={1} />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </div>
  );
}
