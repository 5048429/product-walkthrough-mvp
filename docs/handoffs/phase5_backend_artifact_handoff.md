# Phase 5 Backend Artifact Handoff

## Scope

This handoff covers the Phase 5 backend artifact/history/screenshot work for the local FastAPI console. The implementation stays inside `src/prodwalk/server/` plus `tests/test_server.py`; it does not change `apps/web/`, legacy CLI behavior, or report/evidence/evaluation artifact formats.

## Added Or Modified APIs

- `GET /api/runs`
  - Continues to scan in-memory runs plus workspace `runs*` directories.
  - Each run summary now includes:
    - `run_id`
    - `status`
    - `created_at`
    - `mode`
    - `report_exists`
    - `evidence_exists`
    - `evaluation_exists`
    - `screenshot_count`
- `GET /api/runs/{run_id}`
  - Returns the same availability fields through `RunDetail` inheritance.
- `GET /api/runs/{run_id}/artifacts`
  - Rebuilds current fixed artifacts and screenshots from disk, then safely merges valid persisted artifact metadata.
  - Screenshot artifacts are discovered under `run_dir/screenshots/**/*` for `.png`, `.jpg`, `.jpeg`, `.webp`, and `.gif`.
- `GET /api/runs/{run_id}/artifacts/{artifact_id}/content`
  - Existing Phase 4 content URL remains supported.
  - Responses include `X-Content-Type-Options: nosniff`.
- `GET /api/runs/{run_id}/artifacts/{artifact_ref:path}`
  - If `artifact_ref` matches a registered artifact id, returns artifact metadata.
  - Otherwise treats `artifact_ref` as a run-relative artifact file path and returns file content.
- `GET /api/runs/{run_id}/screenshots/{filename}`
  - Returns a screenshot image from `run_dir/screenshots/{filename}` with the correct image media type.

## Artifact URL Rules

Use one of these backend URLs only; the frontend must never link directly to local filesystem paths.

- Metadata by artifact id:
  - `/api/runs/{run_id}/artifacts/{artifact_id}`
  - Example: `/api/runs/run-.../artifacts/art_report_md`
- Content by artifact id:
  - `/api/runs/{run_id}/artifacts/{artifact_id}/content`
  - Example: `/api/runs/run-.../artifacts/art_report_md/content`
- Content by run-relative artifact path:
  - `/api/runs/{run_id}/artifacts/{artifact_path}`
  - Example: `/api/runs/run-.../artifacts/report.md`
  - Example: `/api/runs/run-.../artifacts/screenshots/shot.png`
  - Path segments must be URL encoded by the frontend.

Artifact registry items now include convenience metadata:

- `metadata.content_url`
- `metadata.path_url`
- screenshot artifacts additionally include `metadata.screenshot_url`

## Screenshot URL Rules

Preferred screenshot loading options:

- If the UI has a screenshot artifact id, use:
  - `/api/runs/{run_id}/artifacts/{artifact_id}/content`
- If the UI has a run-relative screenshot path, use:
  - `/api/runs/{run_id}/artifacts/screenshots/{filename}`
- If the UI has only a screenshot filename from an artifact entry, use:
  - `/api/runs/{run_id}/screenshots/{filename}`

The dedicated screenshot endpoint accepts only a single filename, not a nested path.

## Path Safety Strategy

- `run_id` must match the existing `run-[A-Za-z0-9_.-]+` validation.
- Run directories are resolved only from in-memory state or workspace `runs*` scans.
- Artifact path reads are resolved from `run_dir` plus a POSIX-style relative path.
- Empty paths, absolute paths, `.` segments, `..` segments, backslashes, and Windows drive-style `:` segments are rejected with `ARTIFACT_FORBIDDEN`.
- Resolved artifact paths must remain inside the selected `run_dir`.
- Screenshot reads must remain inside `run_dir/screenshots`.
- Missing files return `ARTIFACT_NOT_FOUND`.
- File responses include `X-Content-Type-Options: nosniff`.

## Pytest Result

Command:

```powershell
python -m pytest
```

Result:

```text
46 passed, 1 warning in 7.39s
```

Known warning:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

## Frontend Consumption Guidance

- Run History should read availability directly from `GET /api/runs` instead of probing files.
- Evidence screenshots should resolve `screenshot_artifact_id` through `GET /api/runs/{run_id}/artifacts`, then render `metadata.content_url` or `/artifacts/{artifact_id}/content` in an `<img>`.
- If a screenshot artifact only exposes a path, render `metadata.path_url`.
- If a component has only the screenshot filename, render `metadata.screenshot_url` or `/screenshots/{filename}`.
- Handle `404 ARTIFACT_NOT_FOUND` as a missing/unavailable artifact state.
- Handle `403 ARTIFACT_FORBIDDEN` as an unsafe or unsupported artifact reference state.
- Continue using `GET /report`, `GET /evidence`, and `GET /evaluation` for normalized console views; the raw artifact content endpoints are for file preview/download behavior.
