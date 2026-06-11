# Product Walkthrough MVP

This is a multi-agent MVP for product walkthrough research.

Pipeline:

`ResearchDirector -> ScenarioPlanner -> BrowserWalker -> EvidenceExtractor -> ProductAnalyst -> CompetitiveAnalyst -> Reviewer -> ReportWriter -> Evaluator`

The default `mock` walker validates orchestration without opening a browser. The local `browser-use` walker controls a local Chrome/Edge browser for real walkthroughs.

## Key Files

- `src/prodwalk/cli.py`: command entry point.
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

Outputs:

- `evidence.json`: raw walkthrough results and evidence.
- `report.md`: product research report.
- `evaluation.json`: MVP scoring.

## Local Browser-Use

Install dependencies:

```powershell
pip install -e ".[browser-use-local]"
```

The local mode does not need a Browser Use Cloud API key, but it still needs an LLM. By default, this MVP inherits the local Codex config:

- `~/.codex/config.toml`: `model`, `model_provider`, and `base_url`
- `~/.codex/auth.json`: `OPENAI_API_KEY`

The API key is not printed or persisted by this project.

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

## Recommended First Real Run

First run the smoke plan to verify browser control, LLM wiring, evidence capture, report writing, and evaluation:

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="false"
python -m prodwalk.cli run --config examples/smoke_plan.json --mode browser-use --out runs --concurrency 1 --browser-max-steps 12
```

`BROWSER_USE_HEADLESS="false"` lets you watch the browser.

After the smoke run succeeds, replace the URLs in `examples/research_plan.json`:

- `https://example.com`
- `https://example.org`
- `https://example.net`

Use your real product/staging URL and competitor URLs.

Then run:

```powershell
$env:PYTHONPATH="src"
$env:BROWSER_USE_HEADLESS="false"
python -m prodwalk.cli run --config examples/research_plan.json --mode browser-use --out runs --concurrency 1 --browser-max-steps 25
```

Local browser-use mode defaults to concurrency `1`, because launching multiple local browser sessions in parallel can trigger Chrome/CDP startup timeouts. Mock mode defaults to concurrency `3`.

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
- `BROWSER_USE_RECORD_VIDEO_DIR`: local video recording output directory
- `PRODWALK_CREDENTIAL_STORE`: local credential store path, default `.prodwalk/credentials.json`

## Current Evaluation Metrics

`evaluation.json` includes:

- task completion rate
- evidence coverage rate
- finding grounding rate
- recommendation actionability rate

The next useful step is a human-labeled golden set: expected issues, key screenshot moments, and success paths for each scenario, then compare system output against that set.
