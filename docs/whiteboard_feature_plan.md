# 走查页面关系白板功能规划

## 0. 背景与现状判断

当前项目已经具备本地 Web 控制台、FastAPI 服务、真实 `browser-use` 页面走查、人工登录/验证、运行进度展示、报告预览、证据查看、截图 artifact、历史 run 浏览等能力。白板功能不应该重建一套新的采集和存储体系，而应该把已有 run artifact 结构化成一个更适合产品经理理解的“产品结构图”。

本次阅读到的关键现状：

- `ResearchDirector.run()` 在走查后写出 `evidence.json`、`report.md`、`evaluation.json`。
- `RunRuntime._postprocess_run_outputs()` 会归档 browser-use history，并对 evidence 里的本地路径和敏感字段做清理。
- `RunRuntime._build_artifacts()` 已经把 `run.json`、`plan.json`、`events.jsonl`、`agents.json`、`artifacts.json`、`evidence.json`、`report.md`、`evaluation.json`、截图、browser history 注册为 artifact。
- `GET /api/runs/{run_id}/evidence` 会返回 normalized evidence，并把截图引用映射为 `screenshot_artifact_id` / `screenshot_artifact_ids`。
- 前端 `ConsolePage.tsx` 当前是单页 workbench，用 tab 展示 dashboard / report / evidence / history / details。
- 前端 API 层集中在 `apps/web/src/api/client.ts`，类型集中在 `apps/web/src/types/contracts.ts`，状态聚合集中在 `apps/web/src/hooks/useProdwalkConsole.ts`。
- `apps/web/package.json` 当前只有 React / React DOM，未引入图谱或可视化库。

结论：第一版白板应作为“走查后 artifact + API + 控制台新 tab”接入，不做实时协作、不做独立数据库、不改现有业务走查逻辑。

## 1. 需求定义

### 1.1 产品目标

页面关系白板要解决的问题是：产品经理在一次真实产品走查后，不能只看到线性日志和文字报告，还需要快速理解“这个产品由哪些页面/功能表面组成、agent 实际走到了哪里、页面之间怎样跳转、关键流程有没有断点”。它应该把走查轨迹从文本证据转成一个可浏览的产品结构图。

白板的核心价值：

- 快速理解产品的信息架构和主要导航路径。
- 看清 agent 实际访问过哪些页面，哪些页面只是被发现但未进入。
- 识别页面层级、流程闭环、跳转断点、外部跳转和错误页。
- 点击页面节点后能查看该页面的用途、主要功能、入口控件、相关证据和截图。
- 为后续竞品分析、产品走查报告、PRD 梳理提供结构化素材。

### 1.2 与现有视图的区别

报告预览：

- 面向结论表达，强调总结、发现、建议、评分。
- 通常是线性的 Markdown 文档，不适合快速看页面拓扑。
- 白板不替代报告，而是作为报告的结构化入口和证据导航。

运行日志：

- 面向执行追踪，强调事件时间线、agent 状态、artifact 生成过程。
- 适合调试任务是否执行成功，不适合 PM 理解产品结构。
- 白板只吸收日志中的关键上下文，例如步骤序号、agent 观察、artifact 引用。

agent 进度展示：

- 面向 run 进行中状态，回答“当前走到哪一步、哪个 agent 在工作”。
- 白板第一版以走查完成后查看为主，回答“最终发现了哪些页面和关系”。

证据查看：

- 面向 evidence item 列表和截图。
- 白板会把 evidence 按页面节点重新组织，让用户从页面结构进入证据。

### 1.3 MVP 不做什么

第一版避免范围过大，明确不做：

- 不做实时生成白板，不要求边走查边更新节点。
- 不做可编辑白板，不支持用户拖拽保存布局、改节点名称、增删边。
- 不做多人协作、评论、权限、云端同步。
- 不做完整爬虫，不承诺发现产品所有页面。
- 不做页面自动回放或浏览器重放。
- 不做跨 run 对比、版本 diff、竞品矩阵。
- 不做 AI 自动生成完美 IA；页面名称、用途、类型可以有置信度和 fallback。
- 不做复杂图算法、力导向炫技图或大型知识图谱。
- 不做 PRD 自动生成，只为后续 PRD 提供结构化输入。

## 2. 用户流程

### 2.1 完整流程

1. 用户在控制台选择走查计划。
2. 用户完成人工登录准备或选择已有登录态。
3. 用户启动真实走查。
4. `BrowserWalker` / `BrowserUseLocalWalker` 访问页面并记录 browser-use history、URL 序列、action、title、截图路径、每步 summary。
5. `EvidenceExtractor` 归档截图到 run 目录，`ResearchDirector` 写出 `evidence.json`、`report.md`、`evaluation.json`。
6. 后端在 run 结束后生成 `walkthrough_map.json`。
7. 后端注册 `walkthrough_map.json` 为 artifact，并通过 `GET /api/runs/{run_id}/map` 暴露。
8. 前端收到 run terminal event 后加载 report / evidence / evaluation，同时加载 map。
9. 控制台出现“白板 / 页面地图”tab。
10. 用户打开白板，看到页面节点和跳转边。
11. 用户点击某个页面节点，右侧详情面板展示页面名称、URL、页面类型、用途、关键功能、主要控件、问题、截图、相关 evidence 和 agent 观察。
12. 用户在详情里点击截图或 evidence link，跳转到现有截图预览 / evidence 视图 / report 证据位置。

### 2.2 关键用户场景

产品经理首次理解产品：

- 打开白板后先看节点分组和主路径，例如 Home -> Transactions -> Detail。
- 看节点颜色判断成功访问、受阻、外链、错误页。
- 点开节点看截图和简短用途。

走查复盘：

- 看到 agent 没有进入某个设置子页面，标记为 discovered-but-unvisited。
- 通过边的标签看到跳转来源是菜单、按钮、搜索结果还是未知推断。
- 点击对应 evidence 查看 agent 当时的观察记录。

报告写作：

- 从白板确认报告里的关键流程是否闭环。
- 把节点详情中的功能点、问题、截图证据带入报告和 PRD。

## 3. 信息架构

### 3.1 TypeScript 数据结构草案

