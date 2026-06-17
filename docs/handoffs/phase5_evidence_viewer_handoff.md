# Phase 5 Evidence Viewer Handoff

## Scope

Enhanced the frontend Evidence Viewer so product managers can scan evidence, statuses, screenshots, and event-linked blocking points more quickly. Changes stayed within the allowed frontend folders plus this handoff.

## Added Or Modified Components

- `apps/web/src/components/evidence/EvidenceList.tsx`
  - Added search over evidence `title`, `summary`, `url`, and `id`.
  - Added filters for `product`, `scenario`, `kind`, and `status`.
  - Kept grouping by `product`, `scenario`, `kind`, or `status`.
  - Added selected evidence detail with screenshot gallery, linked artifact links, linked findings, final output, and sanitized `data`.
  - Listens for `prodwalk:evidence-focus` events from EventLog and selects/scrolls the matching evidence.
- `apps/web/src/components/evidence/EvidenceItemCard.tsx`
  - Replaced screenshot placeholder-only UI with real screenshot preview thumbnails.
  - Keeps visible status pills for `completed`, `blocked`, `friction`, `running`, and `failed`.
- `apps/web/src/components/evidence/ScreenshotPreview.tsx`
  - New component for image artifact rendering, loading state, load failure state, retry, and open-artifact fallback.
- `apps/web/src/components/evidence/evidenceFocus.ts`
  - New helper for stable evidence DOM ids and scroll-to-selected behavior.
- `apps/web/src/components/events/EventLog.tsx`
  - Artifact ids render as clickable tokens.
  - Payload keys containing `evidence` and `id` render string or string-array values as clickable evidence tokens.
  - Clicking a token dispatches `prodwalk:evidence-focus`.
- `apps/web/src/types/contracts.ts`
  - Added `EvidenceItem.data`.
  - Added `EVIDENCE_FOCUS_EVENT` and `EvidenceFocusRequest`.
- `apps/web/src/api/client.ts`
  - Preserves normalized API `data` on evidence items for the detail inspector.
- `apps/web/src/hooks/useProdwalkConsole.ts`
  - Treats `screenshot.archived` as an artifact refresh event.

## Evidence Grouping And Filtering

- Grouping is controlled by `groupBy`: `product`, `scenario`, `kind`, or `status`.
- Filtering is applied before grouping:
  - `product` matches `EvidenceItem.product`.
  - `scenario` matches `scenario_title` when present, otherwise `scenario_id`.
  - `kind` matches `EvidenceItem.kind`.
  - `status` uses `item.status`, then `friction` if the item has errors, then matching walkthrough result status, then `completed`.
- Search runs across title, summary, URL, and id.
- EventLog focus clears active filters/search first so a linked evidence item is not hidden by the current filter.

## Artifact URL Usage

Screenshot previews never read local filesystem paths directly.

Resolution order:

1. `artifact.metadata.content_url`
2. `artifact.metadata.path_url`
3. `artifact.metadata.screenshot_url`
4. Fallback to `runApiPath(runId, /artifacts/{artifact_id}/content)`

Relative `/api/...` metadata URLs are resolved against `VITE_API_BASE_URL` / `VITE_PRODWALK_API_BASE_URL` through the existing API path helpers. Artifact links still open through the backend artifact content endpoint.

## Image Fallback Handling

- Missing screenshot id: shows `Missing screenshot` and keeps the evidence visible.
- Missing screenshot URL: shows `Screenshot URL unavailable` plus artifact link when possible.
- Unsupported media type: shows `Unsupported artifact media`.
- Image load error: hides the broken image and shows `Screenshot failed to load`, `Open artifact`, and `Retry`.
- Browser mock fallback check confirmed the failed screenshot path renders fallback text without console errors.

## EventLog To Evidence Linking

- Evidence id tokens dispatch:
  - `runId`
  - `evidenceId`
  - `sourceEventId`
- Artifact id tokens dispatch:
  - `runId`
  - `artifactId`
  - `sourceEventId`
- EvidenceList resolves by exact evidence id first, then by `artifact_ids`, `screenshot_artifact_id`, or `screenshot_artifact_ids`.

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
54 modules transformed
dist/index.html
dist/assets/index-D0U1z88j.css
dist/assets/index-CNUysQYT.js
built successfully
```

Browser smoke check:

- Started Vite on `http://127.0.0.1:5174/` with API base `http://127.0.0.1:8000`.
- Started temporary mock fallback Vite on `http://127.0.0.1:5176/` with API base `http://127.0.0.1:8999`, then stopped it after verification.
- Confirmed Evidence search/filter controls render in empty and mock-data states.
- Clicked EventLog evidence id `ev-our-product-onboarding-1`; Evidence selected `Clear first-run checklist`.
- Searched `checkout`; Evidence showed `1 of 4 items` and selected the blocked checkout evidence.
- Checked browser console errors/warnings: none.

## Remaining Issues

- Route-level deep links and URL params were not added because this task did not allow changing page/router structure.
- EventLog artifact ids such as `art_evidence_json` may not map to one evidence item; screenshot or evidence-specific artifact ids do map.
- Real browser-use screenshot runs were not created in this pass; screenshot UI was verified against mock missing/failing image behavior and build-time type checks.
- No new package dependency was added; `apps/web/package.json` was not changed.
