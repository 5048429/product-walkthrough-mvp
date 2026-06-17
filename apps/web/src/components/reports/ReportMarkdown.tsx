import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { backendUrl, runArtifactContentUrl, runArtifactPathUrl } from "../../api/paths";
import type { Artifact } from "../../types/contracts";

export interface Heading {
  id: string;
  text: string;
  level: number;
}

interface ReportMarkdownProps {
  markdown: string;
  artifacts: Artifact[];
  runId?: string | null;
}

type MarkdownBlock =
  | { type: "heading"; id: string; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; language: string | null; code: string }
  | { type: "table"; headers: string[]; rows: string[][] }
  | { type: "quote"; text: string }
  | { type: "hr" };

type AssetResolver = (target: string) => string | null;

const imageExtensions = /\.(?:png|jpe?g|webp|gif|bmp)$/i;

const styles: Record<string, CSSProperties> = {
  root: {
    display: "grid",
    gap: 12,
    color: "#263243",
    lineHeight: 1.58,
  },
  heading1: {
    margin: "2px 0 4px",
    color: "#111827",
    fontSize: 26,
    lineHeight: 1.2,
  },
  heading2: {
    margin: "16px 0 4px",
    color: "#1d2430",
    fontSize: 20,
    lineHeight: 1.25,
  },
  heading3: {
    margin: "12px 0 2px",
    color: "#263243",
    fontSize: 16,
    lineHeight: 1.3,
  },
  heading4: {
    margin: "10px 0 0",
    color: "#3b4656",
    fontSize: 14,
    lineHeight: 1.35,
  },
  paragraph: {
    margin: 0,
    overflowWrap: "anywhere",
  },
  list: {
    display: "grid",
    gap: 6,
    margin: 0,
    paddingLeft: 22,
  },
  listItem: {
    paddingLeft: 2,
    overflowWrap: "anywhere",
  },
  codeBlock: {
    overflow: "auto",
    margin: 0,
    border: "1px solid var(--line)",
    borderRadius: 8,
    background: "#111827",
    padding: 12,
    color: "#e5edf7",
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, Liberation Mono, monospace",
    fontSize: 12,
    lineHeight: 1.55,
    whiteSpace: "pre",
  },
  inlineCode: {
    border: "1px solid var(--line)",
    borderRadius: 4,
    background: "#ffffff",
    padding: "1px 5px",
    color: "#3b4656",
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, Liberation Mono, monospace",
    fontSize: "0.92em",
  },
  link: {
    color: "var(--blue)",
    fontWeight: 700,
    textDecoration: "none",
  },
  unresolvedLink: {
    borderBottom: "1px dotted var(--line-strong)",
    color: "var(--text-muted)",
  },
  tableWrap: {
    overflowX: "auto",
    border: "1px solid var(--line)",
    borderRadius: 8,
    background: "#ffffff",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  tableCell: {
    borderBottom: "1px solid var(--line)",
    padding: "8px 10px",
    textAlign: "left",
    verticalAlign: "top",
  },
  tableHeader: {
    background: "#eef2f6",
    color: "#1d2430",
    fontWeight: 750,
  },
  quote: {
    margin: 0,
    borderLeft: "3px solid var(--line-strong)",
    background: "#ffffff",
    padding: "8px 10px",
    color: "#3b4656",
  },
  imageShell: {
    display: "block",
    margin: "8px 0",
  },
  image: {
    display: "block",
    maxWidth: "100%",
    maxHeight: 420,
    border: "1px solid var(--line)",
    borderRadius: 8,
    background: "#ffffff",
    objectFit: "contain",
  },
  imageCaption: {
    display: "block",
    marginTop: 4,
    color: "var(--text-muted)",
    fontSize: 12,
  },
  imageFallback: {
    display: "inline-block",
    border: "1px dashed var(--line-strong)",
    borderRadius: 8,
    background: "#ffffff",
    padding: "8px 10px",
    color: "var(--text-muted)",
    fontSize: 12,
  },
  hr: {
    width: "100%",
    height: 1,
    border: 0,
    background: "var(--line)",
  },
};

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .trim()
    .replace(/[`*_~[\]()]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");

  return slug || "section";
}

function normalizeMarkdown(markdown: string): string[] {
  return markdown.replace(/\r\n?/g, "\n").split("\n");
}

function isFenceStart(line: string): RegExpMatchArray | null {
  return line.match(/^\s*(```|~~~)\s*([A-Za-z0-9_-]+)?\s*$/);
}

