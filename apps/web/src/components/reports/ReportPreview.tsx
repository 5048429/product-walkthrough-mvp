import { useMemo, useState } from "react";
import { backendUrl, runArtifactContentUrl } from "../../api/paths";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { ReportMarkdown, extractHeadings } from "./ReportMarkdown";
import { ReportToolbar } from "./ReportToolbar";
import type { Artifact, ConsoleStatus, EvidenceItem, EvidenceResponse, ReportResponse } from "../../types/contracts";

interface ReportPreviewProps {
  report: ReportResponse | null;
  evidence?: EvidenceResponse | null;
  artifacts?: Artifact[];
  status?: ConsoleStatus;
  error?: string | null;
  evaluationError?: string | null;
  loading?: boolean;
}

interface ReportScreenshot {
  id: string;
  title: string;
  summary: string;
  url: string;
  sourceUrl: string | null;
}

interface MarkdownSection {
  heading: string;
  lines: string[];
}

interface CompletionSummary {
  total: number;
  completed: number;
  blocked: number;
  failed: number;
  running: number;
  label: string;
}

const completedStatuses = new Set(["completed", "succeeded", "done", "passed"]);
const runningStatuses = new Set(["queued", "starting", "running", "finalizing", "pending"]);
const blockedStatuses = new Set(["blocked", "awaiting_verification", "waiting", "friction"]);
const failedStatuses = new Set(["failed", "timeout", "canceled", "cancelled", "error"]);
const imageExtensions = /\.(?:png|jpe?g|webp|gif|bmp)$/i;

function inferStatus(report: ReportResponse | null, status?: ConsoleStatus): ConsoleStatus {
  if (status) {
    return status;
  }

  return report?.markdown.trim() ? "done" : "idle";
}

function formatScore(value: number): string {
  return value <= 1 ? `${Math.round(value * 100)}%` : String(value);
}

function mergeArtifacts(...artifactGroups: Array<Artifact[] | undefined>): Artifact[] {
  const byId = new Map<string, Artifact>();

  for (const group of artifactGroups) {
    for (const artifact of group ?? []) {
      byId.set(artifact.id, artifact);
    }
  }

  return Array.from(byId.values());
}

function normalizeHeading(value: string): string {
  return value
    .toLowerCase()
    .replace(/[`*_~[\]():：.。!！?？]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function stripInlineMarkdown(value: string): string {
  return value
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[`*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function parseMarkdownSections(markdown: string): MarkdownSection[] {
  const sections: MarkdownSection[] = [];
  let current: MarkdownSection | null = null;

  for (const line of markdown.replace(/\r\n?/g, "\n").split("\n")) {
    const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line.trim());

    if (heading) {
      current = { heading: heading[2].trim(), lines: [] };
      sections.push(current);
      continue;
    }

    current?.lines.push(line);
  }

  return sections;
}

function extractItemsFromLines(lines: string[], limit: number): string[] {
  const items: string[] = [];
  let paragraph = "";

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line || line.startsWith("```") || line.startsWith("|")) {
      if (paragraph) {
        items.push(stripInlineMarkdown(paragraph));
        paragraph = "";
      }
      continue;
    }

    const listMatch = /^(?:[-*+]\s+|\d+[.)]\s+)(.+)$/.exec(line);

    if (listMatch) {
      if (paragraph) {
        items.push(stripInlineMarkdown(paragraph));
        paragraph = "";
      }
      items.push(stripInlineMarkdown(listMatch[1]));
      continue;
    }

    paragraph = paragraph ? `${paragraph} ${line}` : line;

    if (/[。.!?？]$/.test(line)) {
      items.push(stripInlineMarkdown(paragraph));
      paragraph = "";
    }

    if (items.length >= limit) {
      break;
    }
  }

  if (paragraph && items.length < limit) {
    items.push(stripInlineMarkdown(paragraph));
  }

  return items.filter(Boolean).slice(0, limit);
}

function findSection(sections: MarkdownSection[], keywords: string[]): MarkdownSection | null {
  return (
    sections.find((section) => {
      const heading = normalizeHeading(section.heading);
      return keywords.some((keyword) => heading.includes(keyword));
    }) ?? null
  );
}

function getSectionItems(sections: MarkdownSection[], keywords: string[], limit: number): string[] {
  const section = findSection(sections, keywords);
  return section ? extractItemsFromLines(section.lines, limit) : [];
}

