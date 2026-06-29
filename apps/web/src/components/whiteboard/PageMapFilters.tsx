import type { PageNodeStatus, PageType } from "../../types/contracts";

export const pageStatusOptions: PageNodeStatus[] = ["visited", "blocked", "discovered", "external", "error"];

export interface PageMapFiltersState {
  query: string;
  statuses: PageNodeStatus[];
  pageType: PageType | "all";
  issuesOnly: boolean;
  screenshotsOnly: boolean;
  showUncoveredEntries: boolean;
}

interface PageMapFiltersProps {
  filters: PageMapFiltersState;
  pageTypes: PageType[];
  onChange: (filters: PageMapFiltersState) => void;
  onReset: () => void;
}

const statusLabels: Record<PageNodeStatus, string> = {
  visited: "已访问",
  blocked: "受阻",
  discovered: "已发现",
  external: "外部",
  error: "异常",
};

const typeLabels: Record<PageType, string> = {
  dashboard: "看板",
  list: "列表",
  detail: "详情",
  settings: "设置",
  form: "表单",
  auth: "登录/验证",
  error: "错误页",
  external: "外部页",
  unknown: "未知",
};

export function PageMapFilters({ filters, pageTypes, onChange, onReset }: PageMapFiltersProps) {
  const update = (patch: Partial<PageMapFiltersState>) => onChange({ ...filters, ...patch });
  const toggleStatus = (status: PageNodeStatus) => {
    const nextStatuses = filters.statuses.includes(status)
      ? filters.statuses.filter((item) => item !== status)
      : [...filters.statuses, status];

    update({ statuses: nextStatuses });
  };
  const hasActiveFilters =
    filters.query.trim() ||
    filters.statuses.length !== pageStatusOptions.length ||
    filters.pageType !== "all" ||
    filters.issuesOnly ||
    filters.screenshotsOnly ||
    filters.showUncoveredEntries;

  return (
    <div className="page-map-filters" aria-label="页面地图筛选">
      <label className="field page-map-search">
        <span>搜索页面</span>
        <input
          value={filters.query}
          placeholder="页面名、URL、用途"
          onChange={(event) => update({ query: event.target.value })}
        />
      </label>
      <label className="field page-map-type-filter">
        <span>页面类型</span>
        <select value={filters.pageType} onChange={(event) => update({ pageType: event.target.value as PageType | "all" })}>
          <option value="all">全部</option>
          {pageTypes.map((type) => (
            <option key={type} value={type}>
              {typeLabels[type]}
            </option>
          ))}
        </select>
      </label>
      <div className="page-map-status-filters" role="group" aria-label="页面状态">
        {pageStatusOptions.map((status) => (
          <label key={status} className={`page-map-check page-map-check-${status}`}>
            <input type="checkbox" checked={filters.statuses.includes(status)} onChange={() => toggleStatus(status)} />
            <span>{statusLabels[status]}</span>
          </label>
        ))}
      </div>
      <div className="page-map-toggle-row">
        <label className="page-map-check">
          <input type="checkbox" checked={filters.issuesOnly} onChange={(event) => update({ issuesOnly: event.target.checked })} />
          <span>只看有问题</span>
        </label>
        <label className="page-map-check">
          <input
            type="checkbox"
            checked={filters.screenshotsOnly}
            onChange={(event) => update({ screenshotsOnly: event.target.checked })}
          />
          <span>只看有截图</span>
        </label>
        <label className="page-map-check page-map-check-entry" title="页面上发现但本次没有实际进入的按钮或菜单入口，不代表报错。">
          <input
            type="checkbox"
            checked={filters.showUncoveredEntries}
            onChange={(event) => update({ showUncoveredEntries: event.target.checked })}
          />
          <span>显示未覆盖入口</span>
        </label>
        <button type="button" onClick={onReset} disabled={!hasActiveFilters}>
          重置
        </button>
      </div>
    </div>
  );
}
