# Phase 5 Report Experience Handoff

## Scope

This handoff covers the frontend Report Preview experience work. Changes are limited to:

- `apps/web/src/components/reports/`
- `apps/web/src/api/paths.ts`
- `docs/handoffs/phase5_report_experience_handoff.md`

No backend files, Evidence Viewer component body, or `apps/web/package.json` were changed.

## ReportPreview New Capabilities

- Report body now renders as readable Markdown instead of raw `<pre>` text.
- Outline entries now link to rendered report headings.
- Report states are clearer for:
  - loading: shows API read progress before Markdown is available and a refresh banner when Markdown is already visible.
  - empty: distinguishes no selected run, running-but-not-generated, and empty `report.md`.
  - running: keeps partial report visible with a partial-report banner.
  - failed / blocked: keeps recoverable Markdown visible when present and shows an error state when not present.
- Evaluation errors no longer hide the Markdown report.
- Report request errors can be shown as compact warnings when stale or partial Markdown is still available.

## Markdown Rendering

No Markdown dependency was added. The renderer is a small safe React renderer in `ReportMarkdown.tsx`.

Supported blocks:

- headings `#` through `######`
- paragraphs
- unordered and ordered lists
- fenced code blocks
- pipe tables
- blockquotes
- horizontal rules

Supported inline elements:

- links
- images
- inline code
- bold
- italic

Raw HTML is not rendered with `dangerouslySetInnerHTML`; it is treated as text through React rendering. Link protocols are restricted to backend artifact URLs, `http(s)`, `mailto`, and heading anchors.

## Copy / Download Implementation

- Copy uses the original full `report.markdown` string, not the rendered or rewritten preview.
- Copy first tries `navigator.clipboard.writeText()`, then falls back to a hidden textarea plus `document.execCommand("copy")`.
- The toolbar shows `Copied` or `Copy failed` feedback.
- Download creates a `Blob` with `text/markdown;charset=utf-8`, attaches a temporary `<a download="report.md">`, clicks it, and revokes the object URL.
- Download also uses the original full `report.markdown` string.

## Artifact Path Handling

`apps/web/src/api/paths.ts` now exposes helpers for backend artifact URLs:

- `backendUrl()`
- `runArtifactContentUrl()`
- `runArtifactPathUrl()`

The Markdown renderer resolves report links/images as follows:

- If a Markdown target matches a registered artifact path or screenshot filename, it uses the backend artifact content URL.
- Artifact metadata URLs are honored when present: `metadata.content_url`, `metadata.path_url`, or `metadata.screenshot_url`.
- Run-relative screenshot paths like `screenshots/shot.png` fall back to `/api/runs/{run_id}/artifacts/screenshots/shot.png`.
- Absolute local paths are not linked directly. If they end with a registered screenshot path or filename, they are mapped to the backend artifact URL; otherwise the rendered link is shown as unresolved text.

## Verification

Command:

```powershell
cd apps/web
npm run build
```

Result:

```text
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
55 modules transformed
dist/index.html
dist/assets/index-D0U1z88j.css
dist/assets/index-D0rDos0j.js
built successfully
```

Browser spot check:

- Opened local dev server on `http://127.0.0.1:5175/`.
- Verified rendered headings, lists, linked outline, and enabled Copy / Download buttons in Report Preview.
- Verified Copy writes the complete Markdown report to the browser clipboard in the mock report path.
- Codex in-app Browser does not support download events, so the actual file-save event could not be observed there; the button and Blob-based implementation are present and build-clean.

## Remaining Issues

- This is not a full CommonMark implementation. Nested lists, escaped pipe table cells, footnotes, and complex Markdown link destinations may render simply.
- Report evidence IDs are still rendered as text unless the report author uses Markdown links.
- Broken screenshot URLs show an inline image-unavailable state, but there is no retry control.
- Download behavior was not end-to-end verified in the in-app Browser because that browser surface rejects downloads.
