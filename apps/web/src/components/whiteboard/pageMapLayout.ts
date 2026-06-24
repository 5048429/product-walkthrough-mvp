import type { PageEdge, PageNode, WalkthroughMapResponse } from "../../types/contracts";

export interface PageMapPosition {
  x: number;
  y: number;
  depth: number;
}

const nodeWidth = 304;
const nodeHeight = 188;
const columnGap = 126;
const rowGap = 58;
const laneGap = 390;
const sideColumnGap = 170;

const detailPageTypes = new Set<PageNode["page_type"]>(["detail", "settings", "form", "auth"]);

function hasPresetLayout(layout: WalkthroughMapResponse["layout"] | undefined, nodes: PageNode[]): boolean {
  if (!layout?.nodes) {
    return false;
  }

  const positions = nodes.map((node) => layout.nodes[node.id]);
  const hasEveryPosition = positions.every((position) => {
    return (
      position &&
      Number.isFinite(position.x) &&
      Number.isFinite(position.y) &&
      Number.isFinite(position.depth)
    );
  });

  if (!hasEveryPosition) {
    return false;
  }

  if (nodes.length <= 1) {
    return true;
  }

  if (layout.algorithm === "prototype_map") {
    return true;
  }

  const presetPositions = positions as Array<{ x: number; y: number; depth: number }>;
  const xs = presetPositions.map((position) => position.x);
  const ys = presetPositions.map((position) => position.y);
  const spanX = Math.max(...xs) - Math.min(...xs);
  const spanY = Math.max(...ys) - Math.min(...ys);
  const uniqueYCount = new Set(ys.map((y) => Math.round(y / 20))).size;
  const uniqueXs = Array.from(new Set(xs.map((x) => Math.round(x)))).sort((a, b) => a - b);
  const positiveXGaps = uniqueXs.slice(1).map((x, index) => x - uniqueXs[index]);
  const hasTightColumns = positiveXGaps.some((gap) => gap < nodeWidth + 48);

  return !hasTightColumns && !(spanX > nodeWidth * 2 && (spanY < nodeHeight * 0.8 || uniqueYCount <= 2));
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

function getRoutePath(node: PageNode): string | null {
  const path = node.route ?? node.metadata.normalized_route;

  if (path) {
    return path.startsWith("/") ? path : `/${path}`;
  }

  if (!node.url) {
    return null;
  }

  try {
    return new URL(node.url).pathname || "/";
  } catch {
    return null;
  }
}

function isChildRoute(parent: PageNode, child: PageNode): boolean {
  const parentPath = getRoutePath(parent);
  const childPath = getRoutePath(child);

  return Boolean(parentPath && childPath && parentPath !== "/" && childPath.startsWith(`${parentPath}/`));
}

function sortNodes(a: PageNode, b: PageNode): number {
  const stepDiff = (a.first_seen_step ?? Number.MAX_SAFE_INTEGER) - (b.first_seen_step ?? Number.MAX_SAFE_INTEGER);
  const productDiff = a.product.localeCompare(b.product);

  return productDiff || stepDiff || a.name.localeCompare(b.name);
}

function isSideNode(node: PageNode): boolean {
  return node.status === "external" || node.status === "error" || node.page_type === "external" || node.page_type === "error";
}

function isDetailNode(node: PageNode, incomingCount: number): boolean {
  return incomingCount > 0 && detailPageTypes.has(node.page_type);
}

function buildEdgeIndexes(nodes: PageNode[], edges: PageEdge[]) {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const outgoing = new Map<string, PageEdge[]>();
  const incoming = new Map<string, PageEdge[]>();

  for (const node of nodes) {
    outgoing.set(node.id, []);
    incoming.set(node.id, []);
  }

  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      continue;
    }

    outgoing.get(edge.source)?.push(edge);
    incoming.get(edge.target)?.push(edge);
  }

  for (const edgeList of [...outgoing.values(), ...incoming.values()]) {
    edgeList.sort((a, b) => b.confidence - a.confidence || a.id.localeCompare(b.id));
  }

  return { incoming, outgoing };
}

function getParentId(
  node: PageNode,
  nodesById: Map<string, PageNode>,
  incoming: Map<string, PageEdge[]>,
): string | null {
  const structuralParent = node.metadata.structural_parent_node_id;

  if (typeof structuralParent === "string" && nodesById.has(structuralParent)) {
    return structuralParent;
  }

  const discoveredFrom = node.metadata.discovered_from_node_id;

  if (typeof discoveredFrom === "string" && nodesById.has(discoveredFrom)) {
    return discoveredFrom;
  }

  const incomingEdges = incoming.get(node.id) ?? [];
  const structuralEdge = incomingEdges.find((edge) => {
    const relation = String(edge.metadata.map_relation ?? edge.metadata.structural_relation ?? "");
    return ["app_navigation", "detail_parent", "route_parent"].includes(relation);
  });

  if (structuralEdge) {
    return structuralEdge.source;
  }

  const routeParent = Array.from(nodesById.values())
    .filter((candidate) => candidate.id !== node.id && isChildRoute(candidate, node))
    .sort((a, b) => (getRoutePath(b)?.length ?? 0) - (getRoutePath(a)?.length ?? 0))[0];

  if (routeParent) {
    return routeParent.id;
  }

  const nonTraceEdge = incomingEdges.find((edge) => edge.metadata.map_relation !== "walkthrough_path");

  return nonTraceEdge?.source ?? null;
}