function summarizeCompletion(evidence: EvidenceResponse | null | undefined, status: ConsoleStatus): CompletionSummary {
  const results = evidence?.results ?? [];

  if (results.length === 0) {
    return {
      total: 0,
      completed: status === "done" ? 1 : 0,
      blocked: blockedStatuses.has(status) ? 1 : 0,
      failed: failedStatuses.has(status) ? 1 : 0,
      running: runningStatuses.has(status) ? 1 : 0,
      label: status === "done" ? "报告已完成" : statusCopy(status),
    };
  }

  let completed = 0;
  let blocked = 0;
  let failed = 0;
  let running = 0;

  for (const result of results) {
    const resultStatus = result.status.toLowerCase();

    if (completedStatuses.has(resultStatus)) {
      completed += 1;
    } else if (blockedStatuses.has(resultStatus)) {
      blocked += 1;
    } else if (failedStatuses.has(resultStatus)) {
      failed += 1;
    } else if (runningStatuses.has(resultStatus)) {
      running += 1;
    }
  }

  return {
    total: results.length,
    completed,
    blocked,
    failed,
    running,
    label: `${completed}/${results.length} 个场景完成`,
  };
}

function completionPercent(summary: CompletionSummary): number {
  if (summary.total === 0) {
    return summary.completed > 0 ? 100 : 0;
  }

  return Math.round((summary.completed / summary.total) * 100);
}

function statusCopy(status: ConsoleStatus): string {
  switch (status) {
    case "done":
      return "已完成";
    case "running":
      return "正在生成";
    case "awaiting_verification":
      return "暂停等待验证";
    case "blocked":
      return "受阻";
    case "failed":
      return "失败";
    case "timeout":
      return "超时";
    default:
      return "未开始";
  }
}

function metadataString(artifact: Artifact, keys: string[]): string | null {
  for (const key of keys) {
    const value = artifact.metadata[key];

    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }

  return null;
}

function getArtifactUrl(artifact: Artifact): string {
  const metadataUrl = metadataString(artifact, ["screenshot_url", "path_url", "content_url"]);

  if (metadataUrl) {
    return backendUrl(metadataUrl);
  }

  return runArtifactContentUrl(artifact.run_id, artifact.id);
}

function isImageArtifact(artifact: Artifact): boolean {
  return artifact.type === "screenshot" || artifact.media_type.toLowerCase().startsWith("image/") || imageExtensions.test(artifact.path);
}

function getScreenshotArtifactIds(item: EvidenceItem): string[] {
  if (item.screenshot_artifact_ids?.length) {
    return item.screenshot_artifact_ids;
  }

  return item.screenshot_artifact_id ? [item.screenshot_artifact_id] : [];
}

function collectReportScreenshots(evidence: EvidenceResponse | null | undefined, artifacts: Artifact[], limit = 6): ReportScreenshot[] {
  const imageArtifacts = new Map(artifacts.filter(isImageArtifact).map((artifact) => [artifact.id, artifact]));
  const screenshots: ReportScreenshot[] = [];
  const seen = new Set<string>();

  for (const item of evidence?.evidence ?? []) {
    for (const artifactId of getScreenshotArtifactIds(item)) {
      const artifact = imageArtifacts.get(artifactId);

      if (!artifact || seen.has(artifact.id)) {
        continue;
      }

      seen.add(artifact.id);
      screenshots.push({
        id: artifact.id,
        title: item.title || artifact.title,
        summary: item.summary || artifact.title,
        url: getArtifactUrl(artifact),
        sourceUrl: item.url,
      });

      if (screenshots.length >= limit) {
        return screenshots;
      }
    }
  }

  for (const artifact of artifacts.filter(isImageArtifact)) {
    if (seen.has(artifact.id)) {
      continue;
    }

    seen.add(artifact.id);
    screenshots.push({
      id: artifact.id,
      title: artifact.title,
      summary: artifact.path,
      url: getArtifactUrl(artifact),
      sourceUrl: null,
    });

    if (screenshots.length >= limit) {
      break;
    }
  }

  return screenshots;
}

