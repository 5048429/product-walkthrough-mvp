# Product Walkthrough MVP

This is a multi-agent MVP for product walkthrough research.

Pipeline:

`ResearchDirector -> ScenarioPlanner -> BrowserWalker -> EvidenceExtractor -> ProductAnalyst -> CompetitiveAnalyst -> Reviewer -> ReportWriter -> Evaluator`

The default `mock` walker validates orchestration without opening a browser. The local `browser-use` walker controls a local Chrome/Edge browser for real walkthroughs.

## Key Files

- `src/prodwalk/cli.py`: command entry point.
- `src/prodwalk/auth_session.py`: human-assisted login profile creation for Altcha/CAPTCHA/SSO flows.
- `src/prodwalk/agents/director.py`: orchestration for walkthroughs, evidence, analysis, reporting, and evaluation.
- `src/prodwalk/agents/walker.py`: browser walkthrough boundary, including `MockBrowserWalker` and `BrowserUseLocalWalker`.
- `src/prodwalk/agents/analyst.py`: product-level analysis and competitive comparison.
- `src/prodwalk/agents/report.py`: Markdown report generation.
- `src/prodwalk/agents/evaluator.py`: MVP scoring.
- `examples/research_plan.json`: full sample with three products and two scenarios. Replace the sample URLs before real research.
- `examples/smoke_plan.json`: one public page and one light scenario for local browser-use verification.

## Run Mock Mode

```powershell
$env:PYTHONPATH="src"
python -m prodwalk.cli run --config examples/research_plan.json --mode mock --out runs-test
```

Choose the report language per run:

```powershell
python -m prodwalk.cli run --config examples/research_plan.json --mode mock --out runs-test --report-language zh
```

Outputs:

- `evidence.json`: raw walkthrough results and evidence.
- `report.md`: product research report.
- `evaluation.json`: MVP scoring.
- `screenshots/`: archived browser screenshots for the run when browser-use captures them.

## Local Browser-Use

Install dependencies:

```powershell
pip install -e ".[browser-use-local]"
```

The local mode does not need a Browser Use Cloud API key, but it still needs an LLM. By default, this MVP inherits the local Codex config:

- `~/.codex/config.toml`: `model`, `model_provider`, and `base_url`
- `~/.codex/auth.json`: `OPENAI_API_KEY`

The API key is not printed or persisted by this project.

## Report Language

Reports default to English. To make Chinese the default for a plan, add this top-level field:

```json
{
  "research_goal": "Analyze onboarding flows.",
  "report_language": "zh",
  "products": [
    {
      "name": "Example",
      "url": "https://example.test"
    }
  ],
  "scenarios": [
    {
      "title": "Smoke",
      "goal": "Verify the entry flow."
    }
  ]
}
```

The CLI flag `--report-language en|zh` overrides the config for a single run.

## Local Credentials

Research plans should only contain a stable `credentials_ref`, not real passwords.

Store a credential locally:

```powershell
$env:PYTHONPATH="src"
python -m prodwalk.cli credentials set --ref CLINK_UAT_ACCOUNT --site https://uat-dashboard.clinkbill.com --username "name@example.com"
```

The command prompts for the password without echoing it. By default credentials are stored in `.prodwalk/credentials.json`, which is ignored by git. On Windows, secret values are encrypted with the current user's DPAPI key, so the file is not portable to another OS user.

List stored refs without revealing secrets:

```powershell
$env:PYTHONPATH="src"
python -m prodwalk.cli credentials list
```

Delete a ref:

```powershell
$env:PYTHONPATH="src"
python -m prodwalk.cli credentials delete --ref CLINK_UAT_ACCOUNT
```

At runtime, `BrowserUseLocalWalker` first checks environment variables such as `CLINK_UAT_ACCOUNT_USERNAME` and `CLINK_UAT_ACCOUNT_PASSWORD`, then falls back to the local encrypted credential store. Credentials are passed to browser-use through `sensitive_data` placeholders and redacted from saved history files.

## Human-Assisted Login For Altcha/CAPTCHA

For products that use Altcha, CAPTCHA, SSO, MFA, or other bot checks, use a human login checkpoint once and let later walkthroughs reuse that local browser profile.

Create or refresh the authenticated profile:

```powershell
$env:PYTHONPATH="src"
python -m prodwalk.cli auth-session --url https://uat-dashboard.clinkbill.com/analytics --credentials-ref CLINK_UAT_ACCOUNT --user-data-dir .prodwalk\browser-profiles\clink_uat_account --success-url-contains /analytics --timeout-sec 300 --manual-confirm
```

This opens a visible Chrome/Edge window and fills stored credentials when available. Complete Altcha and click Login manually. When the authenticated product page is visible, return to the terminal and press Enter. The command then closes the browser and keeps the profile under `.prodwalk/browser-profiles/...`.