```ts
export type PageType =
  | "dashboard"
  | "list"
  | "detail"
  | "settings"
  | "form"
  | "auth"
  | "error"
  | "external"
  | "unknown";

export type PageNodeStatus =
  | "visited"
  | "blocked"
  | "discovered"
  | "external"
  | "error";

export type EdgeKind =
  | "navigation"
  | "menu"
  | "button"
  | "link"
  | "redirect"
  | "form_submit"
  | "inferred";

export interface ScreenshotEvidence {
  id: string;
  artifact_id: string | null;
  title: string;
  path: string | null;
  content_url: string | null;
  screenshot_url: string | null;
  evidence_id: string | null;
  step_index: number | null;
  captured_at: string | null;
  is_primary: boolean;
}

export interface PageInsight {
  id: string;
  kind: "purpose" | "function" | "control" | "issue" | "observation";
  title: string;
  summary: string;
  severity?: "info" | "low" | "medium" | "high";
  confidence: number;
  evidence_ids: string[];
  source: "browser_step" | "browser_run_summary" | "report" | "evaluation" | "heuristic";
}

export interface PageNode {
  id: string;
  product: string;
  scenario_ids: string[];
  name: string;
  title: string | null;
  url: string | null;
  route: string | null;
  canonical_url: string | null;
  page_type: PageType;
  status: PageNodeStatus;
  purpose: string;
  key_functions: string[];
  key_controls: string[];
  issues: PageInsight[];
  observations: PageInsight[];
  screenshot_evidence: ScreenshotEvidence[];
  primary_screenshot_artifact_id: string | null;
  evidence_ids: string[];
  event_ids: string[];
  first_seen_step: number | null;
  last_seen_step: number | null;
  visit_count: number;
  confidence: number;
  metadata: {
    normalized_route: string | null;
    dynamic_route_pattern?: string | null;
    discovered_from_node_id?: string | null;
    source_history_artifact_ids?: string[];
    raw_titles?: string[];
    raw_urls?: string[];
  };
}

export interface PageEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  kind: EdgeKind;
  action: string | null;
  from_step_index: number | null;
  to_step_index: number | null;
  evidence_ids: string[];
  event_ids: string[];
  confidence: number;
  metadata: {
    source_url?: string | null;
    target_url?: string | null;
    inferred_reason?: string | null;
    occurrence_count?: number;
  };
}

export interface WalkthroughMap {
  run_id: string;
  artifact_id: string;
  generated_at: string;
  schema_version: "1.0";
  source_artifact_ids: string[];
  products: Array<{
    name: string;
    kind: string;
    start_url: string;
  }>;
  summary: {
    node_count: number;
    edge_count: number;
    visited_count: number;
    blocked_count: number;
    discovered_count: number;
    external_count: number;
    screenshot_count: number;
    confidence: number;
  };
  nodes: PageNode[];
  edges: PageEdge[];
  layout?: {
    algorithm: "layered" | "none";
    nodes: Record<string, { x: number; y: number; depth: number }>;
  };
  warnings: Array<{
    code: string;
    message: string;
    details?: Record<string, unknown>;
  }>;
}
```

### 3.2 后端 JSON 返回结构草案

`GET /api/runs/{run_id}/map`：

```json
{
  "run_id": "run-20260623-190713-568156",
  "artifact_id": "art_walkthrough_map",
  "generated_at": "2026-06-24T10:00:00Z",
  "schema_version": "1.0",
  "source_artifact_ids": [
    "art_evidence_json",
    "art_report_md",
    "art_evaluation_json",
    "art_browser_history_browser_use_history_open_https_uat_dashboard..."
  ],
  "products": [
    {
      "name": "Clink UAT Dashboard",
      "kind": "owned",
      "start_url": "https://uat-dashboard.clinkbill.com/analytics"
    }
  ],
  "summary": {
    "node_count": 10,
    "edge_count": 9,
    "visited_count": 10,
    "blocked_count": 0,
    "discovered_count": 0,
    "external_count": 0,
    "screenshot_count": 21,
    "confidence": 0.78
  },
  "nodes": [
    {
      "id": "page_clink_uat_dashboard_analytics",
      "product": "Clink UAT Dashboard",
      "scenario_ids": ["clink_complete_continuous_walkthrough"],
      "name": "Analytics",
      "title": "Clink",
      "url": "https://uat-dashboard.clinkbill.com/analytics",
      "route": "/analytics",
      "canonical_url": "https://uat-dashboard.clinkbill.com/analytics",
      "page_type": "dashboard",
      "status": "visited",
      "purpose": "Dashboard overview for product metrics and navigation.",
      "key_functions": ["Metric overview", "Charts", "Date range controls"],
      "key_controls": ["Home", "Core Metrics", "View More"],
      "issues": [],
      "observations": [
        {
          "id": "ins_page_analytics_1",
          "kind": "observation",
          "title": "Navigation observed",
          "summary": "Left navigation was visible with Home, Data Insights, Transactions, Risk, Balances, Customers, Subscriptions, Products, Developers/Skills, and Settings.",
          "confidence": 0.75,
          "evidence_ids": ["ev-clink-uat-dashboard-clink_complete_continuous_walkthrough-browser-use-local"],
          "source": "browser_run_summary"
        }
      ],
      "screenshot_evidence": [
        {
          "id": "shot_analytics_step_3",
          "artifact_id": "art_screenshot_ev_clink_uat_dashboard_clink_complete_continuous_walkthrough_browser_use_local_step_3_25345aba",
          "title": "step-3.png",
          "path": "screenshots/ev-clink-uat-dashboard-clink-complete-continuous-walkthrough-browser-use-local-step-3.png",
          "content_url": "/api/runs/run-20260623-190713-568156/artifacts/art_screenshot_ev_clink_uat_dashboard_clink_complete_continuous_walkthrough_browser_use_local_step_3_25345aba/content",
          "screenshot_url": "/api/runs/run-20260623-190713-568156/screenshots/ev-clink-uat-dashboard-clink-complete-continuous-walkthrough-browser-use-local-step-3.png",
          "evidence_id": "ev-clink-uat-dashboard-clink_complete_continuous_walkthrough-browser-use-local-step-3",
          "step_index": 3,
          "captured_at": null,
          "is_primary": true
        }
      ],
      "primary_screenshot_artifact_id": "art_screenshot_ev_clink_uat_dashboard_clink_complete_continuous_walkthrough_browser_use_local_step_3_25345aba",
      "evidence_ids": [
        "ev-clink-uat-dashboard-clink_complete_continuous_walkthrough-browser-use-local-step-3"
      ],
      "event_ids": [],
      "first_seen_step": 1,
      "last_seen_step": 5,
      "visit_count": 5,
      "confidence": 0.86,
      "metadata": {
        "normalized_route": "/analytics",
        "raw_titles": ["Initial Actions", "uat-dashboard.clinkbill.com/analytics", "Clink"],
        "raw_urls": ["https://uat-dashboard.clinkbill.com/analytics"]
      }
    }
  ],
  "edges": [
    {
      "id": "edge_page_clink_uat_dashboard_analytics__page_clink_uat_dashboard_core_metrics",
      "source": "page_clink_uat_dashboard_analytics",
      "target": "page_clink_uat_dashboard_core_metrics",
      "label": "Core Metrics",
      "kind": "menu",
      "action": "replace_file, click",
      "from_step_index": 5,
      "to_step_index": 6,
      "evidence_ids": [
        "ev-clink-uat-dashboard-clink_complete_continuous_walkthrough-browser-use-local-step-6"
      ],
      "event_ids": [],
      "confidence": 0.72,
      "metadata": {
        "source_url": "https://uat-dashboard.clinkbill.com/analytics",
        "target_url": "https://uat-dashboard.clinkbill.com/data-insights/core-metrics",
        "inferred_reason": "Adjacent walkthrough steps changed URL after click action.",
        "occurrence_count": 1
      }
    }
  ],
  "layout": {
    "algorithm": "layered",
    "nodes": {
      "page_clink_uat_dashboard_analytics": { "x": 0, "y": 0, "depth": 0 }
    }
  },
  "warnings": [
    {
      "code": "EDGE_INFERRED_FROM_ADJACENT_STEPS",
      "message": "Some edges are inferred from adjacent URL changes and may not represent exact click targets."
    }
  ]
}
```