function isListStart(line: string): boolean {
  return /^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(line);
}

function isHeading(line: string): boolean {
  return /^(#{1,6})\s+/.test(line.trim());
}

function isHorizontalRule(line: string): boolean {
  return /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line);
}

function parsePipeRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  const cells = parsePipeRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isTableStart(line: string | undefined, nextLine: string | undefined): boolean {
  return Boolean(line?.includes("|") && nextLine?.includes("|") && isTableSeparator(nextLine));
}

function isQuoteStart(line: string): boolean {
  return /^\s{0,3}>\s?/.test(line);
}

function isBlockStart(line: string | undefined, nextLine?: string): boolean {
  if (line === undefined) {
    return false;
  }

  return Boolean(
    isFenceStart(line) ||
      isHeading(line) ||
      isHorizontalRule(line) ||
      isListStart(line) ||
      isQuoteStart(line) ||
      isTableStart(line, nextLine),
  );
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = normalizeMarkdown(markdown);
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (line.trim() === "") {
      index += 1;
      continue;
    }

    const fence = isFenceStart(line);
    if (fence) {
      const marker = fence[1];
      const language = fence[2] ?? null;
      const codeLines: string[] = [];
      index += 1;

      while (index < lines.length && !lines[index].trim().startsWith(marker)) {
        codeLines.push(lines[index]);
        index += 1;
      }

      if (index < lines.length) {
        index += 1;
      }

      blocks.push({ type: "code", language, code: codeLines.join("\n") });
      continue;
    }

    const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line.trim());
    if (heading) {
      const text = heading[2].trim();
      blocks.push({
        type: "heading",
        id: `report-heading-${index}-${slugify(text)}`,
        level: heading[1].length,
        text,
      });
      index += 1;
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push({ type: "hr" });
      index += 1;
      continue;
    }

    if (isTableStart(line, lines[index + 1])) {
      const headers = parsePipeRow(line);
      const rows: string[][] = [];
      index += 2;

      while (index < lines.length && lines[index].trim() !== "" && lines[index].includes("|")) {
        rows.push(parsePipeRow(lines[index]));
        index += 1;
      }

      blocks.push({ type: "table", headers, rows });
      continue;
    }

    if (isListStart(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const marker = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/;
      const items: string[] = [];

      while (index < lines.length) {
        const current = lines[index];

        if (current.trim() === "") {
          index += 1;
          break;
        }

        if (marker.test(current)) {
          items.push(current.replace(marker, "").trim());
          index += 1;
          continue;
        }

        if (items.length > 0 && !isBlockStart(current, lines[index + 1])) {
          items[items.length - 1] = `${items[items.length - 1]}\n${current.trim()}`;
          index += 1;
          continue;
        }

        break;
      }

      blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (isQuoteStart(line)) {
      const quoteLines: string[] = [];

      while (index < lines.length && isQuoteStart(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s{0,3}>\s?/, ""));
        index += 1;
      }

      blocks.push({ type: "quote", text: quoteLines.join("\n") });
      continue;
    }

    const paragraphLines: string[] = [];

    while (index < lines.length && lines[index].trim() !== "" && !isBlockStart(lines[index], lines[index + 1])) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }

    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

export function extractHeadings(markdown: string): Heading[] {
  return parseMarkdown(markdown)
    .filter((block): block is Extract<MarkdownBlock, { type: "heading" }> => block.type === "heading" && block.level <= 3)
    .map(({ id, text, level }) => ({ id, text, level }));
}

