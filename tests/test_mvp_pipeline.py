from __future__ import annotations

import json
import os
import tempfile
import unittest
import asyncio
from pathlib import Path

from pydantic import BaseModel

from prodwalk.agents.analyst import ProductAnalyst
from prodwalk.agents.director import ResearchDirector
from prodwalk.agents.evidence import EvidenceExtractor
from prodwalk.agents.walker import BrowserUseLocalWalker, MockBrowserWalker
from prodwalk.auth_session import is_auth_success_url, resolve_user_data_dir
from prodwalk.config_loader import load_research_plan
from prodwalk.credentials import CredentialStore
from prodwalk.llm_adapters import OpenAIResponsesChatModel
from prodwalk.models import EvidenceItem, ProductTarget, Scenario, WalkStep, WalkthroughResult, utc_now
from browser_use.llm.messages import SystemMessage, UserMessage


class MvpPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_mock_pipeline_generates_artifacts(self) -> None:
        plan = load_research_plan(Path("examples") / "research_plan.json")
        with tempfile.TemporaryDirectory() as tmp:
            director = ResearchDirector(MockBrowserWalker(), concurrency=2)
            paths = await director.run(plan, tmp)

            self.assertTrue(paths["evidence"].exists())
            self.assertTrue(paths["report"].exists())
            self.assertTrue(paths["evaluation"].exists())

            payload = json.loads(paths["evidence"].read_text(encoding="utf-8"))
            self.assertEqual(len(payload["results"]), len(plan.products) * len(plan.scenarios))
            self.assertGreater(len(payload["evidence"]), 0)

            evaluation = json.loads(paths["evaluation"].read_text(encoding="utf-8"))
            self.assertIn("overall_score", evaluation)
            self.assertGreaterEqual(evaluation["overall_score"], 0)


class EvidenceExtractorTest(unittest.TestCase):
    def test_archives_browser_screenshots_into_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "browser_temp"
            source_dir.mkdir()
            source = source_dir / "step_1.png"
            source.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            step_evidence = EvidenceItem(
                id="ev-example-scenario-step-1",
                product="Example",
                scenario_id="scenario",
                kind="browser_step",
                title="Browser step 1",
                summary="Loaded the dashboard.",
                screenshot=str(source),
                data={"screenshot_path": str(source)},
            )
            run_evidence = EvidenceItem(
                id="ev-example-scenario-browser-use-local",
                product="Example",
                scenario_id="scenario",
                kind="browser_run",
                title="browser-use run",
                summary="Completed.",
                data={"screenshot_paths": [str(source)]},
            )
            result = WalkthroughResult(
                product="Example",
                product_kind="owned",
                scenario_id="scenario",
                scenario_title="Scenario",
                status="completed",
                started_at=utc_now(),
                completed_at=utc_now(),
                steps=[
                    WalkStep(
                        index=1,
                        action="Open dashboard",
                        status="passed",
                        observation="Loaded the dashboard.",
                        screenshot=str(source),
                        evidence_ids=[step_evidence.id],
                    )
                ],
                evidence=[run_evidence, step_evidence],
            )

            archived = EvidenceExtractor().archive_screenshots([result], root / "run")

            expected = "screenshots/ev-example-scenario-step-1.png"
            self.assertEqual(len(archived), 1)
            self.assertEqual(step_evidence.screenshot, expected)
            self.assertEqual(step_evidence.data["screenshot_path"], expected)
            self.assertEqual(result.steps[0].screenshot, expected)
            self.assertEqual(run_evidence.data["screenshot_paths"], [expected])
            self.assertTrue((root / "run" / expected).exists())