## 4. 数据来源分析

### 4.1 来源清单

| 来源 | 现有字段 | 可用于白板 | 需要新增或增强 |
| --- | --- | --- | --- |
| `browser-use` history | `history[].state.url`、`state.title`、`state.screenshot_path`、`model_output.action`、`result.extracted_content`、`result.long_term_memory`、`metadata.step_number` | 页面访问序列、标题、截图、动作、观察文本、相邻跳转推断 | 更稳定的 click target label、DOM role/name、当前 route key、外链拦截原因 |
| walker evidence | `WalkthroughResult.steps[]` 的 `index/action/status/observation/url/screenshot/evidence_ids`，`EvidenceItem` 的 `kind/title/summary/url/screenshot/data` | 节点、边、页面详情、相关证据、步骤状态 | 页面类型、关键控件、页面用途最好新增结构化采集或后处理 |
| screenshot artifacts | `artifacts.json` 中 `type=screenshot`、`metadata.content_url/path_url/screenshot_url` | 节点缩略图、详情截图、证据跳转 | 将截图和 PageNode 建立稳定关联；多截图主次排序 |
| run events | `events.jsonl`、API event `seq/type/agent_type/scenario_id/step_index/payload/artifact_ids` | 运行状态、终端状态、artifact 创建、后续跳转日志 | 真实 step event 粒度有限；当前很多 page 关系只能从 evidence/history 推断 |
| report / evaluation artifacts | `report.md`、`evaluation.json`，raw `evidence.json` 内的 `analyses/findings/review_notes` | 页面问题、产品发现、总结句、评分上下文 | normalized report API 当前不返回 findings 到页面粒度；需要 map builder 直接读 raw evidence 或新增 safe API |
| URL / title / DOM observations | URL、route、title、agent summary 中可见导航项和控件名称 | 页面命名、类型识别、主要入口 | DOM 控件列表目前不是稳定结构，主要从自然语言 summary 解析，准确度有限 |
| agent summary | browser_run evidence 的 `final_output` | 页面用途、关键功能、未走到/受阻信息 | 需要 JSON 解析容错；summary 不是强 schema |

### 4.2 当前已有的信息

已足够支撑 MVP 的字段：

- 访问过的 URL 序列：`results[].steps[].url` 和 browser_run `data.urls`。
- 每步动作：`results[].steps[].action`、browser history `model_output.action`。
- 每步观察：`results[].steps[].observation`、browser_step evidence `summary`。
- 页面标题：browser history `state.title`、browser_step evidence `data.title`。
- 截图：`results[].steps[].screenshot`、evidence `screenshot`、evidence `data.screenshot_path/screenshot_paths`，后端已可映射为 artifact id。
- 相关 evidence：`steps[].evidence_ids`。
- 走查整体总结：browser_run evidence `summary` / `data.final_output`。
- 历史 run artifact：`runs/run-*/browser-history/*.json` 和 `screenshots/*` 已注册。

### 4.3 需要新增或增强的信息

MVP 可以先用 heuristic 推断，但后续应增强：

- click target label：例如“Core Metrics”“Transactions”，不应只保存 `click`。
- DOM role/name：用于区分菜单、按钮、链接、表单提交。
- 页面类型：先根据 route/title/summary 推断，后续由 walker 采集结构化 page classification。
- 页面关键控件：先从 final_output 和 step summary 抽取，后续新增 `page_controls` evidence。
- discovered-but-unvisited 页面：需要采集导航菜单可见但未点击的入口，否则只能少量从 final_output 推断。
- SPA 状态：URL 不变但内容变化时，需要 title、active nav、heading 或 route key 辅助建节点。
- 跳转原因：目前相邻 URL 变化只能推断边，不能保证确切由哪个控件触发。

## 5. 后端改造规划

### 5.1 新增 artifact

建议新增 run artifact：

```text
runs/run-*/walkthrough_map.json
```

artifact 注册建议：

- `id`: `art_walkthrough_map`
- `type`: `walkthrough_map`
- `title`: `walkthrough_map.json`
- `path`: `walkthrough_map.json`
- `media_type`: `application/json`

需要更新：

- `src/prodwalk/server/models.py` 的 `ArtifactType`
- `RunRuntime._build_artifacts()` 固定 artifact specs
- 前端 `ArtifactType`
- mock artifacts

### 5.2 新增 API

新增：

```text
GET /api/runs/{run_id}/map
```

行为建议：