function safeDecode(value: string): string {
  try {
    return decodeURI(value);
  } catch {
    return value;
  }
}

function stripMarkdownDestination(rawTarget: string): string {
  const trimmed = rawTarget.trim();

  if (trimmed.startsWith("<")) {
    const end = trimmed.indexOf(">");
    return end > 0 ? trimmed.slice(1, end) : trimmed;
  }

  return trimmed.split(/\s+/)[0] ?? trimmed;
}

function normalizeTargetPath(rawTarget: string): string {
  return safeDecode(stripMarkdownDestination(rawTarget))
    .replace(/^file:\/+/i, "")
    .replaceAll("\\", "/")
    .replace(/^\.\/+/, "")
    .split(/[?#]/)[0]
    .trim();
}

function basename(value: string): string {
  const normalized = value.replaceAll("\\", "/");
  return normalized.slice(normalized.lastIndexOf("/") + 1).toLowerCase();
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
  const metadataUrl = metadataString(artifact, ["content_url", "path_url", "screenshot_url"]);

  if (metadataUrl) {
    return backendUrl(metadataUrl);
  }

  return runArtifactContentUrl(artifact.run_id, artifact.id);
}

function isLikelyImageArtifact(artifact: Artifact): boolean {
  return artifact.type === "screenshot" || artifact.media_type.startsWith("image/") || imageExtensions.test(artifact.path);
}

function isSafeRunRelativeScreenshotPath(path: string): boolean {
  return (
    path.startsWith("screenshots/") &&
    !path.startsWith("/") &&
    !path.includes("..") &&
    !path.includes(":") &&
    !path.includes("//")
  );
}

function findMatchingArtifact(targetPath: string, artifacts: Artifact[]): Artifact | null {
  const normalizedTarget = normalizeTargetPath(targetPath).toLowerCase();
  const screenshotIndex = normalizedTarget.lastIndexOf("screenshots/");
  const screenshotSuffix = screenshotIndex >= 0 ? normalizedTarget.slice(screenshotIndex) : normalizedTarget;
  const targetBase = basename(normalizedTarget);

  const exactMatch = artifacts.find((artifact) => {
    const artifactPath = normalizeTargetPath(artifact.path).toLowerCase();
    return artifactPath === normalizedTarget || artifactPath === screenshotSuffix;
  });

  if (exactMatch) {
    return exactMatch;
  }

  const suffixMatch = artifacts.find((artifact) => {
    const artifactPath = normalizeTargetPath(artifact.path).toLowerCase();
    return normalizedTarget.endsWith(artifactPath) || artifactPath.endsWith(normalizedTarget);
  });

  if (suffixMatch) {
    return suffixMatch;
  }

  return (
    artifacts.find((artifact) => {
      if (!isLikelyImageArtifact(artifact)) {
        return false;
      }

      return basename(artifact.path) === targetBase || basename(artifact.title) === targetBase;
    }) ?? null
  );
}

function buildAssetResolver(runId: string | null | undefined, artifacts: Artifact[]): AssetResolver {
  return (target) => {
    const normalizedTarget = normalizeTargetPath(target);

    if (!normalizedTarget || /^(?:https?:|mailto:|#)/i.test(normalizedTarget)) {
      return null;
    }

    const artifact = findMatchingArtifact(normalizedTarget, artifacts);

    if (artifact) {
      return getArtifactUrl(artifact);
    }

    if (runId && imageExtensions.test(normalizedTarget) && isSafeRunRelativeScreenshotPath(normalizedTarget)) {
      return runArtifactPathUrl(runId, normalizedTarget);
    }

    return null;
  };
}

function safeExternalHref(rawTarget: string): string | null {
  const target = stripMarkdownDestination(rawTarget);

  if (/^https?:\/\//i.test(target) || /^mailto:/i.test(target) || /^#[\w.-]+$/i.test(target)) {
    return backendUrl(target);
  }

  return null;
}

function readBracketed(text: string, start: number): { value: string; end: number } | null {
  if (text[start] !== "[") {
    return null;
  }

  const end = text.indexOf("]", start + 1);
  return end > start ? { value: text.slice(start + 1, end), end } : null;
}

function readParenthesized(text: string, start: number): { value: string; end: number } | null {
  if (text[start] !== "(") {
    return null;
  }

  const end = text.indexOf(")", start + 1);
  return end > start ? { value: text.slice(start + 1, end), end } : null;
}

function ReportImage({ alt, src }: { alt: string; src: string }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <span style={styles.imageFallback} title="The referenced artifact URL could not be loaded as an image.">
        Image unavailable{alt ? `: ${alt}` : ""}
      </span>
    );
  }

  return (
    <span style={styles.imageShell}>
      <a href={src} target="_blank" rel="noreferrer">
        <img src={src} alt={alt || "Report artifact image"} style={styles.image} onError={() => setFailed(true)} />
      </a>
      {alt ? <span style={styles.imageCaption}>{alt}</span> : null}
    </span>
  );
}

function renderInline(text: string, keyPrefix: string, resolveAsset: AssetResolver): ReactNode[] {
  const nodes: ReactNode[] = [];
  let index = 0;

  while (index < text.length) {
    if (text.startsWith("![", index)) {
      const label = readBracketed(text, index + 1);
      const target = label ? readParenthesized(text, label.end + 1) : null;

      if (label && target) {
        const href = resolveAsset(target.value) ?? safeExternalHref(target.value);
        nodes.push(
          href ? (
            <ReportImage key={`${keyPrefix}-image-${index}`} alt={label.value} src={href} />
          ) : (
            <span key={`${keyPrefix}-image-missing-${index}`} style={styles.unresolvedLink}>
              {label.value || "Image reference unavailable"}
            </span>
          ),
        );
        index = target.end + 1;
        continue;
      }
    }

    if (text[index] === "[") {
      const label = readBracketed(text, index);
      const target = label ? readParenthesized(text, label.end + 1) : null;

      if (label && target) {
        const href = resolveAsset(target.value) ?? safeExternalHref(target.value);
        nodes.push(
          href ? (
            <a key={`${keyPrefix}-link-${index}`} href={href} target={href.startsWith("#") ? undefined : "_blank"} rel="noreferrer" style={styles.link}>
              {renderInline(label.value, `${keyPrefix}-link-label-${index}`, resolveAsset)}
            </a>
          ) : (
            <span
              key={`${keyPrefix}-unresolved-${index}`}
              style={styles.unresolvedLink}
              title="This report link was not opened because it is not a registered backend artifact URL."
            >
              {renderInline(label.value, `${keyPrefix}-unresolved-label-${index}`, resolveAsset)}
            </span>
          ),
        );
        index = target.end + 1;
        continue;
      }
    }

    if (text[index] === "`") {
      const end = text.indexOf("`", index + 1);

      if (end > index) {
        nodes.push(
          <code key={`${keyPrefix}-code-${index}`} style={styles.inlineCode}>
            {text.slice(index + 1, end)}
          </code>,
        );
        index = end + 1;
        continue;
      }
    }

    if (text.startsWith("**", index)) {
      const end = text.indexOf("**", index + 2);

      if (end > index) {
        nodes.push(
          <strong key={`${keyPrefix}-strong-${index}`}>
            {renderInline(text.slice(index + 2, end), `${keyPrefix}-strong-inner-${index}`, resolveAsset)}
          </strong>,
        );
        index = end + 2;
        continue;
      }
    }

    if (text[index] === "*") {
      const end = text.indexOf("*", index + 1);

      if (end > index + 1) {
        nodes.push(
          <em key={`${keyPrefix}-em-${index}`}>
            {renderInline(text.slice(index + 1, end), `${keyPrefix}-em-inner-${index}`, resolveAsset)}
          </em>,
        );
        index = end + 1;
        continue;
      }
    }

    const nextSpecial = text.slice(index + 1).search(/[![`*]/);
    const nextIndex = nextSpecial >= 0 ? index + 1 + nextSpecial : text.length;
    nodes.push(text.slice(index, nextIndex));
    index = nextIndex;
  }

  return nodes;
}

function renderInlineWithBreaks(text: string, keyPrefix: string, resolveAsset: AssetResolver): ReactNode[] {
  return text.split("\n").flatMap((line, index) => [
    ...(index > 0 ? [<br key={`${keyPrefix}-br-${index}`} />] : []),
    ...renderInline(line, `${keyPrefix}-line-${index}`, resolveAsset),
  ]);
}

function headingStyle(level: number): CSSProperties {
  if (level === 1) {
    return styles.heading1;
  }

  if (level === 2) {
    return styles.heading2;
  }

  if (level === 3) {
    return styles.heading3;
  }

  return styles.heading4;
}

function renderHeading(block: Extract<MarkdownBlock, { type: "heading" }>, index: number, resolveAsset: AssetResolver): ReactNode {
  const content = renderInline(block.text, `heading-${index}`, resolveAsset);
  const style = headingStyle(block.level);

  if (block.level === 1) {
    return (
      <h1 key={block.id} id={block.id} style={style}>
        {content}
      </h1>
    );
  }

  if (block.level === 2) {
    return (
      <h2 key={block.id} id={block.id} style={style}>
        {content}
      </h2>
    );
  }

  if (block.level === 3) {
    return (
      <h3 key={block.id} id={block.id} style={style}>
        {content}
      </h3>
    );
  }

  return (
    <h4 key={block.id} id={block.id} style={style}>
      {content}
    </h4>
  );
}

function renderBlock(block: MarkdownBlock, index: number, resolveAsset: AssetResolver): ReactNode {
  if (block.type === "heading") {
    return renderHeading(block, index, resolveAsset);
  }

  if (block.type === "paragraph") {
    return (
      <p key={`paragraph-${index}`} style={styles.paragraph}>
        {renderInline(block.text, `paragraph-${index}`, resolveAsset)}
      </p>
    );
  }

  if (block.type === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <Tag key={`list-${index}`} style={styles.list}>
        {block.items.map((item, itemIndex) => (
          <li key={`${index}-${itemIndex}`} style={styles.listItem}>
            {renderInlineWithBreaks(item, `list-${index}-${itemIndex}`, resolveAsset)}
          </li>
        ))}
      </Tag>
    );
  }

  if (block.type === "code") {
    return (
      <pre key={`code-${index}`} style={styles.codeBlock}>
        <code>{block.code}</code>
      </pre>
    );
  }

  if (block.type === "table") {
    return (
      <div key={`table-${index}`} style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              {block.headers.map((header, headerIndex) => (
                <th key={`${index}-header-${headerIndex}`} style={{ ...styles.tableCell, ...styles.tableHeader }}>
                  {renderInline(header, `table-${index}-header-${headerIndex}`, resolveAsset)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={`${index}-row-${rowIndex}`}>
                {block.headers.map((_, cellIndex) => (
                  <td key={`${index}-row-${rowIndex}-cell-${cellIndex}`} style={styles.tableCell}>
                    {renderInline(row[cellIndex] ?? "", `table-${index}-${rowIndex}-${cellIndex}`, resolveAsset)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (block.type === "quote") {
    return (
      <blockquote key={`quote-${index}`} style={styles.quote}>
        {renderInlineWithBreaks(block.text, `quote-${index}`, resolveAsset)}
      </blockquote>
    );
  }

  return <hr key={`hr-${index}`} style={styles.hr} />;
}

export function ReportMarkdown({ markdown, artifacts, runId }: ReportMarkdownProps) {
  const blocks = useMemo(() => parseMarkdown(markdown), [markdown]);
  const resolveAsset = useMemo(() => buildAssetResolver(runId, artifacts), [artifacts, runId]);

  return <div style={styles.root}>{blocks.map((block, index) => renderBlock(block, index, resolveAsset))}</div>;
}
