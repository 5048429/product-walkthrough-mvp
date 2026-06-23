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
  sourceLabel: string | null;
}

interface MarkdownSection {
  heading: string;
  lines: string[];
}

const blockedStatuses = new Set(["blocked", "awaiting_verification", "waiting", "friction"]);
const failedStatuses = new Set(["failed", "timeout", "canceled", "cancelled", "error"]);
const imageExtensions = /\.(?:png|jpe?g|webp|gif|bmp)$/i;
const longTextLimit = 180;

function inferStatus(report: ReportResponse | null, status?: ConsoleStatus): ConsoleStatus {
  if (status) {
    return status;
  }

  return report?.markdown.trim() ? "done" : "idle";
}

function formatScore(value: number): string {
  return value <= 1 ? `${Math.round(value * 100)}%` : String(value);
}

function scoreLabel(key: string): string | null {
  const normalized = key.toLowerCase();
  const labels: Record<string, string> = {
    accuracy: "结论准确性",
    completeness: "覆盖完整度",
    evidence_quality: "线索质量",
    clarity: "表达清晰度",
    overall_score: "总体评分",
    relevance: "相关性",
    usefulness: "可执行性",
  };

  if (/scenario_id|artifact|markdown|report\.md|evaluation\.json|run_id|evidence_count/.test(normalized)) {
    return null;
  }

  return labels[normalized] ?? key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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

function truncateText(value: string, limit = longTextLimit): string {
  if (value.length <= limit) {
    return value;
  }

  return `${value.slice(0, Math.max(0, limit - 1)).trim()}…`;
}

function shortPageLabel(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = new URL(value);
    const pathParts = parsed.pathname.split("/").filter(Boolean);
    const lastPart = pathParts[pathParts.length - 1]?.replace(/[-_]+/g, " ");
    const pageName = lastPart ? ` · ${truncateText(lastPart, 28)}` : "";

    return `页面 ${parsed.hostname}${pageName}`;
  } catch {
    return null;
  }
}

function cleanUserFacingText(value: string, fallback = ""): string {
  const cleaned = stripInlineMarkdown(value)
    .replace(/\bscenario_id\s*[:：=]\s*[\w.-]+/gi, "对应场景")
    .replace(/\boverall_score\b/gi, "总体评分")
    .replace(/\bevidence_count\b/gi, "证据数量")
    .replace(/\breport\.md\b/gi, "原始报告")
    .replace(/\bevaluation\.json\b/gi, "评估信息")
    .replace(/\bMarkdown\b/g, "原文")
    .replace(/\bartifacts?\b/gi, "文件")
    .replace(/https?:\/\/\S+/gi, "相关页面")
    .replace(/[A-Za-z]:[\\/][^\s，。；、)）]+/g, "本地文件")
    .replace(/(?:^|\s)[./\\][^\s，。；、)）]+/g, " 本地文件")
    .replace(/\s+/g, " ")
    .trim();

  return cleaned || fallback;
}

function oneSentence(value: string, fallback: string): string {
  const cleaned = cleanUserFacingText(value, fallback);
  const sentence = /^(.+?[。！？!?])(?:\s|$)/.exec(cleaned)?.[1] ?? cleaned;

  return truncateText(sentence, 160);
}

