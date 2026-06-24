import type { PageEdge, PageNode, WalkthroughMapResponse } from "../../types/contracts";

export interface PageMapPosition {
  x: number;
  y: number;
  depth: number;
}

const nodeWidth = 230;
const nodeHeight = 132;
const columnGap = 110;
const rowGap = 44;

function hasPresetLayout(layout: WalkthroughMapResponse["layout"] | undefined, nodes: PageNode[]): boolean {
  if (!layout?.nodes) {
    return false;
  }

  return nodes.every((node) => {
    const position = layout.nodes[node.id];
    return (
      position &&
      Number.isFinite(position.x) &&
      Number.isFinite(position.y) &&
      Number.isFinite(position.depth)
    );
  });
}

function getLayeredDepths(nodes: PageNode[], edges: PageEdge[]): Map<string, number> {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const incomingCount = new Map<string, number>();
  const outgoing = new Map<string, string[]>();

  for (const node of nodes) {
    incomingCount.set(node.id, 0);
    outgoing.set(node.id, []);
  }

  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      continue;
    }

    incomingCount.set(edge.target, (incomingCount.get(edge.target) ?? 0) + 1);
    outgoing.get(edge.source)?.push(edge.target);
  }

  const roots = nodes
    .filter((node) => (incomingCount.get(node.id) ?? 0) === 0)
    .sort((a, b) => (a.first_seen_step ?? Number.MAX_SAFE_INTEGER) - (b.first_seen_step ?? Number.MAX_SAFE_INTEGER));
  const queue = roots.length ? roots.map((node) => node.id) : nodes[0] ? [nodes[0].id] : [];
  const depths = new Map<string, number>();

  for (const rootId of queue) {
    depths.set(rootId, 0);
  }

  while (queue.length) {
    const currentId = queue.shift()!;
    const currentDepth = depths.get(currentId) ?? 0;

    for (const targetId of outgoing.get(currentId) ?? []) {
      const nextDepth = currentDepth + 1;

      if (!depths.has(targetId) || nextDepth < (depths.get(targetId) ?? nextDepth)) {
        depths.set(targetId, nextDepth);
        queue.push(targetId);
      }
    }
  }

  for (const node of nodes) {
    if (!depths.has(node.id)) {
      const fallbackDepth = node.status === "external" || node.status === "discovered" ? 2 : 0;
      depths.set(node.id, fallbackDepth);
    }
  }

  return depths;
}

export function getPageMapLayout(
  nodes: PageNode[],
  edges: PageEdge[],
  layout?: WalkthroughMapResponse["layout"],
): Record<string, PageMapPosition> {
  if (hasPresetLayout(layout, nodes)) {
    return Object.fromEntries(
      nodes.map((node) => {
        const position = layout!.nodes[node.id];
        return [
          node.id,
          {
            x: position.x,
            y: position.y,
            depth: position.depth,
          },
        ];
      }),
    );
  }

  const depths = getLayeredDepths(nodes, edges);
  const groups = new Map<number, PageNode[]>();

  for (const node of nodes) {
    const depth = depths.get(node.id) ?? 0;
    const group = groups.get(depth) ?? [];
    group.push(node);
    groups.set(depth, group);
  }

  for (const group of groups.values()) {
    group.sort((a, b) => {
      const stepDiff = (a.first_seen_step ?? Number.MAX_SAFE_INTEGER) - (b.first_seen_step ?? Number.MAX_SAFE_INTEGER);
      return stepDiff || a.name.localeCompare(b.name);
    });
  }

  const result: Record<string, PageMapPosition> = {};
  const sortedDepths = Array.from(groups.keys()).sort((a, b) => a - b);

  for (const depth of sortedDepths) {
    const group = groups.get(depth) ?? [];
    const columnHeight = group.length * nodeHeight + Math.max(0, group.length - 1) * rowGap;
    const yOffset = -columnHeight / 2 + nodeHeight / 2;

    group.forEach((node, index) => {
      result[node.id] = {
        x: depth * (nodeWidth + columnGap),
        y: yOffset + index * (nodeHeight + rowGap),
        depth,
      };
    });
  }

  return result;
}