function reservePosition(
  result: Record<string, PageMapPosition>,
  x: number,
  preferredY: number,
  depth: number,
): PageMapPosition {
  let y = preferredY;
  const minDistance = nodeHeight + rowGap;

  while (
    Object.values(result).some(
      (position) => Math.abs(position.x - x) < nodeWidth * 0.45 && Math.abs(position.y - y) < minDistance,
    )
  ) {
    y += minDistance;
  }

  return { x, y, depth };
}

function childOffset(index: number, count: number): number {
  return (index - (count - 1) / 2) * (nodeHeight + rowGap);
}

function getStructuredFallbackLayout(nodes: PageNode[], edges: PageEdge[]): Record<string, PageMapPosition> {
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const { incoming, outgoing } = buildEdgeIndexes(nodes, edges);
  const depths = getLayeredDepths(nodes, edges);
  const parentById = new Map<string, string | null>();

  for (const node of nodes) {
    parentById.set(node.id, getParentId(node, nodesById, incoming));
  }

  const rootNodes = nodes
    .filter((node) => !isSideNode(node) && (!parentById.get(node.id) || (incoming.get(node.id)?.length ?? 0) === 0))
    .sort(sortNodes);
  const roots = rootNodes.length ? rootNodes : nodes.filter((node) => !isSideNode(node)).slice(0, 1);
  const result: Record<string, PageMapPosition> = {};
  const placed = new Set<string>();

  roots.forEach((root, index) => {
    result[root.id] = { x: 0, y: index * laneGap, depth: 0 };
    placed.add(root.id);
  });

  const queue = roots.map((root) => root.id);

  while (queue.length) {
    const sourceId = queue.shift()!;
    const sourcePosition = result[sourceId];

    if (!sourcePosition) {
      continue;
    }

    const primaryChildren = (outgoing.get(sourceId) ?? [])
      .map((edge) => nodesById.get(edge.target))
      .filter((node): node is PageNode => Boolean(node))
      .filter((node) => !placed.has(node.id) && !isSideNode(node) && !isDetailNode(node, incoming.get(node.id)?.length ?? 0))
      .sort(sortNodes);

    primaryChildren.forEach((child, index) => {
      const depth = Math.max(sourcePosition.depth + 1, depths.get(child.id) ?? sourcePosition.depth + 1);
      const x = depth * (nodeWidth + columnGap);
      const y = sourcePosition.y + childOffset(index, primaryChildren.length);
      result[child.id] = reservePosition(result, x, y, depth);
      placed.add(child.id);
      queue.push(child.id);
    });
  }

  const nonSideNodes = nodes.filter((node) => !isSideNode(node)).sort(sortNodes);

  for (const node of nonSideNodes) {
    if (placed.has(node.id)) {
      continue;
    }

    const parentId = parentById.get(node.id);
    const parentPosition = parentId ? result[parentId] : undefined;
    const depth = parentPosition ? parentPosition.depth + 1 : depths.get(node.id) ?? 0;
    const siblingDetails = nonSideNodes.filter((candidate) => parentById.get(candidate.id) === parentId && !placed.has(candidate.id));
    const siblingIndex = Math.max(0, siblingDetails.findIndex((candidate) => candidate.id === node.id));
    const preferredX = parentPosition ? parentPosition.x + nodeWidth + columnGap : depth * (nodeWidth + columnGap);
    const preferredY = parentPosition ? parentPosition.y + childOffset(siblingIndex, siblingDetails.length) : roots.length * laneGap;

    result[node.id] = reservePosition(result, preferredX, preferredY, depth);
    placed.add(node.id);
  }

  const maxX = Math.max(0, ...Object.values(result).map((position) => position.x));
  const sideX = maxX + nodeWidth + sideColumnGap;
  const sideNodes = nodes.filter(isSideNode).sort(sortNodes);

  sideNodes.forEach((node, index) => {
    const parentId = parentById.get(node.id);
    const parentPosition = parentId ? result[parentId] : undefined;
    const y = parentPosition ? parentPosition.y + childOffset(index, sideNodes.length) : index * (nodeHeight + rowGap);

    result[node.id] = reservePosition(result, sideX, y, Math.round(sideX / (nodeWidth + columnGap)));
  });

  return result;
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

  return getStructuredFallbackLayout(nodes, edges);
}
