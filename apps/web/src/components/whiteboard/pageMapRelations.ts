import type { PageEdge, PageNode } from "../../types/contracts";

export type PageEdgeRelation = "navigation" | "detail" | "external" | "blocked" | "inferred";

export const pageEdgeRelationLabels: Record<PageEdgeRelation, string> = {
  navigation: "visited/navigation",
  detail: "detail/settings",
  external: "external",
  blocked: "blocked/error",
  inferred: "inferred",
};

export const pageEdgeRelationColors: Record<PageEdgeRelation, string> = {
  navigation: "#1f5ed2",
  detail: "#6d54d9",
  external: "#2876bd",
  blocked: "#b86b00",
  inferred: "#7b8798",
};

export function getPageEdgeRelation(edge: PageEdge, target?: PageNode): PageEdgeRelation {
  const mapRelation = String(edge.metadata.map_relation ?? edge.metadata.structural_relation ?? "");

  if (["detail_parent", "route_parent"].includes(mapRelation)) {
    return "detail";
  }

  if (mapRelation === "external") {
    return "external";
  }

  if (mapRelation === "blocked") {
    return "blocked";
  }

  if (mapRelation === "walkthrough_path" || mapRelation === "entry_link" || mapRelation === "discovered_from") {
    return edge.kind === "inferred" || edge.confidence < 0.5 ? "inferred" : "navigation";
  }

  if (mapRelation === "app_navigation") {
    return edge.kind === "inferred" && edge.confidence < 0.5 ? "inferred" : "navigation";
  }

  if (target?.status === "blocked" || target?.status === "error" || target?.page_type === "error") {
    return "blocked";
  }

  if (target?.status === "external" || target?.page_type === "external") {
    return "external";
  }

  if (target && ["detail", "settings", "form", "auth"].includes(target.page_type)) {
    return "detail";
  }

  if (edge.kind === "inferred" || edge.confidence < 0.5) {
    return "inferred";
  }

  return "navigation";
}
