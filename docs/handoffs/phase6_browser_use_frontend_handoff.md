# Phase 6 Browser-Use Frontend Integration Handoff

## Scope

This pass connected the simplified `apps/web` UI to the Phase 6 browser-use backend path.

Modified frontend areas:
- `apps/web/src/api/`
- `apps/web/src/hooks/`
- `apps/web/src/components/`
- `apps/web/src/pages/`
- `apps/web/src/types/`

`src/prodwalk/` was not modified by this frontend pass.

## 新增 UI

- Run mode selector now supports `mock` and `browser-use`.
- The main launcher button changes between `Start Mock Run` and `Start Browser-use Run`.
- Browser-use mode shows a compact parameter area:
  - `Browser max steps`
  - `Timeout seconds`
  - `Verification mode`
  - headless/visible browser note, explaining that `BROWSER_USE_HEADLESS` is controlled by the server environment.
- Advanced browser-use parameters are in a collapsed section by default:
  - `User data dir`
  - `Storage state`
  - `Verification timeout`
  - `Success URL contains`
  - `Login URL contains`
- `timeout` is now a first-class frontend status and renders as a failed/red terminal state.
- `awaiting_verification` gets a dedicated Current Run Status panel with the button `我已完成验证，继续`.

## Browser-Use 请求参数

Browser-use launch still uses the existing API client method:

```text
POST /api/runs
```

When mode is `browser-use`, the frontend sends:

```json
{
  "config_path": "<selected plan path>",
  "plan": null,
  "mode": "browser-use",
  "out": "runs",
  "concurrency": 1,
  "report_language": "<plan/report language>",
  "browser_model": null,
  "browser_max_steps": 25,
  "browser_timeout_sec": 600,
  "browser_user_data_dir": null,
  "browser_storage_state": null,
  "verification_mode": "auto",
  "verification_timeout_sec": 300,
  "verification_success_url_contains": [],
  "verification_login_url_contains": "/auth/login"
}
```

Notes:
- Browser-use always sends `concurrency: 1` from the UI.
- Empty user data dir and storage state fields are sent as `null`.
- `verification_success_url_contains` is entered as comma-separated text and sent as a string array.
- The frontend contract now uses `verification_mode: "auto" | "off"`. Historical/backend `manual` values are normalized to `auto` on read.
- Mock mode still sends `mode: "mock"` and forces `verification_mode: "off"`.

## Verification 交互方式

- When the active run status is `awaiting_verification`, the dashboard shows a verification prompt.
- Clicking `我已完成验证，继续` calls:

```text
POST /api/runs/{run_id}/verification/confirm
```

with:

```json
{
  "confirmed": true,
  "note": "Confirmed from the web console."
}
```

- After confirm, the hook refreshes recent events, run detail, and run history.
- If the backend returns `blocked`, the UI explains that verification was recorded but no waiting browser task remained to continue.
- In mock fallback preview, the same button returns the local preview to a running state without calling the API.

## Screenshot 展示方式

- Existing screenshot rendering was preserved and reused.
- Evidence items continue to use `screenshot_artifact_id` and `screenshot_artifact_ids`.
- `ScreenshotPreview` resolves real images through artifact metadata URLs when present, otherwise through:

```text
GET /api/runs/{run_id}/artifacts/{artifact_id}/content
```

- Multiple screenshots show the first image inline and expose additional screenshot artifact links.
- Browser-use screenshots therefore render from archived screenshot artifacts, not from local filesystem paths.

## Browser-Use 错误展示

- API errors now format nested `details.errors`, `details.message`, `details.reason`, `details.type`, and `details.path` into readable text.
- This makes backend failures such as `BROWSER_USE_UNAVAILABLE` show the concrete missing dependency/configuration reasons instead of a raw JSON blob.
- Run-level `timeout` and `failed` states remain reviewable with partial artifacts.

## Validation

Build:

```text
cd apps/web
npm run build
```

Result:

```text
tsc --noEmit -p tsconfig.json
tsc --noEmit -p tsconfig.node.json
vite build
55 modules transformed
built successfully
```

Browser smoke check:
- Started Vite at `http://127.0.0.1:5173/` with `VITE_API_BASE_URL=http://127.0.0.1:8000`.
- Confirmed the simplified Dashboard renders.
- Switched to `browser-use` mode and confirmed visible controls for max steps, timeout seconds, verification mode, the headless/server environment note, and `Start Browser-use Run`.
- Confirmed advanced browser-use parameters are collapsed by default and reveal user data dir, storage state, verification timeout, success URL, and login URL when expanded.
- Switched back to mock mode and launched a mock run from the UI; it completed with `1/1` scenarios and report content visible.
- Browser console error check returned no errors before and after the mock run.

## 遗留问题

- This frontend pass does not add a browser-use readiness API or readiness panel; dependency/key/browser availability errors still come back from `POST /api/runs`.
- The `verification/confirm` button is wired, but true visible-browser continuation depends on backend runtime support. Current backend behavior may record confirmation and return `blocked` if no waiting task remains.
- Stop/cancel remains disabled in the simplified launcher because this pass did not wire the cancel UI.
- The UI exposes user data dir and storage state as text inputs only; it does not provide a profile picker.
- Real browser-use screenshot rendering depends on backend archived screenshot artifacts being present. The frontend path is ready, but this pass did not run a real browser-use UAT.
