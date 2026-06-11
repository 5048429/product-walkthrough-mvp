# Version History

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