- 如果 `walkthrough_map.json` 已存在，读取并返回。
- 如果不存在但 `evidence.json` 存在，尝试重建并写入 `walkthrough_map.json`，再返回。
- 如果 `evidence.json` 不存在，返回 `ARTIFACT_NOT_FOUND`。
- 返回内容必须是 sanitized map，不暴露本地绝对路径、storage state、credentials、tokens。

可选：

```text
POST /api/runs/{run_id}/map/rebuild
```

MVP 暂不需要开放 rebuild POST；`GET` 的 read-through rebuild 足够支持历史 run。

### 5.3 生成时机

推荐生成时机：

1. `ResearchDirector` 写出 `evidence.json`。
2. `RunRuntime._postprocess_run_outputs()` 归档 browser history 并清理 evidence。
3. 后端调用 map builder 生成 `walkthrough_map.json`。
4. `_refresh_artifacts()` 注册 map artifact。
5. terminal event 的 artifact_ids 包含 `art_walkthrough_map`。

原因：

- map builder 需要使用已归档、已脱敏、路径已安全化的 evidence/history/screenshot。
- 这样 CLI 原有核心 artifact 不受影响。
- 历史 run 可通过同一个 builder 重建。

### 5.4 生成器职责

建议新增纯函数式生成器，例如：

```text
src/prodwalk/agents/map_builder.py
```

或后端专属：

```text
src/prodwalk/server/map_builder.py
```

推荐放在 `src/prodwalk/agents/map_builder.py`，因为 map 是 run artifact，不只是 API projection。生成器保持无副作用，文件读写由 runtime 负责。

核心步骤：

1. 读取 `evidence.json`。
2. 读取 `artifacts.json` 或动态 `_build_artifacts()` 得到截图和 browser history artifact。
3. 从 `results[].steps[]` 构建 `PageVisit[]`。
4. 如果 browser history 存在，补充每步 title、action、screenshot_path、extracted_content。
5. 对 URL 做 canonicalization。
6. 合并相同页面为 `PageNode`。
7. 从相邻 visit 构建 `PageEdge`。
8. 从 browser_run final summary、step summary、raw `analyses/findings/review_notes` 抽取 `PageInsight`。
9. 把截图 artifact 关联到节点。
10. 生成 warnings 和 confidence。

### 5.5 URL 去重与动态路由

URL 归一策略：

- host 小写。
- 去掉默认端口。
- route 保留大小写时要谨慎；一般 path 可原样保留，display name 再格式化。
- 默认去掉 hash；但 SPA 如果 hash 形如 `#/settings`，应把 hash route 纳入 canonical route。
- query 默认忽略 tracking 参数：`utm_*`、`fbclid`、`gclid`、`session`、`token`、`code` 等。
- 业务 query 可保留白名单，例如 `tab`、`status`、`page` 视情况进入 metadata，不默认拆节点。
- 动态 ID 归一为 pattern：数字 ID、UUID、`mcht_*`、`txn_*` 等替换为 `:id` 或 `:merchant_id`。
- node id 使用 `product + normalized_route_pattern` 计算 hash，避免泄露业务 ID。

详情页处理：

- `/transactions/txn_123` 与 `/transactions/txn_456` 合并为 `Transaction Detail`。
- 节点 metadata 保留样例 URL，但不要把大量 ID 都展示为独立节点。
- 如果详情页内容差异明显但 route pattern 相同，MVP 仍合并。

同一页面多次访问：

- 合并为一个节点。
- `visit_count` 递增。
- `first_seen_step` / `last_seen_step` 更新。
- screenshot evidence 保留多张，优先使用最后一张非 loading 状态或第一张有内容截图作为 primary。

### 5.6 特殊页面处理

登录页：

- route 或 title 命中 login/sign-in/auth，标记 `page_type=auth`。
- 如果 run 终止在登录/验证，节点 `status=blocked`。
- 不展示敏感输入内容，不记录 credential。

验证码 / MFA / 人工验证页：

- 标记 `page_type=auth`，`status=blocked`。
- insights 中记录“人工验证阻塞”，来源为 event/evidence。

错误页：

- URL 或 summary 命中 404/500/net::err/error boundary，标记 `page_type=error`。
- edge 保留，帮助 PM 看到断点。

外部链接：

- 如果 host 不属于 product allowed domain，标记 `page_type=external`、`status=external`。
- MVP 不抓外部页面详情，只保留 URL、label、来源节点。

空白页 / loading 页：

- 如果仅出现一次且后续进入正常页面，可不单独建节点，作为 warning 或 screenshot state。
- 如果 run 停在 loading，则建 `unknown/error` 节点并标记 blocked。

### 5.7 后端测试规划

需要覆盖：

- 从真实样例 `runs/run-20260623-190713-568156/evidence.json` 重建 map。
- 没有 browser history 时仅用 `results[].steps[]` 生成 map。
- 同 URL 多次访问合并。
- 动态详情页 ID 归一。
- query 去噪。
- 截图 artifact 关联。
- browser history 缺失或 JSON 损坏时降级。
- 登录/验证码/错误/外部链接分类。
- `GET /api/runs/{run_id}/map` 已存在读取和不存在重建。
- artifact path traversal 不被引入 map 响应。

## 6. 前端改造规划

### 6.1 新增视图

在 `ConsolePage.tsx` 新增 tab：

```ts
type ConsoleView = "dashboard" | "map" | "report" | "evidence" | "history" | "details";
```

建议展示名：

- 中文：`白板`
- 次选：`页面地图`

白板在 run terminal 后可用；如果 map 尚未生成但 evidence 存在，前端请求 `/map` 时后端可 read-through rebuild。

### 6.2 新增组件

建议目录：

```text
apps/web/src/components/whiteboard/
  WalkthroughMapView.tsx
  WhiteboardCanvas.tsx
  PageNodeCard.tsx
  PageDetailPanel.tsx
  PageMapLegend.tsx
  PageMapFilters.tsx
  PageMapEmptyState.tsx
  pageMapLayout.ts
  pageMapUtils.ts
```

组件职责：