Run the product walkthrough with that saved session:

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="true"
python -m prodwalk.cli run --config examples/clink_uat_full_continuous_plan.json --mode browser-use --out runs-clink-continuous-headless --concurrency 1 --browser-max-steps 55 --browser-timeout-sec 900 --browser-user-data-dir .prodwalk\browser-profiles\clink_uat_account
```

Use `BROWSER_USE_HEADLESS="false"` only when debugging the browser visually. For normal PM research runs, headless mode is recommended.

The main `run` command also performs an automatic verification checkpoint by default. It first checks whether the configured browser profile is already authenticated and refreshes a run-local `prodwalk_storage_state.json` beside that profile. If the product is still on login, Altcha, CAPTCHA, or another verification page, the command opens a visible browser, fills stored credentials when available, and waits for you to complete verification. After the authenticated product page is visible, return to the terminal and press Enter; the same run command then continues into the headless browser-use walkthrough.

There is also a second safety net during the formal browser-use walkthrough. If browser-use is redirected back to login or reports that Altcha/CAPTCHA/manual verification is required, the run pauses, opens a visible browser, asks you to complete verification, and retries the walkthrough once.

Disable this checkpoint for public or fully automated runs:

```powershell
python -m prodwalk.cli run --config examples/smoke_plan.json --mode browser-use --out runs --verification-mode off
```

## Recommended First Real Run

First run the smoke plan to verify browser control, LLM wiring, evidence capture, report writing, and evaluation:

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="true"
python -m prodwalk.cli run --config examples/smoke_plan.json --mode browser-use --out runs --concurrency 1 --browser-max-steps 12
```

After the smoke run succeeds, replace the URLs in `examples/research_plan.json`:

- `https://example.com`
- `https://example.org`
- `https://example.net`

Use your real product/staging URL and competitor URLs.

Then run:

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="true"
python -m prodwalk.cli run --config examples/research_plan.json --mode browser-use --out runs --concurrency 1 --browser-max-steps 25
```

Local browser-use mode defaults to concurrency `1`, because launching multiple local browser sessions in parallel can trigger Chrome/CDP startup timeouts. Mock mode defaults to concurrency `3`.

For authenticated products that use bot checks or short-lived verification, prefer the human-assisted profile flow above. `--browser-storage-state` remains available as an optional browser-use runtime path, but persistent `--browser-user-data-dir` is the recommended MVP path for Clink-style UAT testing.

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="true"
python -m prodwalk.cli run --config examples/clink_uat_full_continuous_plan.json --mode browser-use --out runs-clink-continuous-headless --concurrency 1 --browser-max-steps 55 --browser-timeout-sec 900 --browser-user-data-dir .prodwalk\browser-profiles\clink_uat_account
```

Each browser-use scenario is bounded by `--browser-timeout-sec`, so a stuck login, loading state, or navigation loop becomes a blocked scenario in the report instead of preventing artifact generation. Browser screenshots captured during the run are copied into that run's `screenshots/` directory and referenced from `evidence.json` and `report.md` with relative paths.

For Clink-style UAT runs, one command is enough:

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="true"
python -m prodwalk.cli run --config examples/clink_uat_full_continuous_plan.json --mode browser-use --out runs-clink-full --concurrency 1 --browser-max-steps 55 --browser-timeout-sec 900 --browser-user-data-dir .prodwalk\browser-profiles\clink_uat_account --report-language zh
```

If verification is needed, complete it in the browser window, then press Enter in the terminal. The run will continue automatically.

## Optional Environment Variables

- `BROWSER_USE_LLM_PROVIDER`: `openai`, `anthropic`, `google`, `ollama`, or `openrouter`
- `BROWSER_USE_MODEL`: model name
- `BROWSER_USE_LLM_API_KEY`: generic LLM key override
- `BROWSER_USE_INHERIT_CODEX`: inherit Codex config, default `true`
- `BROWSER_USE_OPENAI_WIRE_API`: `responses` or `chat`; inherited from Codex when available
- `BROWSER_USE_OPENAI_BASE_URL`: OpenAI-compatible base URL override
- `BROWSER_USE_REASONING_EFFORT`: reasoning effort for Responses API models, default `low`
- `BROWSER_USE_CHROME_PATH`: Chrome/Edge executable path
- `BROWSER_USE_HEADLESS`: headless mode, default `true`
- `BROWSER_USE_USER_DATA_DIR`: browser user data directory for login reuse
- `BROWSER_USE_STORAGE_STATE`: storage state JSON file for login/session reuse
- `BROWSER_USE_RUN_TIMEOUT_SEC`: maximum seconds per browser-use scenario
- `BROWSER_USE_RECORD_VIDEO_DIR`: local video recording output directory
- `PRODWALK_CREDENTIAL_STORE`: local credential store path, default `.prodwalk/credentials.json`

## Verification Options

- `--verification-mode`: `auto` or `off`, default `auto`
- `--verification-timeout-sec`: maximum seconds for automatic login success detection
- `--verification-login-url-contains`: URL substring treated as login page, default `/auth/login`
- `--verification-success-url-contains`: URL substring that marks login success; can be passed multiple times

## Current Evaluation Metrics

`evaluation.json` includes:

- task completion rate
- evidence coverage rate
- finding grounding rate
- recommendation actionability rate

`report.md` includes product findings extracted from browser-use final summaries when the agent returns structured JSON-like fields such as `blockers`, `friction_points`, `evidence_needed`, and `top_recommendations`. The MVP currently classifies issues such as loading-state friction, secret exposure, destructive controls, empty states, and external-link clarity with simple deterministic rules.

The next useful step is a human-labeled golden set: expected issues, key screenshot moments, and success paths for each scenario, then compare system output against that set.