function markdownLines(markdown: string): string[] {
  return markdown
    .split(/\r?\n/)
    .map((line) => line.replace(/^#{1,6}\s*/, "").replace(/^[-*]\s*/, "").trim())
    .filter((line) => line && !line.startsWith("```") && !line.startsWith("|"))
    .map(stripInlineMarkdown)
    .filter(Boolean);
}

function getSummaryText(markdown: string, sections: MarkdownSection[]): string {
  const summary = getSectionItems(
    sections,
    ["summary", "executive summary", "结论", "摘要", "概览", "总体", "总结"],
    1,
  );

  return summary[0] ?? markdownLines(markdown)[0] ?? "报告已生成，完整 Markdown 保留在下方。";
}

function getEvidenceStatus(item: EvidenceItem): string {
  if (item.status) {
    return item.status;
  }

  if (item.errors?.length) {
    return "blocked";
  }

  return "completed";
}

function getRiskItems(
  sections: MarkdownSection[],
  evidence: EvidenceResponse | null | undefined,
  status: ConsoleStatus,
  limit: number,
): string[] {
  const sectionItems = getSectionItems(
    sections,
    ["risk", "risks", "follow", "issue", "blocked", "风险", "跟进", "待处理", "阻塞", "问题"],
    limit,
  );
  const evidenceItems =
    evidence?.evidence
      .filter((item) => {
        const itemStatus = getEvidenceStatus(item).toLowerCase();
        return item.errors?.length || blockedStatuses.has(itemStatus) || failedStatuses.has(itemStatus);
      })
      .map((item) => `${item.title}: ${item.errors?.[0] ?? item.summary}`) ?? [];
  const statusItems =
    status === "awaiting_verification"
      ? ["真实浏览器仍在等待人工验证，最终结论可能需要补充确认。"]
      : status === "blocked"
        ? ["任务被阻塞，建议先查看证据和错误信息后再重跑。"]
        : status === "failed"
          ? ["任务未干净完成，报告中的结论应结合已有证据复核。"]
          : [];

  return Array.from(new Set([...sectionItems, ...evidenceItems, ...statusItems])).slice(0, limit);
}

function getReportInsights(
  markdown: string,
  evidence: EvidenceResponse | null | undefined,
  status: ConsoleStatus,
  evaluationNotes: string[] | undefined,
) {
  const sections = parseMarkdownSections(markdown);
  const findingsFromReport = getSectionItems(
    sections,
    ["key findings", "findings", "finding", "主要发现", "关键发现", "发现"],
    4,
  );
  const evidenceFindings =
    evidence?.evidence
      .filter((item) => item.kind === "finding" || item.finding_ids?.length)
      .map((item) => `${item.title}: ${item.summary}`) ?? [];
  const recommendations = getSectionItems(
    sections,
    ["recommendations", "recommendation", "next steps", "建议", "行动建议", "下一步"],
    4,
  );

  return {
    summary: getSummaryText(markdown, sections),
    findings: (findingsFromReport.length ? findingsFromReport : evidenceFindings).slice(0, 4),
    recommendations: recommendations.length ? recommendations : (evaluationNotes?.filter(Boolean) ?? []).slice(0, 3),
    risks: getRiskItems(sections, evidence, status, 4),
  };
}

function renderInsightList(items: string[], fallback: string) {
  if (items.length === 0) {
    return <p className="empty-copy">{fallback}</p>;
  }

  return (
    <ul>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function getReportState(
  status: ConsoleStatus,
  hasMarkdown: boolean,
  error: string | null | undefined,
): { kind: "ready" | "empty" | "error"; title: string; message: string; tone?: "failed" | "blocked" } {
  if (error && !hasMarkdown) {
    return {
      kind: "error",
      title: "报告产物不可用",
      message: error,
      tone: "failed",
    };
  }

  if (status === "idle") {
    return {
      kind: "empty",
      title: "报告尚未就绪",
      message: "请选择或启动一次走查后再查看报告。",
    };
  }

  if (status === "running" && !hasMarkdown) {
    return {
      kind: "empty",
      title: "报告仍在生成",
      message: "报告写入器尚未产出 report.md；产物生成后这里会自动展示。",
    };
  }

  if (status === "awaiting_verification" && !hasMarkdown) {
    return {
      kind: "error",
      title: "报告等待验证",
      message: "真实浏览器仍在等待人工验证确认，最终报告暂未生成。",
      tone: "blocked",
    };
  }

  if (status === "blocked" && !hasMarkdown) {
    return {
      kind: "error",
      title: "报告生成受阻",
      message: "任务在生成 report.md 前被阻塞，已有证据仍可复核。",
      tone: "blocked",
    };
  }

  if (status === "failed" && !hasMarkdown) {
    return {
      kind: "error",
      title: "报告读取失败",
      message: "任务失败时还没有可读取的 Markdown 报告。",
      tone: "failed",
    };
  }

  if (!hasMarkdown) {
    return {
      kind: "empty",
      title: "report.md 为空",
      message: "当前任务返回了报告响应，但 Markdown 正文为空。",
    };
  }

  return {
    kind: "ready",
    title: "",
    message: "",
  };
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back to the legacy selection path below.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "0";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, value.length);

  try {
    const copied = document.execCommand("copy");

    if (!copied) {
      throw new Error("Browser copy command was rejected.");
    }
  } finally {
    document.body.removeChild(textarea);
  }
}

function downloadMarkdown(markdown: string): void {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "report.md";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
}

export function ReportPreview({
  report,
  evidence,
  artifacts,
  status,
  error,
  evaluationError,
  loading = false,
}: ReportPreviewProps) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const markdown = report?.markdown ?? "";
  const hasMarkdown = markdown.trim().length > 0;
  const effectiveStatus = inferStatus(report, status);
  const state = getReportState(effectiveStatus, hasMarkdown, error);
  const headings = useMemo(() => extractHeadings(markdown), [markdown]);
  const resolvedArtifacts = useMemo(
    () => mergeArtifacts(artifacts, report?.artifacts, evidence?.artifacts),
    [artifacts, evidence?.artifacts, report?.artifacts],
  );
  const screenshots = useMemo(
    () => collectReportScreenshots(evidence, resolvedArtifacts),
    [evidence, resolvedArtifacts],
  );
  const insights = useMemo(
    () => getReportInsights(markdown, evidence, effectiveStatus, report?.evaluation?.notes),
    [effectiveStatus, evidence, markdown, report?.evaluation?.notes],
  );
  const completion = useMemo(() => summarizeCompletion(evidence, effectiveStatus), [effectiveStatus, evidence]);
  const completionValue = completionPercent(completion);
  const evidenceCount = evidence?.evidence.length ?? 0;

  async function handleCopyMarkdown() {
    if (!hasMarkdown) {
      return;
    }

    try {
      await copyText(markdown);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }

    window.setTimeout(() => setCopyState("idle"), 1800);
  }

  function handleDownloadMarkdown() {
    if (!hasMarkdown) {
      return;
    }

    downloadMarkdown(markdown);
  }

  return (
    <section className="panel report-panel" aria-labelledby="report-preview-title">
      <div className="panel-header report-header">
        <div>
          <h2 id="report-preview-title">报告结论</h2>
          <p>{report ? `先看结论和截图，完整 Markdown 在下方保留。` : "尚未选择报告"}</p>
        </div>
      </div>

      <ReportToolbar
        report={report}
        artifacts={resolvedArtifacts}
        status={effectiveStatus}
        copyState={copyState}
        onCopyMarkdown={handleCopyMarkdown}
        onDownloadMarkdown={handleDownloadMarkdown}
      />

      {loading && !hasMarkdown ? (
        <EmptyState title="正在读取报告" message="正在从 API 读取 report.md 和 evaluation.json。" />
      ) : null}
      {!loading && state.kind === "empty" ? <EmptyState title={state.title} message={state.message} /> : null}
      {state.kind === "error" ? (
        <ErrorState title={state.title} message={state.message} tone={state.tone} details={error ?? undefined} />
      ) : null}
      {evaluationError && hasMarkdown ? (
        <ErrorState
          title="评分暂不可用"
          message="evaluation.json 缺失或不可读，但 Markdown 报告仍可查看。"
          details={evaluationError}
          compact
        />
      ) : null}
      {error && hasMarkdown ? (
        <ErrorState
          title="报告刷新异常"
          message="当前仍显示已缓存或部分生成的 Markdown 报告，但最新请求返回了错误。"
          details={error}
          compact
        />
      ) : null}

      {hasMarkdown ? (
        <div className="report-layout">
          <article className="markdown-preview" aria-label="Markdown report">
            <section className="report-outcome" aria-label="报告结论摘要">
              <div className="report-outcome-main">
                <div className="section-title">总体结论</div>
                <h3>{insights.summary}</h3>
                <div className="report-progress-card">
                  <div>
                    <span>完成情况</span>
                    <strong>{completion.label}</strong>
                  </div>
                  <div className="report-progress-bar" aria-label={`完成度 ${completionValue}%`}>
                    <span style={{ width: `${completionValue}%` }} />
                  </div>
                </div>
              </div>
              <div className="report-outcome-metrics" aria-label="报告关键指标">
                <div>
                  <span>总体评分</span>
                  <strong>{report?.evaluation ? formatScore(report.evaluation.overall_score) : "待生成"}</strong>
                </div>
                <div>
                  <span>任务状态</span>
                  <strong>{statusCopy(effectiveStatus)}</strong>
                </div>
                <div>
                  <span>证据</span>
                  <strong>{evidenceCount} 条</strong>
                </div>
                <div>
                  <span>截图</span>
                  <strong>{screenshots.length} 张</strong>
                </div>
                <div>
                  <span>风险跟进</span>
                  <strong>{completion.blocked + completion.failed} 项</strong>
                </div>
                <div>
                  <span>进行中</span>
                  <strong>{completion.running} 项</strong>
                </div>
              </div>
            </section>

            <section className="report-insight-grid" aria-label="关键结论">
              <article className="report-insight-card">
                <div className="section-title">主要发现</div>
                {renderInsightList(insights.findings, "报告暂未提炼出独立发现，可在完整 Markdown 中查看原始内容。")}
              </article>
              <article className="report-insight-card">
                <div className="section-title">建议动作</div>
                {renderInsightList(insights.recommendations, "报告暂未写入建议动作。")}
              </article>
              <article className="report-insight-card report-insight-card-risk">
                <div className="section-title">风险 / 需跟进</div>
                {renderInsightList(insights.risks, "暂无明确风险项。")}
              </article>
            </section>

            <section className="report-screenshot-strip" aria-label="报告关键截图">
              <div className="report-section-heading">
                <div>
                  <div className="section-title">关联截图</div>
                  <strong>直接查看页面证据</strong>
                </div>
                <span>{screenshots.length} 张</span>
              </div>
              {screenshots.length ? (
                <div className="report-screenshot-grid">
                  {screenshots.map((screenshot) => (
                    <figure key={screenshot.id} className="report-screenshot-card">
                      <a href={screenshot.url} target="_blank" rel="noreferrer">
                        <img src={screenshot.url} alt={screenshot.title} loading="lazy" />
                      </a>
                      <figcaption>
                        <strong>{screenshot.title}</strong>
                        <span>{screenshot.summary}</span>
                        {screenshot.sourceUrl ? <small>{screenshot.sourceUrl}</small> : null}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ) : (
                <EmptyState title="暂无可预览截图" message="如果 evidence 或 artifacts 写入截图，截图会直接出现在这里。" compact />
              )}
            </section>

            <details className="report-markdown-details">
              <summary>
                <strong>完整 Markdown 报告</strong>
                <span>保留原始过程、证据和建议</span>
              </summary>
              <div className="report-markdown-body">
            {loading ? (
              <div className="partial-banner partial-banner-running">
                <strong>正在刷新报告</strong>
                <span>正在从 API 读取最新 report.md。</span>
              </div>
            ) : null}
            {effectiveStatus === "running" ||
            effectiveStatus === "awaiting_verification" ||
            effectiveStatus === "blocked" ||
            effectiveStatus === "failed" ? (
              <div className={`partial-banner partial-banner-${effectiveStatus}`}>
                <strong>{effectiveStatus === "running" ? "报告仍在生成" : "已保留部分报告"}</strong>
                <span>
                  {effectiveStatus === "running"
                    ? "任务仍在运行；报告生成完成后这里可能继续更新。"
                    : effectiveStatus === "awaiting_verification"
                      ? "浏览器正在等待人工验证，当前报告仍可查看。"
                      : "任务未干净完成，但已生成的报告仍可复核。"}
                </span>
              </div>
            ) : null}
            <ReportMarkdown markdown={markdown} artifacts={resolvedArtifacts} runId={report?.run_id} />
              </div>
            </details>
          </article>

          <aside className="evaluation-panel">
            <div className="section-title">报告目录</div>
            {headings.length > 0 ? (
              <ol className="outline-list">
                {headings.map((heading) => (
                  <li key={heading.id} className={`outline-level-${heading.level}`}>
                    <a href={`#${heading.id}`}>{heading.text}</a>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState title="暂无目录" message="Markdown 中还没有可提取的标题。" compact />
            )}

            <div className="section-title evaluation-title">评分明细</div>
            {report?.evaluation ? (
              <>
                <div className="score-display">{formatScore(report.evaluation.overall_score)}</div>
                <dl className="score-list">
                  {Object.entries(report.evaluation.scores).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{formatScore(value)}</dd>
                    </div>
                  ))}
                </dl>
                <ul className="notes-list">
                  {report.evaluation.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </>
            ) : (
              <EmptyState title="评分暂不可用" message="evaluation.json 缺失时仍可查看 Markdown 报告。" compact />
            )}
          </aside>
        </div>
      ) : null}
    </section>
  );
}