function cleanInsightItems(items: string[], limit: number): string[] {
  const seen = new Set<string>();
  const cleanedItems: string[] = [];

  for (const item of items) {
    const cleaned = truncateText(cleanUserFacingText(item), longTextLimit);

    if (!cleaned || seen.has(cleaned)) {
      continue;
    }

    seen.add(cleaned);
    cleanedItems.push(cleaned);

    if (cleanedItems.length >= limit) {
      break;
    }
  }

  return cleanedItems;
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

function readableScreenshotTitle(item: EvidenceItem, artifact: Artifact): string {
  const candidates = [item.scenario_title, item.title, item.product, artifact.title];

  for (const candidate of candidates) {
    const cleaned = cleanUserFacingText(candidate ?? "");

    if (cleaned && !imageExtensions.test(cleaned) && !/^[\w.-]{18,}$/.test(cleaned)) {
      return truncateText(cleaned, 56);
    }
  }

  return "关键页面截图";
}

function readableScreenshotSummary(item: EvidenceItem): string {
  const candidates = [item.summary, item.scenario_title, shortPageLabel(item.url), item.product];

  for (const candidate of candidates) {
    const cleaned = cleanUserFacingText(candidate ?? "");

    if (cleaned) {
      return truncateText(cleaned, 96);
    }
  }

  return "本次走查保留的页面画面。";
}

function readableArtifactScreenshot(artifact: Artifact): Pick<ReportScreenshot, "title" | "summary" | "sourceLabel"> {
  const title = cleanUserFacingText(artifact.title);
  const fileTitle = artifact.path
    .split(/[\\/]/)
    .pop()
    ?.replace(/\.[^.]+$/, "")
    .replace(/[-_]+/g, " ");

  return {
    title: truncateText(title || cleanUserFacingText(fileTitle ?? "") || "关键页面截图", 56),
    summary: "本次走查保留的页面画面。",
    sourceLabel: null,
  };
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
        title: readableScreenshotTitle(item, artifact),
        summary: readableScreenshotSummary(item),
        url: getArtifactUrl(artifact),
        sourceLabel: shortPageLabel(item.url),
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
    const screenshotCopy = readableArtifactScreenshot(artifact);
    screenshots.push({
      id: artifact.id,
      title: screenshotCopy.title,
      summary: screenshotCopy.summary,
      url: getArtifactUrl(artifact),
      sourceLabel: screenshotCopy.sourceLabel,
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

  return oneSentence(summary[0] ?? markdownLines(markdown)[0] ?? "", "报告已生成，可先查看主要结论和关键截图。");
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
        ? ["任务被阻塞，建议先复核已保留的线索，再决定是否重试。"]
        : status === "failed"
          ? ["任务未干净完成，报告中的结论应结合已有证据复核。"]
          : [];

  return cleanInsightItems([...sectionItems, ...evidenceItems, ...statusItems], limit);
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
    findings: cleanInsightItems(findingsFromReport.length ? findingsFromReport : evidenceFindings, 4),
    recommendations: cleanInsightItems(
      recommendations.length ? recommendations : (evaluationNotes?.filter(Boolean) ?? []),
      4,
    ),
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
      title: "报告暂时不可用",
      message: "这次结果还没有整理成可查看的报告，请稍后刷新或重试。",
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
      message: "结果还在整理中，完成后这里会自动展示。",
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
      message: "任务在整理结果前被阻塞，已有线索仍可复核。",
      tone: "blocked",
    };
  }

  if (status === "failed" && !hasMarkdown) {
    return {
      kind: "error",
      title: "报告读取失败",
      message: "任务失败时还没有可读取的报告。",
      tone: "failed",
    };
  }

  if (!hasMarkdown) {
    return {
      kind: "empty",
      title: "报告暂无正文",
      message: "当前任务已有报告记录，但正文还没有内容。",
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
  link.download = "原始报告.md";
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
  const scoreEntries = useMemo(
    () =>
      Object.entries(report?.evaluation?.scores ?? {})
        .map(([key, value]) => ({ label: scoreLabel(key), value }))
        .filter((entry): entry is { label: string; value: number } => Boolean(entry.label)),
    [report?.evaluation?.scores],
  );

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
          <p>{report ? "先看结论、建议动作和关键截图。" : "尚未选择报告"}</p>
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

      {loading && !hasMarkdown ? <EmptyState title="正在读取报告" message="正在整理最新结论，请稍候。" /> : null}
      {!loading && state.kind === "empty" ? <EmptyState title={state.title} message={state.message} /> : null}
      {state.kind === "error" ? (
        <ErrorState title={state.title} message={state.message} tone={state.tone} />
      ) : null}
      {evaluationError && hasMarkdown ? (
        <ErrorState
          title="评估信息暂不可用"
          message="不影响查看报告结论和原始报告全文。"
          compact
        />
      ) : null}
      {error && hasMarkdown ? (
        <ErrorState
          title="报告刷新异常"
          message="当前仍显示已缓存或部分生成的报告；最新结果稍后可再次刷新。"
          compact
        />
      ) : null}

      {hasMarkdown ? (
        <div className="report-layout">
          <article className="markdown-preview" aria-label="报告内容">
            <section className="report-outcome" aria-label="报告结论摘要">
              <div className="report-outcome-main">
                <div className="section-title">总体结论</div>
                <h3>{insights.summary}</h3>
              </div>
            </section>

            <section className="report-insight-grid" aria-label="关键结论">
              <article className="report-insight-card">
                <div className="section-title">主要发现</div>
                {renderInsightList(insights.findings, "报告暂未提炼出独立发现，可在原始报告全文中查看。")}
              </article>
              <article className="report-insight-card">
                <div className="section-title">建议动作</div>
                {renderInsightList(insights.recommendations, "暂无明确建议动作。")}
              </article>
              <article className="report-insight-card report-insight-card-risk">
                <div className="section-title">风险 / 需跟进</div>
                {renderInsightList(insights.risks, "暂无明确风险项。")}
              </article>
            </section>

            <section className="report-screenshot-strip" aria-label="报告关键截图">
              <div className="report-section-heading">
                <div>
                  <div className="section-title">关键截图</div>
                  <strong>快速确认对应页面画面</strong>
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
                        {screenshot.sourceLabel ? <small>{screenshot.sourceLabel}</small> : null}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ) : (
                <EmptyState title="暂无关键截图" message="如果本次走查保存了页面截图，会显示在这里。" compact />
              )}
            </section>

            <details className="report-markdown-details">
              <summary>
                <strong>原始报告全文</strong>
                <span>保留完整描述，默认收起</span>
              </summary>
              <div className="report-markdown-body">
                {loading ? (
                  <div className="partial-banner partial-banner-running">
                    <strong>正在刷新报告</strong>
                    <span>正在读取最新结果。</span>
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

            <details className="report-advanced-details">
              <summary>
                <strong>高级信息</strong>
                <span>提纲和评估细项</span>
              </summary>
              <div className="report-advanced-grid">
                <section className="evaluation-panel">
                  <div className="section-title">报告提纲</div>
                  {headings.length > 0 ? (
                    <ol className="outline-list">
                      {headings.map((heading) => (
                        <li key={heading.id} className={`outline-level-${heading.level}`}>
                          <a href={`#${heading.id}`}>{cleanUserFacingText(heading.text, "报告段落")}</a>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <EmptyState title="暂无提纲" message="原始报告里暂时没有可提取的标题。" compact />
                  )}
                </section>

                <section className="evaluation-panel">
                  <div className="section-title evaluation-title">评估细项</div>
                  {report?.evaluation ? (
                    <>
                      <div className="score-display">{formatScore(report.evaluation.overall_score)}</div>
                      {scoreEntries.length > 0 ? (
                        <dl className="score-list">
                          {scoreEntries.map((entry) => (
                            <div key={entry.label}>
                              <dt>{entry.label}</dt>
                              <dd>{formatScore(entry.value)}</dd>
                            </div>
                          ))}
                        </dl>
                      ) : null}
                      <ul className="notes-list">
                        {report.evaluation.notes.map((note) => (
                          <li key={note}>{cleanUserFacingText(note)}</li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <EmptyState title="评估信息暂不可用" message="仍可查看报告结论和原始报告全文。" compact />
                  )}
                </section>
              </div>
            </details>
          </article>
        </div>
      ) : null}
    </section>
  );
}
