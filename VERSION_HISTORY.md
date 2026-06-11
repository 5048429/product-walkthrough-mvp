# Version History

## v0.4.0 - 2026-06-11

Status: browser-use final summaries now become structured product findings.

### Added

- Product analysis now parses browser-use final JSON summaries from run evidence.
- Structured findings are generated from:
  - `blockers`
  - `friction_points`
  - `top_recommendations`
- Finding themes now classify common product-walkthrough issues:
  - Secret handling/admin safety
  - Permission and destructive controls
  - Navigation and loading feedback
  - Empty-state guidance
  - External-link clarity
- Full redacted browser-use final output is stored in browser-run evidence data as `final_output`, avoiding loss from display-summary truncation.

### Changed

- Completed browser runs no longer default to a weak `Baseline pass` when the final summary contains product issues.
- Product analysis summaries now include the number of extracted product findings in addition to runtime blockers/friction.

### Validation

- Unit tests: `22 tests OK`.
- Added coverage for Clink-style final summaries with loading-state, secret exposure, and destructive-control findings.

## v0.3.2 - 2026-06-11

Status: auth-session success detection hardened.

### Fixed

- `prodwalk auth-session` no longer treats the initial target URL as a successful login while the login form, password input, or Altcha widget is still visible.
- Added `--manual-confirm` so the user can complete Altcha/login, verify the authenticated product page visually, then press Enter before the profile is saved.

## v0.3.1 - 2026-06-11

Status: auth-session dependency fix.

### Fixed

- Added explicit `playwright` dependency to the `browser-use-local` extra because `prodwalk auth-session` imports Playwright directly for human-assisted login profile creation.

## v0.3.0 - 2026-06-11

Status: Clink walkthrough reliability improved with human-assisted auth and one-session runs.

### Added

- `prodwalk auth-session` command for human-assisted login checkpoints.
  - Opens a visible local browser.
  - Auto-fills stored credentials when a `--credentials-ref` is provided.
  - Lets the user manually complete Altcha/CAPTCHA/SSO/MFA.
  - Saves a reusable persistent browser profile under `.prodwalk/browser-profiles/...`.
- Recommended Clink run path using one continuous scenario:
  - `examples/clink_uat_full_continuous_plan.json`
  - `--browser-user-data-dir .prodwalk\browser-profiles\clink_uat_account`
  - `BROWSER_USE_HEADLESS=true` for normal report generation.
- Browser-use run timeout support:
  - CLI: `--browser-timeout-sec`
  - Env: `BROWSER_USE_RUN_TIMEOUT_SEC`
- Browser runtime path support:
  - CLI: `--browser-user-data-dir`
  - CLI: `--browser-storage-state`
  - Env: `BROWSER_USE_USER_DATA_DIR`
  - Env: `BROWSER_USE_STORAGE_STATE`
- Generic redaction for API tokens, Bearer tokens, JWT-like values, and labeled publishable/secret keys.
- More tolerant OpenAI Responses adapter parsing for browser-use structured output with trailing JSON/text.

### Changed

- Headless browser-use is now the recommended default for PM research runs; visible mode is for debugging or the `auth-session` login checkpoint.
- Recovered intermediate browser-use errors no longer automatically mark a scenario as blocked when the final result is present and completed.
- Clink full walkthrough should run as one browser-use session rather than several independent scenarios, avoiding repeated login and Altcha friction.
- Clink prompts now include stronger guardrails against external links, destructive actions, exports, and secret copying.

### Validation

- Unit tests: `20 tests OK`.
- A headless continuous Clink run completed authenticated navigation through Analytics, Core Metrics, Transactions, Balances, Customers, Subscriptions, Products, Developers, and Settings.
- Key product findings from the Clink run:
  - Altcha repeatedly expired during login, creating significant automation and user-flow friction.
  - Developers/API Keys displayed full key values in the UI; reports must avoid copying values and product should consider masking/audit controls.
  - Several read-only review surfaces expose prominent mutating controls such as Add, Edit, Archive, Submit Payout, Generate, Disable, and Save.

