# Phase 3 Report And Evidence Handoff

## Scope

Implemented the Phase 3.1 report and evidence display area on top of the existing `apps/web` scaffold. This pass only uses mock data and does not call backend APIs directly.

Modified areas:
- `apps/web/src/components/reports/`
- `apps/web/src/components/evidence/`
- `apps/web/src/components/common/`
- `apps/web/src/types/`
- `apps/web/src/mock/`

No backend files, `src/prodwalk/`, or `apps/web/package.json` were changed.

## Components

### ReportPreview

File: `apps/web/src/components/reports/ReportPreview.tsx`

Props:
- `report: ReportResponse | null`
- `artifacts?: Artifact[]`
- `status?: ConsoleStatus`
- `error?: string | null`

Behavior:
- Displays Markdown text directly in a pre-wrapped preview.
- Shows report outline from Markdown headings.
- Shows evaluation score, metrics, and notes when available.
- Keeps partial Markdown visible during `running`, `blocked`, and `failed` states.
- Shows empty, blocked, and failed states when Markdown is unavailable.

### ReportToolbar

File: `apps/web/src/components/reports/ReportToolbar.tsx`

Props:
- `report: ReportResponse | null`
- `artifacts?: Artifact[]`
- `status: ConsoleStatus`
- `copied: boolean`
- `onCopyMarkdown: () => void`

Behavior:
- Shows status, generated time, report/evaluation artifact links, and Copy Markdown.
- Artifact links use `/api/runs/{run_id}/artifacts/{artifact_id}/content`.

### EvidenceList

File: `apps/web/src/components/evidence/EvidenceList.tsx`

Props:
- `evidence: EvidenceResponse | null`
- `artifacts?: Artifact[]`
- `status?: ConsoleStatus`
- `error?: string | null`
- `initialGroupBy?: "product" | "scenario" | "kind" | "status"`

Behavior:
- Supports grouped display by product, scenario, kind, and status.
- Shows partial evidence banners for `running`, `blocked`, and `failed`.
- Keeps available evidence visible even when the run is blocked or failed.
- Includes selected evidence detail panel with IDs, status, product, scenario, final output, and linked findings.

### EvidenceItemCard

File: `apps/web/src/components/evidence/EvidenceItemCard.tsx`

Props:
- `item: EvidenceItem`
- `result?: WalkthroughResult`
- `artifacts?: Artifact[]`
- `selected?: boolean`
- `onSelect?: (item: EvidenceItem) => void`

Behavior:
- Displays title, product, scenario, kind, status, confidence, step, action, errors, and URL.
- Displays mock screenshot artifact links when present.
- Displays Missing screenshot while keeping evidence text visible.

### ArtifactLink

File: `apps/web/src/components/common/ArtifactLink.tsx`

Props:
- `artifact?: Artifact | null`
- `artifactId?: string | null`
- `artifacts?: Artifact[]`
- `runId?: string | null`
- `label?: string`
- `disabledReason?: string`
- `className?: string`

Behavior:
- Resolves artifact metadata from a direct object or artifact registry.
- Generates backend content URLs only.
- Does not expose or join local filesystem paths.

### EmptyState

File: `apps/web/src/components/common/EmptyState.tsx`

Props:
- `title: string`
- `message: string`
- `action?: ReactNode`
- `compact?: boolean`

### ErrorState

File: `apps/web/src/components/common/ErrorState.tsx`

Props:
- `title: string`
- `message: string`
- `code?: string`
- `details?: string`
- `tone?: "failed" | "blocked"`
- `action?: ReactNode`
- `compact?: boolean`

## Mock Data

### Artifacts

File: `apps/web/src/mock/artifacts.ts`

Includes:
- `art_report_md`
- `art_evaluation_json`
- `art_evidence_json`
- `art_screenshot_onboarding_step_1`

Screenshot artifact is a mock placeholder with `metadata.mock_placeholder = true`; no real image is required.

### Evidence

File: `apps/web/src/mock/evidence.ts`

Includes evidence examples for:
- completed browser step with mock screenshot artifact
- running browser run
- blocked observation
- failed browser step with missing screenshot

The mock evidence response carries the mock artifact registry in `artifacts`.

### Report

File: `apps/web/src/mock/report.ts`

Includes:
- Markdown report text with evidence IDs
- evaluation summary and scores
- mock artifact registry in `artifacts`

## Types

File: `apps/web/src/types/contracts.ts`

Extended:
- `EvidenceItem` with optional `product_kind`, `scenario_title`, `status`, `step_index`, `action`, screenshot/artifact/finding IDs, `errors`, and `final_output`.
- `EvidenceResponse` with optional `artifacts`.
- `ReportResponse` with optional `artifacts`.

The existing API contract fields remain compatible.

## Verification

Ran:

```bash
cd apps/web
npm run build
```

Result: build passed.

Browser smoke check on `http://127.0.0.1:5173/`:
- Report Preview rendered.
- Evidence rendered with 4 cards.
- Artifact links resolved to `/api/runs/.../artifacts/.../content`.
- Browser console had no error logs.

## Remaining Work

- Wire report/evidence status props to the real active run when route/page integration is expanded.
- Replace mock screenshot placeholders with artifact content previews once backend screenshot content is available.
- Add deep links from report evidence IDs to the Evidence Viewer route when route skeleton exists.
- Add automated frontend tests when the project has a test runner configured.