- `WalkthroughMapView`: 容器组件，处理 loading/error/empty/selected node。
- `WhiteboardCanvas`: 图谱渲染、pan/zoom、fit view、节点点击。
- `PageNodeCard`: 节点视觉，展示页面名、类型、状态、截图缩略图/截图数量。
- `PageDetailPanel`: 页面详情，展示 URL、用途、关键功能、控件、问题、观察、截图、evidence links。
- `ScreenshotPreview`: 复用现有 `components/evidence/ScreenshotPreview.tsx`，不要重复实现图片加载逻辑。
- `PageMapLegend`: 解释颜色和线型。
- `PageMapFilters`: 按 page type、status、scenario、has issue、has screenshot 过滤。
- `PageMapEmptyState`: 无 map、无 evidence、map 重建失败时的状态。

### 6.3 前端数据层

需要更新：

- `apps/web/src/types/contracts.ts`
  - 新增 `PageNode`、`PageEdge`、`PageInsight`、`ScreenshotEvidence`、`WalkthroughMapResponse`。
  - `ArtifactType` 增加 `walkthrough_map`。
- `apps/web/src/api/client.ts`
  - 新增 `normalizeWalkthroughMap()`。
  - 新增 `prodwalkApi.getWalkthroughMap(runId)`。
- `apps/web/src/hooks/useProdwalkConsole.ts`
  - 新增 active/history map state、loading、error。
  - terminal event 或 artifact.created 包含 `art_walkthrough_map` 时加载 map。
  - `loadFinalArtifacts()` 可改名或扩展为 `loadFinalOutputs()`，同时加载 report/evidence/evaluation/map。
- `apps/web/src/mock/*`
  - 新增 mock map，确保 API 不可用时白板也能预览。

### 6.4 UI 行为

白板主视图：

- 左侧或主区域为画布。
- 右侧为节点详情面板；移动端改为下方抽屉式内容。
- 默认选中入口节点或第一个 visited 节点。
- 节点颜色表达状态：visited、blocked、discovered、external、error。
- 节点图标或小标签表达 page type：dashboard/list/detail/settings/form/auth。
- 边标签简短显示目标入口，例如 `Core Metrics`，未知则显示 `跳转`。
- 画布顶部提供轻量工具条：fit view、按状态过滤、按场景过滤。

空状态：

- run 未完成：提示“走查完成后会生成页面地图”。
- 无 evidence：提示“当前 run 没有 evidence.json，无法生成页面地图”。
- map 为空：提示“未识别到可展示页面，可查看证据和 browser history”。
- map 生成失败：展示错误和“查看 evidence”入口。

加载状态：

- skeleton 或简洁 loading，不要做复杂动画。
- 历史 run 切换时清空旧 selected node，避免展示错 run 详情。

截图预览：

- 节点卡片使用 primary screenshot 缩略图，缺失时显示页面类型占位。
- 详情面板显示截图 gallery，点击可打开原 artifact。
- 截图 URL 只使用后端 artifact metadata，不拼本地文件路径。

### 6.5 图谱库评估

候选方案：

| 方案 | 优点 | 缺点 | 适配判断 |
| --- | --- | --- | --- |
| 原生 SVG + React | 无新增依赖、完全可控、适合十几个节点 | pan/zoom/selection/edge routing/fit view 都要自写，后续维护成本高 | 可作为 fallback，不推荐 MVP 主方案 |
| React Flow / `@xyflow/react` | React 生态，节点就是 React 组件，内置 pan/zoom/select/controls，适合产品流程图和白板类 UI | 新增依赖，需要适配 CSS 和节点布局 | 推荐 |
| Cytoscape.js | 图分析能力强，适合大规模网络和算法布局 | 与 React 组件化节点集成不如 React Flow 直观，视觉更偏网络图 | 后续大规模图可考虑，MVP 不推荐 |
| D3 | 极度灵活，适合定制可视化 | 低层 API，React 集成和交互都要写大量胶水代码 | 不推荐 MVP |

