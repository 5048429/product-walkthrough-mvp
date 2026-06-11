from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from prodwalk.agents.director import ResearchDirector
from prodwalk.agents.walker import BrowserUseLocalWalker, MockBrowserWalker
from prodwalk.config_loader import load_research_plan
from prodwalk.credentials import CredentialStore
from prodwalk.llm_adapters import OpenAIResponsesChatModel
from prodwalk.models import ProductTarget, Scenario
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


class BrowserUseLocalWalkerTest(unittest.IsolatedAsyncioTestCase):
    def test_classifies_browser_errors_as_blocked(self) -> None:
        walker = BrowserUseLocalWalker(max_steps=3)
        status, reason = walker._classify_run("", {"errors": ["404 page not found"]})

        self.assertEqual(status, "blocked")
        self.assertIn("404", reason)

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
        self.assertTrue(all(step.status == "passed" for step in result.steps))

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


if __name__ == "__main__":
    unittest.main()