### Known Limitations

- `auth-session` requires a local visible browser and human action for bot checks.
- Persistent browser profiles are local machine state and should not be committed, shared, or treated as long-term credential backups.
- Product finding extraction is still mostly heuristic; the next step is stronger parsing of final browser-use JSON summaries into structured product issues.
- UAT environments with Altcha/CAPTCHA should ideally provide an automation-safe bypass, allowlist, pre-auth token, or dedicated test role for reliable scheduled runs.

## v0.2.0 - 2026-06-11

Status: local credential storage implemented.

### Added

- Local encrypted credential store at `.prodwalk/credentials.json`.
- CLI credential management:
  - `python -m prodwalk.cli credentials set`
  - `python -m prodwalk.cli credentials list`
  - `python -m prodwalk.cli credentials delete`
- Windows DPAPI encryption for stored usernames and passwords.
- Runtime credential resolution order:
  - environment variables first
  - local encrypted credential store second
- Browser-use `sensitive_data` integration now works from stored credentials as well as environment variables.
- Additional file-level redaction for saved browser-use history files.

### Validation

- Unit tests cover credential store round trip, no-plaintext storage, credential listing, and walker credential-store integration.

### Known Limitations

- Credential encryption currently targets Windows DPAPI only.
- The credential store is local to the current Windows user and should not be copied across machines as a backup format.

## v0.1.0 - 2026-06-11

Status: local MVP validated.

### System Scope

- Multi-agent product walkthrough research MVP.
- Main pipeline: `ResearchDirector -> ScenarioPlanner -> BrowserWalker -> EvidenceExtractor -> ProductAnalyst -> CompetitiveAnalyst -> Reviewer -> ReportWriter -> Evaluator`.
- Supported walkers:
  - `MockBrowserWalker` for deterministic local orchestration tests.
  - `BrowserUseLocalWalker` for real local browser-use walkthroughs.

### Key Capabilities

- Reads research plans from JSON.
- Runs product and competitor walkthrough scenarios.
- Produces three artifacts per run:
  - `evidence.json`
  - `report.md`
  - `evaluation.json`
- Supports local open-source `browser-use` without Browser Use Cloud.
- Inherits local Codex LLM configuration by default.
- Supports Codex/OpenAI-compatible Responses API through `OpenAIResponsesChatModel`.
- Supports sensitive login credentials through browser-use `sensitive_data` placeholders.
- Redacts sensitive values from final output and saved browser-use history files.

### Included Example Plans

- `examples/smoke_plan.json`: public Wikipedia browser-use smoke test.
- `examples/clink_uat_plan.json`: Clink UAT analytics login and first-screen walkthrough.
- `examples/research_plan.json`: multi-product research template.

### Validation

- Unit tests: `9 tests OK`.
- Wikipedia smoke test:
  - Local browser-use successfully opened Wikipedia, searched for product management, opened a result, and produced a final summary.
- Clink UAT analytics smoke test:
  - Opened `https://uat-dashboard.clinkbill.com/analytics`.
  - Redirected to login.
  - Logged in with sensitive-data placeholders.
  - Reached authenticated analytics dashboard.
  - Produced report and evaluation with `overall_score = 1.0`.

### Known Limitations

- browser-use may occasionally return malformed structured JSON; it usually retries and recovers.
- Product findings are still heuristic and need stronger parsing of final JSON summaries.
- Evaluation is basic; a human-labeled golden set is still needed.
- PowerShell may display Unicode logs as mojibake depending on console encoding.
- Remote GitHub publishing is not configured yet.

### Next Version Goals

- Add a golden-set based evaluator.
- Add scenario-level assertions for login, dashboard load, and first-screen evidence.
- Convert recovered automation errors into separate system reliability metrics.
- Add richer product finding extraction from final walkthrough summaries.
- Add remote GitHub workflow once repository URL and authentication are available.
