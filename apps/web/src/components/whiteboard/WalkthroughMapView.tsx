import { useEffect, useMemo, useState } from "react";
import { ArtifactLink } from "../common/ArtifactLink";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import {
  EVIDENCE_FOCUS_EVENT,
  type Artifact,
  type ConsoleStatus,
  type EvidenceFocusRequest,
  type PageNode,
  type PageType,
  type RunDetail,
  type WalkthroughMapResponse,
} from "../../types/contracts";
import { PageDetailPanel } from "./PageDetailPanel";
import { PageMapFilters, pageStatusOptions, type PageMapFiltersState } from "./PageMapFilters";
import { PageMapLegend } from "./PageMapLegend";
import { WhiteboardCanvas } from "./WhiteboardCanvas";

interface WalkthroughMapViewProps {
  map: WalkthroughMapResponse | null;
  run: RunDetail | null;
  artifacts: Artifact[];
  status: ConsoleStatus;
  loading: boolean;
  error: string | null;
  onOpenEvidence: () => void;
}

const defaultFilters: PageMapFiltersState = {
  query: "",
  statuses: pageStatusOptions,
  pageType: "all",
  issuesOnly: false,
  screenshotsOnly: false,
};

function nodeMatchesQuery(node: PageNode, query: string): boolean {
  const normalized = query.trim().toLowerCase();

  if (!normalized) {
    return true;
  }

  return [
    node.name,
    node.title,
    node.url,
    node.route,
    node.canonical_url,
    node.purpose,
    ...node.key_functions,
    ...node.key_controls,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(normalized));
}

function filterNodes(nodes: PageNode[], filters: PageMapFiltersState): PageNode[] {
  return nodes.filter((node) => {
    if (!filters.statuses.includes(node.status)) {
      return false;
    }

    if (filters.pageType !== "all" && node.page_type !== filters.pageType) {
      return false;
    }

    if (filters.issuesOnly && node.issues.length === 0) {
      return false;
    }

    if (filters.screenshotsOnly && node.screenshot_evidence.length === 0 && !node.primary_screenshot_artifact_id) {
      return false;
    }

    return nodeMatchesQuery(node, filters.query);
  });
}

function dispatchEvidenceFocus(runId: string, evidenceId: string, artifactId?: string | null): void {
  const detail: EvidenceFocusRequest = {
    runId,
    evidenceId,
    artifactId: artifactId ?? null,
  };

  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      window.dispatchEvent(new CustomEvent<EvidenceFocusRequest>(EVIDENCE_FOCUS_EVENT, { detail }));
    });
  });
}

export function WalkthroughMapView({
  map,
  run,
  artifacts,
  status,
  loading,
  error,
  onOpenEvidence,
}: WalkthroughMapViewProps) {
  const [filters, setFilters] = useState<PageMapFiltersState>(defaultFilters);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const pageTypes = useMemo(
    () => (map ? Array.from(new Set(map.nodes.map((node) => node.page_type))).sort() as PageType[] : []),
    [map],
  );
  const visibleNodes = useMemo(() => (map ? filterNodes(map.nodes, filters) : []), [filters, map]);
  const selectedNode = useMemo(
    () => (map && selectedNodeId ? map.nodes.find((node) => node.id === selectedNodeId) ?? null : null),
    [map, selectedNodeId],
  );

  useEffect(() => {
    if (!map?.nodes.length) {
      setSelectedNodeId(null);
      return;
    }

    if (!selectedNodeId || !map.nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(map.nodes[0].id);
    }
  }, [map, selectedNodeId]);

  useEffect(() => {
    if (!visibleNodes.length) {
      return;
    }

    if (!selectedNodeId || !visibleNodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(visibleNodes[0].id);
    }
  }, [selectedNodeId, visibleNodes]);

  const focusEvidence = (evidenceId: string, artifactId?: string | null) => {
    if (!map) {
      return;
    }

    onOpenEvidence();
    dispatchEvidenceFocus(map.run_id, evidenceId, artifactId);
  };

  if (loading && !map) {
    return (
      <section className="panel whiteboard-panel" aria-labelledby="whiteboard-title">
        <div className="panel-header">
          <div>
            <h2 id="whiteboard-title">白板 / 页面地图</h2>
            <p>正在读取页面关系、截图证据和节点摘要。</p>
          </div>
        </div>
        <EmptyState title="正在加载页面地图" message="走查完成后会自动生成页面节点和跳转关系。" />
      </section>
    );
  }

  if (!map && error) {
    return (
      <section className="panel whiteboard-panel" aria-labelledby="whiteboard-title">
        <div className="panel-header">
          <div>
            <h2 id="whiteboard-title">白板 / 页面地图</h2>
            <p>页面地图暂时不可用，其他报告和证据视图不受影响。</p>
          </div>
        </div>
        <ErrorState title="页面地图不可用" message="当前 run 没有可读取的 walkthrough_map 结果。" details={error} />
      </section>
    );
  }

  if (!map) {
    const waitingCopy =
      status === "running" || status === "awaiting_verification"
        ? "走查结束后会在这里显示页面结构图。"
        : "当前 run 没有页面地图数据。";

    return (
      <section className="panel whiteboard-panel" aria-labelledby="whiteboard-title">
        <div className="panel-header">
          <div>
            <h2 id="whiteboard-title">白板 / 页面地图</h2>
            <p>{run ? run.research_goal : "选择或启动一个 run 后查看页面地图。"}</p>
          </div>
        </div>
        <EmptyState title="暂无页面地图" message={waitingCopy} />
      </section>
    );
  }

  const mapSubtitle = run?.research_goal ?? (map.products.map((product) => product.name).join(" / ") || "Walkthrough map");

  return (
    <section className="panel whiteboard-panel" aria-labelledby="whiteboard-title">
      <div className="panel-header whiteboard-header">
        <div>
          <h2 id="whiteboard-title">白板 / 页面地图</h2>
          <p>{mapSubtitle}</p>
        </div>
        <div className="panel-header-actions">
          <ArtifactLink artifactId={map.artifact_id} artifacts={artifacts} runId={map.run_id} label="打开地图源文件" />
        </div>
      </div>

      {error ? (
        <ErrorState
          title="页面地图刷新失败"
          message="当前仍显示最近一次可用地图。"
          details={error}
          tone="blocked"
          compact
        />
      ) : null}

      <div className="whiteboard-summary-row">
        <PageMapLegend map={map} visibleNodes={visibleNodes} />
        <PageMapFilters filters={filters} pageTypes={pageTypes} onChange={setFilters} onReset={() => setFilters(defaultFilters)} />
      </div>

      {map.warnings.length ? (
        <div className="page-map-warning-strip">
          {map.warnings.slice(0, 2).map((warning) => (
            <span key={warning.code}>
              <strong>{warning.code}</strong> {warning.message}
            </span>
          ))}
        </div>
      ) : null}

      <div className="whiteboard-shell">
        <WhiteboardCanvas map={map} nodes={visibleNodes} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />
        <PageDetailPanel map={map} node={selectedNode} artifacts={artifacts} onFocusEvidence={focusEvidence} />
      </div>
    </section>
  );
}