class BrowserUseLocalWalkerTest(unittest.IsolatedAsyncioTestCase):
    def test_classifies_browser_errors_as_blocked(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        status, reason = walker._classify_run("", {"errors": ["404 page not found"]})

        self.assertEqual(status, "blocked")
        self.assertIn("404", reason)

    def test_recovered_intermediate_timeout_is_completed(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        status, reason = walker._classify_run(
            '{"completed": true, "blockers": []}',
            {"errors": ["LLM call timed out after 75 seconds. Keep your thinking and output short."]},
        )

        self.assertEqual(status, "completed")
        self.assertEqual(reason, "")

    def test_history_file_names_include_task_hash(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        first = walker._history_file_for_task(
            "Open https://example.com and perform a product walkthrough. Scenario A"
        )
        second = walker._history_file_for_task(
            "Open https://example.com and perform a product walkthrough. Scenario B"
        )

        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("browser_use_history_"))

    def test_uses_responses_adapter_for_responses_wire_api(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        walker.provider = "openai"
        walker.model = "gpt-test"
        walker.openai_base_url = "https://example.test/v1"
        walker.openai_wire_api = "responses"
        walker.codex_config = {"api_key": "test-key"}

        llm = walker._load_llm()

        self.assertIsInstance(llm, OpenAIResponsesChatModel)

    def test_responses_adapter_moves_system_message_to_instructions(self) -> None:
        llm = OpenAIResponsesChatModel(model="gpt-test", api_key="test-key")
        instructions, input_messages = llm._split_instructions(
            [
                SystemMessage(content="System rules"),
                UserMessage(content="User request"),
            ]
        )

        self.assertEqual(instructions, "System rules")
        self.assertEqual(len(input_messages), 1)

    def test_responses_adapter_extracts_first_json_object(self) -> None:
        class Payload(BaseModel):
            completed: bool

        llm = OpenAIResponsesChatModel(model="gpt-test", api_key="test-key")
        text = '{"completed": true}\n{"extra": "trailing"}'

        parsed = Payload.model_validate_json(llm._first_json_object(text))

        self.assertTrue(parsed.completed)

    async def test_recovered_browser_use_errors_do_not_become_product_blockers(self) -> None:
        class RecoveredWalker(BrowserUseLocalWalker):
            async def _run_browser_use_local(self, task: str) -> dict:
                return {
                    "output": '{"completed": true}',
                    "errors": ["1 validation error for AgentOutput"],
                    "observations": [
                        {
                            "step_number": 1,
                            "action_names": [],
                            "summary": "Error: 1 validation error for AgentOutput",
                            "url": "https://example.test",
                            "title": "Example",
                            "screenshot_path": None,
                            "errors": ["1 validation error for AgentOutput"],
                        },
                        {
                            "step_number": 2,
                            "action_names": ["done"],
                            "summary": '{"completed": true}',
                            "url": "https://example.test",
                            "title": "Example",
                            "screenshot_path": None,
                            "errors": [],
                        },
                    ],
                    "step_count": 2,
                }

        walker = RecoveredWalker(max_steps=3)
        result = await walker.walk(
            ProductTarget(name="Example", url="https://example.test"),
            Scenario(
                id="smoke",
                title="Smoke",
                persona="PM",
                goal="Verify",
                steps=["Open page"],
                success_criteria=["Done"],
                observation_points=["Reliability"],
            ),
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.metrics["blocker_count"], 0)
        self.assertEqual(result.evidence[0].data["final_output"], '{"completed": true}')
        self.assertTrue(all(step.status == "passed" for step in result.steps))

    async def test_browser_use_timeout_returns_blocked_result(self) -> None:
        class SlowWalker(BrowserUseLocalWalker):
            async def _run_browser_use_local(self, task: str) -> dict:
                await asyncio.sleep(1)
                return {"output": '{"completed": true}'}

        walker = SlowWalker(max_steps=3, run_timeout_sec=0.01)
        result = await walker.walk(
            ProductTarget(name="Example", url="https://example.test"),
            Scenario(
                id="slow",
                title="Slow",
                persona="PM",
                goal="Verify timeout handling",
                steps=["Open page"],
                success_criteria=["Done"],
                observation_points=["Reliability"],
            ),
        )

        self.assertEqual(result.status, "blocked")
        self.assertTrue(result.metrics["timed_out"])
        self.assertIn("timed out", result.errors[0])
        self.assertEqual(result.metrics["completion_score"], 0.0)

    def test_task_includes_product_notes_and_external_link_guardrail(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        task = walker._build_task(
            ProductTarget(
                name="Example",
                url="https://example.test",
                notes="Stay inside first-party pages.",
            ),
            Scenario(
                id="guardrail",
                title="Guardrail",
                persona="PM",
                goal="Verify prompt guardrails",
                steps=["Open page"],
                success_criteria=["Done"],
                observation_points=["Reliability"],
            ),
        )

        self.assertIn("Product notes: Stay inside first-party pages.", task)
        self.assertIn("Do not open external documentation", task)

    def test_browser_runtime_paths_are_resolved_and_prepared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            walker = BrowserUseLocalWalker(
                max_steps=3,
                user_data_dir=str(root / "profile"),
                storage_state=str(root / "auth" / "storage_state.json"),
            )

            self.assertEqual(Path(walker.user_data_dir or "").resolve(), root / "profile")
            self.assertTrue((root / "profile").exists())
            self.assertEqual(Path(walker.storage_state or "").resolve(), root / "auth" / "storage_state.json")
            self.assertTrue((root / "auth").exists())

    def test_sensitive_data_is_loaded_from_credential_ref_env(self) -> None:
        previous = {
            "CLINK_UAT_ACCOUNT_USERNAME": os.environ.get("CLINK_UAT_ACCOUNT_USERNAME"),
            "CLINK_UAT_ACCOUNT_PASSWORD": os.environ.get("CLINK_UAT_ACCOUNT_PASSWORD"),
        }
        os.environ["CLINK_UAT_ACCOUNT_USERNAME"] = "user@example.test"
        os.environ["CLINK_UAT_ACCOUNT_PASSWORD"] = "pass"
        try:
            walker = BrowserUseLocalWalker(max_steps=3)
            task = (
                "Open https://uat-dashboard.clinkbill.com/analytics\n"
                "Safe credentials reference: CLINK_UAT_ACCOUNT."
            )
            sensitive_data = walker._sensitive_data_for_task(task)

            self.assertIn("uat-dashboard.clinkbill.com", sensitive_data)
            self.assertIn("*.clinkbill.com", sensitive_data)
            self.assertEqual(
                sensitive_data["uat-dashboard.clinkbill.com"]["clink_uat_account_username"],
                "user@example.test",
            )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_sensitive_text_is_redacted_before_artifacts(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        text = "Logged in as user@example.test"
        sensitive_data = {
            "example.test": {
                "test_username": "user@example.test",
                "test_password": "pass",
            }
        }

        redacted = walker._redact_sensitive_text(text, sensitive_data)

        self.assertNotIn("user@example.test", redacted)
        self.assertIn("<secret>test_username</secret>", redacted)

    def test_potential_api_tokens_are_redacted_before_artifacts(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        text = (
            "Secret Key sk_test_abcdefghijklmnopqrstuvwxyz "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890"
        )

        redacted = walker._redact_sensitive_text(text, {})

        self.assertNotIn("sk_test_abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz1234567890", redacted)
        self.assertIn("<secret>api_token</secret>", redacted)

    def test_sensitive_file_is_redacted_after_history_save(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text('{"state_message":"value=user@example.test"}', encoding="utf-8")

            walker._redact_sensitive_file(
                str(path),
                {"example.test": {"test_username": "user@example.test"}},
            )

            text = path.read_text(encoding="utf-8")
            self.assertNotIn("user@example.test", text)
            self.assertIn("<secret>test_username</secret>", text)

    def test_credential_store_round_trips_without_plaintext_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.json"
            store = CredentialStore(path=path)

            store.set(
                ref="TEST_ACCOUNT",
                site="https://example.test/login",
                username="user@example.test",
                password="secret-pass",
                notes="test only",
            )

            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("user@example.test", raw)
            self.assertNotIn("secret-pass", raw)

            credential = store.get("TEST_ACCOUNT")
            self.assertIsNotNone(credential)
            assert credential is not None
            self.assertEqual(credential.username, "user@example.test")
            self.assertEqual(credential.password, "secret-pass")
            self.assertEqual(credential.host, "example.test")

            rows = store.list()
            self.assertEqual(rows[0]["ref"], "TEST_ACCOUNT")
            self.assertNotIn("secret-pass", json.dumps(rows))

    def test_walker_loads_sensitive_data_from_credential_store(self) -> None:
        previous = os.environ.get("PRODWALK_CREDENTIAL_STORE")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["PRODWALK_CREDENTIAL_STORE"] = str(Path(tmp) / "credentials.json")
                store = CredentialStore()
                store.set(
                    ref="TEST_ACCOUNT",
                    site="https://example.test/login",
                    username="user@example.test",
                    password="secret-pass",
                )

                walker = BrowserUseLocalWalker(max_steps=3)
                task = "Open https://example.test\nSafe credentials reference: TEST_ACCOUNT."
                sensitive_data = walker._sensitive_data_for_task(task)

                self.assertEqual(
                    sensitive_data["example.test"]["test_account_username"],
                    "user@example.test",
                )
                self.assertEqual(
                    sensitive_data["example.test"]["test_account_password"],
                    "secret-pass",
                )
        finally:
            if previous is None:
                os.environ.pop("PRODWALK_CREDENTIAL_STORE", None)
            else:
                os.environ["PRODWALK_CREDENTIAL_STORE"] = previous


class AuthSessionTest(unittest.TestCase):
    def test_auth_success_detects_same_host_after_login_redirect(self) -> None:
        self.assertTrue(
            is_auth_success_url(
                current_url="https://uat-dashboard.clinkbill.com/analytics",
                start_url="https://uat-dashboard.clinkbill.com/analytics",
                login_url_contains="/auth/login",
                success_url_contains=[],
            )
        )
        self.assertFalse(
            is_auth_success_url(
                current_url="https://uat-dashboard.clinkbill.com/auth/login",
                start_url="https://uat-dashboard.clinkbill.com/analytics",
                login_url_contains="/auth/login",
                success_url_contains=[],
            )
        )

    def test_auth_success_rejects_visible_login_form(self) -> None:
        self.assertFalse(
            is_auth_success_url(
                current_url="https://uat-dashboard.clinkbill.com/analytics",
                start_url="https://uat-dashboard.clinkbill.com/analytics",
                login_url_contains="/auth/login",
                success_url_contains=["/analytics"],
                has_login_form=True,
            )
        )

    def test_auth_success_supports_explicit_url_marker(self) -> None:
        self.assertTrue(
            is_auth_success_url(
                current_url="https://example.test/app/home",
                start_url="https://example.test/login",
                login_url_contains="/login",
                success_url_contains=["/app/"],
            )
        )

    def test_default_user_data_dir_uses_credential_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            os.chdir(tmp)
            try:
                path = resolve_user_data_dir(
                    None,
                    "CLINK_UAT_ACCOUNT",
                    "https://uat-dashboard.clinkbill.com/analytics",
                )
            finally:
                os.chdir(previous)

        self.assertTrue(str(path).endswith(str(Path(".prodwalk") / "browser-profiles" / "clink_uat_account")))


class ProductAnalystTest(unittest.TestCase):
    def test_extracts_findings_from_browser_use_final_summary(self) -> None:
        final_summary = {
            "completed": {"session": "completed"},
            "blockers": [
                "No hard blockers encountered during the inspected authenticated dashboard run.",
                "External documentation/help links were intentionally not opened per instruction.",
            ],
            "friction_points": [
                "Repeated page transitions showed previous page content under a spinner for several seconds.",
                "Developers displayed full API/secret key values in the UI.",
                "Operational pages expose Add, Export CSV, Submit Payout, Generate, Edit, Archive, Disable, and Save controls.",
            ],
            "top_recommendations": [
                "Improve route-loading feedback so the page title/content changes promptly.",
                "Mask secret/API values by default and require explicit reveal with audit logging.",
                "Separate read-only operational views from mutation/export controls.",
            ],
        }
        evidence = EvidenceItem(
            id="ev-example-browser-use-local",
            product="Example",
            scenario_id="scenario",
            kind="browser_run",
            title="browser-use run",
            summary="truncated",
            data={"final_output": json.dumps(final_summary)},
        )
        result = WalkthroughResult(
            product="Example",
            product_kind="owned",
            scenario_id="scenario",
            scenario_title="Scenario",
            status="completed",
            started_at=utc_now(),
            completed_at=utc_now(),
            steps=[],
            evidence=[evidence],
            metrics={"completion_score": 1.0, "blocker_count": 0, "friction_count": 0},
        )

        analysis = ProductAnalyst().analyze([result])[0]
        themes = {finding.theme for finding in analysis.findings}
        claims = " ".join(finding.claim for finding in analysis.findings)
        recommendations = " ".join(finding.recommendation for finding in analysis.findings)

        self.assertNotIn("Baseline pass", themes)
        self.assertIn("Navigation and loading feedback", themes)
        self.assertIn("Secret handling/admin safety", themes)
        self.assertIn("Permission and destructive controls", themes)
        self.assertNotIn("No hard access blocker", claims)
        self.assertIn("Mask secret/API values", recommendations)
        self.assertEqual(analysis.metrics["structured_findings"], 3)

    def test_private_data_claim_uses_secret_handling_fallback_recommendation(self) -> None:
        final_summary = {
            "friction_points": [
                "Some private account/contact data is visible in Settings and Customers; final reporting should avoid copying those values."
            ],
            "top_recommendations": [
                "Add external-link indicators and visible destination hints for Help Center and Contact support."
            ],
        }
        evidence = EvidenceItem(
            id="ev-private-data",
            product="Example",
            scenario_id="scenario",
            kind="browser_run",
            title="browser-use run",
            summary="",
            data={"final_output": json.dumps(final_summary)},
        )
        result = WalkthroughResult(
            product="Example",
            product_kind="owned",
            scenario_id="scenario",
            scenario_title="Scenario",
            status="completed",
            started_at=utc_now(),
            completed_at=utc_now(),
            steps=[],
            evidence=[evidence],
            metrics={"completion_score": 1.0},
        )

        finding = ProductAnalyst().analyze([result])[0].findings[0]

        self.assertEqual(finding.theme, "Secret handling/admin safety")
        self.assertIn("Mask sensitive values", finding.recommendation)


if __name__ == "__main__":
    unittest.main()
