import type { PageEdge, PageNode, WalkthroughMapResponse } from "../../types/contracts";

export interface PageMapPosition {
  x: number;
  y: number;
  depth: number;
}

const nodeWidth = 344;
const nodeHeight = 226;
const columnGap = 126;
const rowGap = 58;
const laneGap = 390;
const sideColumnGap = 170;
const presetCollisionPadding = 18;

interface LayoutBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

const detailPageTypes = new Set<PageNode["page_type"]>(["detail", "settings", "form", "auth"]);
type LayoutRole = "entry" | "primary" | "detail" | "settings" | "task" | "external";

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

  if (layout.algorithm === "product_structure_v2") {
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

function layoutBoxesOverlap(a: LayoutBox, b: LayoutBox, padding = 0): boolean {
  return !(
    a.x + a.width + padding <= b.x ||
    b.x + b.width + padding <= a.x ||
    a.y + a.height + padding <= b.y ||
    b.y + b.height + padding <= a.y
  );
}

function getDeoverlappedPresetLayout(
  nodes: PageNode[],
  layout: NonNullable<WalkthroughMapResponse["layout"]>,
): Record<string, PageMapPosition> {
  const placedBoxes: LayoutBox[] = [];
  const result: Record<string, PageMapPosition> = {};
  const orderedNodes = [...nodes].sort((a, b) => {
    const aPosition = layout.nodes?.[a.id];
    const bPosition = layout.nodes?.[b.id];

    return (
      (aPosition?.x ?? 0) - (bPosition?.x ?? 0) ||
      (aPosition?.y ?? 0) - (bPosition?.y ?? 0) ||
      (aPosition?.depth ?? 0) - (bPosition?.depth ?? 0) ||
      sortNodes(a, b)
    );
  });

  for (const node of orderedNodes) {
    const position = layout.nodes?.[node.id];
    if (!position) {
      continue;
    }

    let y = position.y;
    for (let attempt = 0; attempt < nodes.length + 8; attempt += 1) {
      const candidate = { x: position.x, y, width: nodeWidth, height: nodeHeight };
      const colliders = placedBoxes.filter((box) => layoutBoxesOverlap(candidate, box, presetCollisionPadding));

      if (!colliders.length) {
        break;
      }

      y = Math.max(y + 1, ...colliders.map((box) => box.y + box.height + presetCollisionPadding));
    }

    result[node.id] = {
      x: position.x,
      y,
      depth: position.depth,
    };
    placedBoxes.push({ x: position.x, y, width: nodeWidth, height: nodeHeight });
  }

  return result;
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

function routeSection(node: PageNode): string {
  const metadataSection = typeof node.metadata.route_section === "string" ? node.metadata.route_section : "";
  if (metadataSection) {
    return metadataSection;
  }

  const path = getRoutePath(node) ?? "/";
  const segments = path.replace(/^#?!?\/?/, "").split("/").filter(Boolean);
  return segments[0] ?? "home";
}

function buildSectionOffsets(nodes: PageNode[]): Map<string, number> {
  const sections = Array.from(
    new Map(
      nodes
        .filter((node) => !isSideNode(node))
        .sort(sortNodes)
        .map((node) => [routeSection(node), routeSection(node)]),
    ).keys(),
  );
  const midpoint = (sections.length - 1) / 2;
  const offsets = new Map<string, number>();

  sections.forEach((section, index) => {
    offsets.set(section, Math.round((index - midpoint) * 168));
  });

  return offsets;
}

function layoutRole(node: PageNode, incomingCount: number): LayoutRole {
  const metadataRole = typeof node.metadata.layout_role === "string" ? node.metadata.layout_role : "";

  if (isSideNode(node)) {
    return "external";
  }

  if (metadataRole === "entry" || incomingCount === 0) {
    return "entry";
  }

  if (node.page_type === "settings") {
    return "settings";
  }

  if (node.page_type === "detail") {
    return "detail";
  }

  if (node.page_type === "form" || node.page_type === "auth" || node.status === "blocked") {
    return "task";
  }

  return "primary";
}

function roleOffset(role: LayoutRole): number {
  if (role === "detail") {
    return 214;
  }

  if (role === "settings") {
    return 332;
  }

  if (role === "task") {
    return -236;
  }

  if (role === "external") {
    return -360;
  }

  return 0;
}

function nodeVerticalOffset(
  node: PageNode,
  incomingCount: number,
  sectionOffsets: Map<string, number>,
  depth: number,
): number {
  const role = layoutRole(node, incomingCount);
  const sectionOffset = sectionOffsets.get(routeSection(node)) ?? 0;

  if (role === "entry") {
    return 0;
  }

  if (role === "primary") {
    return sectionOffset || (depth % 2 === 0 ? 126 : -126);
  }

  return Math.round(roleOffset(role) + sectionOffset * 0.35);
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
  const sectionOffsets = buildSectionOffsets(nodes);
  const parentById = new Map<string, string | null>();

  for (const node of nodes) {
    parentById.set(node.id, getParentId(node, nodesById, incoming));
  }

  const rootNodes = nodes
    .filter((node) => !isSideNode(node) && !parentById.get(node.id) && (incoming.get(node.id)?.length ?? 0) === 0)
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
      const incomingCount = incoming.get(child.id)?.length ?? 0;
      const y = sourcePosition.y + childOffset(index, primaryChildren.length) + nodeVerticalOffset(child, incomingCount, sectionOffsets, depth);
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
    const incomingCount = incoming.get(node.id)?.length ?? 0;
    const preferredY = parentPosition
      ? parentPosition.y + childOffset(siblingIndex, siblingDetails.length) + nodeVerticalOffset(node, incomingCount, sectionOffsets, depth)
      : roots.length * laneGap + nodeVerticalOffset(node, incomingCount, sectionOffsets, depth);

    result[node.id] = reservePosition(result, preferredX, preferredY, depth);
    placed.add(node.id);
  }

  const maxX = Math.max(0, ...Object.values(result).map((position) => position.x));
  const sideX = maxX + nodeWidth + sideColumnGap;
  const sideNodes = nodes.filter(isSideNode).sort(sortNodes);

  sideNodes.forEach((node, index) => {
    const parentId = parentById.get(node.id);
    const parentPosition = parentId ? result[parentId] : undefined;
    const incomingCount = incoming.get(node.id)?.length ?? 0;
    const y = parentPosition
      ? parentPosition.y + childOffset(index, sideNodes.length) + nodeVerticalOffset(node, incomingCount, sectionOffsets, maxX)
      : index * (nodeHeight + rowGap) + nodeVerticalOffset(node, incomingCount, sectionOffsets, maxX);

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
    return getDeoverlappedPresetLayout(nodes, layout!);
  }

  return getStructuredFallbackLayout(nodes, edges);
}