推荐方案：使用 React Flow，即当前包名 `@xyflow/react`。官方文档显示其核心 `<ReactFlow />` 负责渲染 nodes/edges 和交互，支持 pan/zoom/select 等白板基础能力；这正好匹配“页面节点 + 跳转连线 + 点击详情”的需求。参考：[React Flow docs](https://reactflow.dev/)、[ReactFlow API](https://reactflow.dev/api-reference/react-flow)。Cytoscape.js 更偏 graph theory / network visualization，适合复杂图分析，参考：[Cytoscape.js docs](https://js.cytoscape.org/)。D3 更适合 bespoke data visualization，参考：[D3 docs](https://d3js.org/)。

MVP 布局策略：

- 不引入 dagre/elk 等额外布局库。
- 后端返回 `depth` 或前端根据边做简单 layered layout。
- 节点数量小于 50 时，按入口到下游的层级横向排列；无法拓扑排序的环路放到同层。
- 后续如果页面数变多，再引入自动布局库。

## 7. MVP 范围

### 7.1 必须做

- 新增 `walkthrough_map.json` artifact。
- 新增 `GET /api/runs/{run_id}/map`。
- 支持历史 run 在 evidence 存在时重建 map。
- 从 `evidence.json` / browser history / screenshot artifacts 生成 visited PageNode。
- 从相邻步骤 URL 变化生成 PageEdge，并标明 inferred confidence。
- PageNode 详情包含名称、URL/route、页面类型、用途简介、关键功能、主要控件、问题、截图、相关 evidence。
- 前端新增“白板”tab。
- 白板可展示节点和连线，点击节点显示详情。
- 白板详情中的截图和 evidence 能跳转或复用现有 evidence/screenshot 能力。
- 有 loading / empty / error 状态。
- 有后端单元测试和前端类型/构建测试。

### 7.2 可以做

- 节点按 scenario 过滤。
- 节点按 page type / status 过滤。
- 画布 fit view、mini controls、图例。
- discovered-but-unvisited 节点，仅在 final summary 明确出现时生成。
- 从 raw `analyses/findings/review_notes` 将问题挂到节点。
- 导出 `walkthrough_map.json` artifact 链接。
- 对每条边展示 occurrence count。

### 7.3 暂不做

- 实时白板更新。
- 用户编辑和持久化布局。
- 多人协作白板。
- 大图自动聚类。
- 跨 run diff。
- 自动 PRD 生成。
- 完整 DOM 爬取和全站链接发现。
- 节点拖拽后保存。
- 图谱搜索高级语法。

## 8. 分阶段开发计划

### Phase 1: 数据模型与 artifact 设计

目标：

- 固化 map schema、artifact 类型、API response contract。

涉及文件：

- `src/prodwalk/models.py`
- `src/prodwalk/server/models.py`
- `apps/web/src/types/contracts.ts`
- `docs/api_event_contract.md`
- `docs/whiteboard_feature_plan.md`

具体任务：

- 定义 `WalkthroughMap`、`PageNode`、`PageEdge`、`PageInsight`、`ScreenshotEvidence` schema。
- 在后端 artifact 类型中预留 `walkthrough_map`。
- 在前端 contract 中加入 map 类型。
- 明确 schema version、字段可选性、confidence、warnings。

输出文件：

- 更新后的类型定义。
- 更新后的 API/contract 文档。

验收标准：

- 类型字段能覆盖本规划第 3 节。
- 不破坏现有 run/report/evidence API。
- 后续 agent 能按 schema 写测试 fixture。

并行 agent 数：

- 1 个后端契约 agent + 1 个前端契约 agent，可并行。

### Phase 2: 后端 map 生成器

目标：

- 从现有 run artifact 生成 `walkthrough_map.json`。

涉及文件：

- `src/prodwalk/agents/map_builder.py` 或 `src/prodwalk/server/map_builder.py`
- `src/prodwalk/server/runtime.py`
- `tests/`
- `runs/` 样例只读使用

具体任务：

- 实现纯函数 `build_walkthrough_map(evidence_payload, artifacts, browser_histories)`.
- 实现 URL canonicalization。
- 实现 visited node 合并。
- 实现 adjacent step edge 推断。
- 实现 screenshot artifact 关联。
- 实现 page type heuristic。
- 生成 warnings 和 confidence。

输出文件：

- map builder 源文件。
- map builder 单元测试。
- 测试 fixture 或 inline fixture。

验收标准：

- 能从最新真实 run 生成至少 10 个节点和 9 条边。
- 没有 browser history 时仍能生成基本节点/边。
- 不输出本地绝对路径和敏感字段。
- 动态详情 URL 可合并。

并行 agent 数：

- 1 个 agent。该阶段内部逻辑耦合较强，不建议拆太碎。

### Phase 3: API 与测试

目标：

- 把 map artifact 接入 runtime、artifact registry 和 HTTP API。

涉及文件：

- `src/prodwalk/server/app.py`
- `src/prodwalk/server/runtime.py`
- `src/prodwalk/server/models.py`
- `tests/test_server.py`
- `tests/test_mvp_pipeline.py`

具体任务：

- 新增 `GET /api/runs/{run_id}/map`。
- run 结束后生成 `walkthrough_map.json`。
- `_build_artifacts()` 注册 `art_walkthrough_map`。
- 历史 run 支持 read-through rebuild。
- terminal artifact_ids 包含 map artifact。
- 增加 API 测试。

输出文件：

- API endpoint。
- runtime 集成。
- 测试覆盖。

验收标准：

- `GET /api/runs/{run_id}/map` 对已有 map 返回 200。
- 对只有 evidence 的历史 run 可自动重建。
- 对无 evidence 的 run 返回 404 `ARTIFACT_NOT_FOUND`。
- `/artifacts` 能看到 `walkthrough_map`。
- 现有测试通过。

并行 agent 数：

- 1 个后端 API agent + 1 个测试 agent，可短并行；合并时需要统一 fixture。

### Phase 4: 前端白板基础视图

目标：

- 在控制台增加白板 tab，展示节点和边。

涉及文件：

- `apps/web/package.json`
- `apps/web/package-lock.json`
- `apps/web/src/pages/ConsolePage.tsx`
- `apps/web/src/hooks/useProdwalkConsole.ts`
- `apps/web/src/api/client.ts`
- `apps/web/src/types/contracts.ts`
- `apps/web/src/components/whiteboard/*`
- `apps/web/src/styles/globals.css`

具体任务：

- 引入 `@xyflow/react`。
- 新增 `prodwalkApi.getWalkthroughMap()`。
- 新增 map state/loading/error。
- 新增 `WalkthroughMapView` 和基础 canvas。
- 将后端 node/edge 转为 React Flow nodes/edges。
- 实现简单 layered layout。
- 点击节点后更新 selected node。

输出文件：

- 白板组件目录。
- API client/contract 更新。
- CSS 更新。
- mock map。

验收标准：

- build 通过。
- API 不可用时 mock 模式仍可打开白板。
- 有 map 时显示节点和边。
- 无 map 时显示清晰空状态。
- 不影响报告、证据、历史、详情 tab。

并行 agent 数：

- 2 个 agent：一个做数据层/状态，一个做 UI 组件。最后由 UI agent 集成。

### Phase 5: 节点详情和截图证据

目标：

- 让白板真正服务 PM 查看页面细节，而不只是图。

涉及文件：

- `apps/web/src/components/whiteboard/PageDetailPanel.tsx`
- `apps/web/src/components/whiteboard/PageNodeCard.tsx`
- `apps/web/src/components/evidence/ScreenshotPreview.tsx`
- `apps/web/src/components/evidence/evidenceFocus.ts`
- `apps/web/src/pages/ConsolePage.tsx`
- `apps/web/src/styles/globals.css`

具体任务：

- 详情面板展示页面名称、URL、类型、用途、关键功能、控件、问题、观察记录。
- 详情面板显示 screenshot gallery。
- 点击 evidence id 跳转到 evidence tab 并 focus 对应证据。
- 点击截图打开 artifact 原图。
- 节点卡片显示截图缩略图和状态。
- 增加过滤器和图例。

输出文件：

- 完整 PageDetailPanel。
- 截图/evidence 联动。
- 白板图例和过滤器。

验收标准：

- 点击任意节点能看到详情。
- 有截图的节点能看到可加载图片。
- evidence 跳转可用。
- 断图、无图、artifact 404 有降级状态。
- 移动端详情不遮挡画布内容。

并行 agent 数：

- 2 个 agent：一个做详情/证据联动，一个做视觉和响应式 polish。

### Phase 6: 真实 run 验证与体验优化

目标：

- 用真实 run 验证 map 准确性、可读性和 PM 可用性。

涉及文件：

- `runs/` 样例只读
- `tests/`
- `apps/web/src/styles/globals.css`
- `docs/handoffs/*` 可选新增交接文档

具体任务：

- 用 `runs/run-20260623-190713-568156` 验证节点/边。
- 用 mock run、blocked run、无截图 run 验证空状态。
- 检查 URL 去重和动态详情页归一。
- 检查页面类型和名称是否可理解。
- 调整布局密度、节点尺寸、详情面板信息顺序。
- 运行前后端测试和前端 build。

输出文件：

- QA 记录。
- 必要的 bug fix。
- 可选 handoff 文档。

验收标准：

- 真实 Clink UAT run 能显示主路径：Analytics -> Core Metrics -> Transactions -> Balances -> Customers -> Subscriptions -> Products -> Developers -> Settings。
- 白板第一屏能读懂，不需要 PM 先读日志。
- 节点详情截图可用。
- 主要浏览器尺寸下没有文本重叠。
- 所有新增测试和现有测试通过。

并行 agent 数：

- 1 个 Integration QA agent + 1 个 UI polish agent，可并行。

## 9. 风险与边界

### 9.1 browser-use 跳转关系可能不完整

风险：

- browser-use history 记录了相邻状态，但不一定记录“哪个 DOM 控件导致跳转”。
- 某些 URL 变化发生在 wait 之后，实际触发动作可能在前一步。
- 自动 redirect、SPA route update、后台刷新会让边的因果关系变模糊。

应对：

- 边保留 `confidence` 和 `kind=inferred`。
- `metadata.inferred_reason` 说明推断来源。
- UI 上不要把所有边都表达为确定点击关系。
- 后续增强 walker，保存 click target role/name。

### 9.2 单页应用 URL 不变但页面内容变化

风险：

- SPA 可能通过 tab、modal、drawer 改变主要页面内容，但 URL 不变。
- 如果只按 URL 建节点，会漏掉关键功能表面。

应对：

- MVP 先按 URL/route 为主。
- 当 URL 不变但 title、active nav、main heading、step summary 明显变化时，可在 metadata 中记录 surface，但不默认拆节点。
- 后续新增 `surface_key`：route + active nav + heading。

### 9.3 页面节点去重困难

风险：

- 动态 ID、query、hash、分页、筛选会产生大量伪节点。
- 过度合并又会把真实不同页面混成一个节点。

应对：

- MVP 采用保守归一：合并明显 ID，不合并不同 path。
- 保留 raw_urls 供详情查看。
- warnings 中记录合并数量和低置信度节点。
- 后续引入产品可配置 route patterns。

### 9.4 截图和页面节点关联

风险：

- screenshot_path 可能是上一状态或下一状态截图。
- loading 截图可能被选为 primary。
- 历史 run 截图可能缺失。

应对：

- 先按 step_index 和 URL 关联。
- primary screenshot 选择同节点最后一张非空 artifact；后续可加入视觉/尺寸检查。
- 缺失截图不阻塞节点生成。
- UI 明确显示“无截图证据”。

### 9.5 页面用途自动总结可能不准确

风险：

- `final_output` 是自然语言或 JSON-like 文本，不是强 schema。
- LLM summary 可能把多个页面内容混在一起。

应对：

- 用 `confidence` 标记。
- purpose fallback 为 route/title 的中性描述。
- 问题和功能点必须保留 evidence_ids。
- 不让 UI 把低置信度总结表现为确定事实。

### 9.6 白板太复杂导致 PM 看不懂

风险：

- 节点太多、边太多、颜色太多会变成工程调试图。

应对：

- 默认只显示 visited 主路径，discovered/external 可过滤打开。
- 节点文案短，详情放侧栏。
- 图例控制在 4-5 种状态。
- 不使用力导向乱散布局；用层级布局。
- 第一版不追求炫技，只追求可读、可解释、可回到证据。

### 9.7 安全边界

风险：

- raw evidence/browser history 可能包含本地路径、profile 路径、storage state、secret-like 字段。

应对：

- map builder 只读 runtime 已 postprocess 的 artifact。
- 响应里只返回 run-relative path 和 API URL。
- 沿用 `_sanitize_evidence_data()` 和 artifact containment 规则。
- 测试覆盖本地绝对路径不会进入 map。

## 10. 后续开发 agent 提示词

### 10.1 Backend Map Artifact Agent

```text
你是 Backend Map Artifact Agent，工作目录是 D:\Clink_intern\Agent_explore。

目标：
实现走查结束后的页面关系白板后端 artifact 和 API，不做前端 UI。

必须先阅读：
- docs/whiteboard_feature_plan.md
- src/prodwalk/server/app.py
- src/prodwalk/server/runtime.py
- src/prodwalk/server/models.py
- src/prodwalk/agents/director.py
- src/prodwalk/agents/walker.py
- src/prodwalk/agents/evidence.py
- src/prodwalk/models.py
- tests/test_server.py
- tests/test_mvp_pipeline.py
- runs/run-20260623-190713-568156/evidence.json
- runs/run-20260623-190713-568156/browser-history/*.json
- runs/run-20260623-190713-568156/artifacts.json

任务：
1. 新增 WalkthroughMap 生成器，优先放在 src/prodwalk/agents/map_builder.py，保持纯函数为主。
2. 从 evidence.json、browser-history、artifacts 构建 PageNode、PageEdge、PageInsight、ScreenshotEvidence。
3. 实现 URL canonicalization：去 tracking query、合并动态 ID、保留 hash route。
4. 从相邻 walkthrough steps 推断边，低置信度边标记 kind=inferred 并写 metadata.inferred_reason。
5. 关联 screenshot artifact，只输出 artifact id、run-relative path、content_url/screenshot_url，不输出本地绝对路径。
6. 在 run 完成后生成 runs/run-*/walkthrough_map.json。
7. 在 _build_artifacts() 注册 art_walkthrough_map，type=walkthrough_map。
8. 新增 GET /api/runs/{run_id}/map：已有则读取，不存在但 evidence 存在则重建。
9. 支持历史 run 重建。
10. 增加后端测试，覆盖真实样例、无 browser history、动态路由、截图关联、无 evidence 404、敏感路径不泄露。

约束：
- 不改现有 report/evidence/evaluation 行为，除非为了注册新 artifact 必须触碰 runtime。
- 不引入数据库。
- 不暴露 credential、storage state、user data dir、token、password、本地绝对截图路径。
- 不实现前端。

验收：
- pytest 通过。
- GET /api/runs/{run_id}/map 返回 schema_version=1.0。
- 最新真实 run 可生成清晰节点和边。
- /api/runs/{run_id}/artifacts 包含 walkthrough_map。
```

### 10.2 Frontend Whiteboard UI Agent

```text
你是 Frontend Whiteboard UI Agent，工作目录是 D:\Clink_intern\Agent_explore。

目标：
在现有 React 控制台中新增“白板 / 页面地图”视图，展示后端 WalkthroughMap，并支持点击节点查看页面详情。

必须先阅读：
- docs/whiteboard_feature_plan.md
- apps/web/package.json
- apps/web/src/pages/ConsolePage.tsx
- apps/web/src/hooks/useProdwalkConsole.ts
- apps/web/src/api/client.ts
- apps/web/src/types/contracts.ts
- apps/web/src/styles/globals.css
- apps/web/src/components/evidence/ScreenshotPreview.tsx
- apps/web/src/components/evidence/evidenceFocus.ts
- apps/web/src/components/common/EmptyState.tsx
- apps/web/src/components/common/ErrorState.tsx
- apps/web/src/mock/*

任务：
1. 在 contracts.ts 增加 PageNode、PageEdge、PageInsight、ScreenshotEvidence、WalkthroughMapResponse 类型。
2. 在 client.ts 增加 normalizeWalkthroughMap() 和 prodwalkApi.getWalkthroughMap(runId)。
3. 在 useProdwalkConsole.ts 增加 active/history map state、loading、error，并在 run terminal 后加载 map。
4. 在 ConsolePage.tsx 新增 map tab。
5. 新增 apps/web/src/components/whiteboard/ 组件：
   - WalkthroughMapView
   - WhiteboardCanvas
   - PageNodeCard
   - PageDetailPanel
   - PageMapLegend
   - PageMapFilters
   - pageMapLayout.ts
6. 推荐引入 @xyflow/react，使用 React Flow 渲染节点和边；布局先用简单 layered layout，不额外引入 dagre/elk。
7. 节点点击后右侧展示页面详情：页面名、URL、route、页面类型、用途、关键功能、控件、问题、观察、截图、evidence links。
8. 复用现有截图预览/ArtifactLink 能力，不拼本地文件路径。
9. 增加 mock map，确保 API 不可用时也能预览白板。
10. 补齐 loading、empty、error、no screenshot、broken screenshot 状态。

设计约束：
- UI 面向产品经理，不做工程调试图。
- 克制、清晰、可读，节点不要过大，不做复杂动画。
- 不使用深色炫技画布，不做 3D。
- 移动端详情面板不能遮挡或挤爆内容。
- 不破坏 report/evidence/history/details 现有 tab。

验收：
- npm run build 通过。
- mock 模式可打开白板。
- 有 map 数据时能看到节点、边和详情。
- 无 map 或请求失败时有清晰状态。
- 点击 evidence 能跳到证据视图或触发现有 focus 机制。
```

### 10.3 Integration QA Agent

```text
你是 Integration QA Agent，工作目录是 D:\Clink_intern\Agent_explore。

目标：
验证页面关系白板端到端可用，重点检查真实 run、历史 run、截图、证据跳转和 PM 可读性。

必须先阅读：
- docs/whiteboard_feature_plan.md
- src/prodwalk/server/app.py
- src/prodwalk/server/runtime.py
- apps/web/src/pages/ConsolePage.tsx
- apps/web/src/hooks/useProdwalkConsole.ts
- apps/web/src/components/whiteboard/*
- runs/run-20260623-190713-568156/*
- tests/

任务：
1. 运行后端测试，确认新增 map 测试和既有测试全部通过。
2. 运行前端 build，确认 TypeScript 和 Vite build 通过。
3. 启动 FastAPI 和前端 dev server，用真实历史 run 验证 /api/runs/{run_id}/map。
4. 检查真实 Clink UAT run 的主路径是否可读：
   Analytics -> Core Metrics -> Transactions -> Balances -> Customers -> Subscriptions -> Products -> Developers -> Settings。
5. 检查节点详情：
   - URL/route 是否正确。
   - page_type 是否合理。
   - screenshot 是否加载。
   - evidence link 是否可用。
   - issues/observations 是否有 evidence 支撑。
6. 检查边：
   - 边数量是否与 URL 变化大体一致。
   - wait 导致的 URL 变化是否标记低置信度或 inferred。
   - 动态详情页 ID 是否合并。
7. 检查特殊状态：
   - 无 evidence run。
   - 无 browser history run。
   - 无截图 run。
   - blocked/auth/error/external 节点。
8. 用 Playwright 或浏览器截图检查 desktop/mobile 主要断点，确认没有文本重叠。
9. 输出 QA 记录和发现的问题；能修的小问题直接修，涉及产品取舍的问题列为 follow-up。

约束：
- 不重构无关代码。
- 不删除历史 run artifact。
- 不修改业务走查逻辑。
- 不把本地绝对路径暴露到前端。

验收：
- 测试命令和 build 命令均通过，或明确记录失败原因。
- 白板在真实 run 上可用。
- PM 不看日志也能理解主页面结构。
- 所有发现的问题有文件/行为定位。
```

### 10.4 Optional Walker Instrumentation Agent

```text
你是 Optional Walker Instrumentation Agent，工作目录是 D:\Clink_intern\Agent_explore。

目标：
在不改变现有走查语义的前提下，增强未来白板所需的页面采集质量。只有在 Backend Map Artifact 和 Frontend UI MVP 完成后再执行。

必须先阅读：
- docs/whiteboard_feature_plan.md
- src/prodwalk/agents/walker.py
- src/prodwalk/agents/director.py
- src/prodwalk/events.py
- src/prodwalk/models.py

任务：
1. 评估 browser-use history 是否可稳定提取 click target role/name。
2. 如果可行，在 BrowserUseLocalWalker._extract_observations() 中新增非敏感字段：
   - page_title
   - action_target_label
   - action_target_role
   - main_heading
   - active_nav_label
3. 不采集 input value、token、credential、storage state。
4. 保持旧 evidence schema 兼容。
5. 增加测试验证新增字段不会包含敏感信息。

约束：
- 不影响 browser-use 正常运行。
- 不改变 task prompt 的核心目标。
- 不为了白板引入完整 DOM dump。

验收：
- 新字段能被 map builder 消费但不是必需。
- 旧 run 仍可重建 map。
- 敏感字段测试通过。
```
