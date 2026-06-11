from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    tomllib = None  # type: ignore[assignment]

from ..models import (
    EvidenceItem,
    ProductTarget,
    Scenario,
    WalkStep,
    WalkthroughResult,
    slugify,
    utc_now,
)
from ..credentials import CredentialStore, normalize_ref


class BrowserWalker(ABC):
    @abstractmethod
    async def walk(self, product: ProductTarget, scenario: Scenario) -> WalkthroughResult:
        raise NotImplementedError


class MockBrowserWalker(BrowserWalker):
    """Deterministic walker used to validate orchestration without a browser."""

    async def walk(self, product: ProductTarget, scenario: Scenario) -> WalkthroughResult:
        started_at = utc_now()
        steps: list[WalkStep] = []
        evidence: list[EvidenceItem] = []
        errors: list[str] = []
        friction_count = 0
        blocker_count = 0

        for index, action in enumerate(scenario.steps, start=1):
            await asyncio.sleep(0)
            status, observation = self._simulate_observation(product, scenario, action, index)
            if status == "friction":
                friction_count += 1
            if status == "blocked":
                blocker_count += 1
                errors.append(observation)

            evidence_id = f"ev-{slugify(product.name)}-{scenario.id}-{index}"
            item = EvidenceItem(
                id=evidence_id,
                product=product.name,
                scenario_id=scenario.id,
                kind="observation",
                title=f"Step {index}: {action}",
                summary=observation,
                url=product.url,
                data={
                    "action": action,
                    "status": status,
                    "observation_points": scenario.observation_points,
                    "mock": True,
                },
                confidence=0.65,
            )
            evidence.append(item)
            steps.append(
                WalkStep(
                    index=index,
                    action=action,
                    status=status,
                    observation=observation,
                    url=product.url,
                    elapsed_ms=900 + index * 120,
                    evidence_ids=[evidence_id],
                )
            )

        status = "completed" if blocker_count == 0 else "blocked"
        completed_at = utc_now()
        completion_score = max(0.0, 1.0 - blocker_count * 0.45 - friction_count * 0.12)
        metrics: dict[str, Any] = {
            "step_count": len(steps),
            "friction_count": friction_count,
            "blocker_count": blocker_count,
            "completion_score": round(completion_score, 2),
            "estimated_time_sec": round(sum(step.elapsed_ms for step in steps) / 1000, 1),
        }
        return WalkthroughResult(
            product=product.name,
            product_kind=product.kind,
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            steps=steps,
            evidence=evidence,
            metrics=metrics,
            errors=errors,
        )

    def _simulate_observation(
        self,
        product: ProductTarget,
        scenario: Scenario,
        action: str,
        index: int,
    ) -> tuple[str, str]:
        action_l = action.lower()
        product_seed = sum(ord(ch) for ch in product.name)
        scenario_seed = sum(ord(ch) for ch in scenario.id)

        if ("login" in action_l or "signup" in action_l) and not product.credentials_ref:
            return (
                "friction",
                "Account entry was inspected only as a public flow because no safe credentials were configured.",
            )
        if ("submit" in action_l or "confirm" in action_l) and (product_seed + scenario_seed) % 7 == 0:
            return (
                "blocked",
                "The flow could not be confirmed in mock mode; mark this step for a real browser replay.",
            )
        if index % 4 == 0:
            return (
                "friction",
                "The step appears to need extra guidance or clearer feedback based on the scenario heuristic.",
            )
        return (
            "passed",
            "The step was observable and produced enough evidence for downstream analysis.",
        )


class BrowserUseLocalWalker(BrowserWalker):
    """Adapter boundary for local open-source browser-use runs.

    This uses the installed browser-use package and a local Chrome/Edge browser.
    It still needs an LLM provider, unless provider is set to a local backend
    such as Ollama.
    """

    def __init__(
        self,
        model: str | None = None,
        max_steps: int = 25,
        run_timeout_sec: float | None = None,
        user_data_dir: str | None = None,
        storage_state: str | None = None,
    ) -> None:
        self.codex_config = self._load_codex_llm_config()
        self.provider = (os.getenv("BROWSER_USE_LLM_PROVIDER") or self.codex_config.get("provider") or "openai").lower()
        self.model = model or os.getenv("BROWSER_USE_MODEL") or self.codex_config.get("model") or self._default_model(self.provider)
        self.openai_base_url = os.getenv("BROWSER_USE_OPENAI_BASE_URL") or self.codex_config.get("base_url")
        self.openai_wire_api = (
            os.getenv("BROWSER_USE_OPENAI_WIRE_API") or self.codex_config.get("wire_api") or "chat"
        ).lower()
        self.max_steps = max_steps
        configured_timeout = run_timeout_sec if run_timeout_sec is not None else self._float_env(
            "BROWSER_USE_RUN_TIMEOUT_SEC"
        )
        self.run_timeout_sec = configured_timeout if configured_timeout and configured_timeout > 0 else None
        self.headless = self._bool_env("BROWSER_USE_HEADLESS", default=True)
        self.executable_path = os.getenv("BROWSER_USE_CHROME_PATH") or self._find_local_browser()
        self.user_data_dir = self._resolve_runtime_path(
            user_data_dir or os.getenv("BROWSER_USE_USER_DATA_DIR"),
            create_dir=True,
        )
        self.storage_state = self._resolve_runtime_path(
            storage_state
            or os.getenv("BROWSER_USE_STORAGE_STATE")
            or os.getenv("BROWSER_USE_STORAGE_STATE_PATH"),
            create_parent=True,
        )
        self.record_video_dir = os.getenv("BROWSER_USE_RECORD_VIDEO_DIR") or None

    async def walk(self, product: ProductTarget, scenario: Scenario) -> WalkthroughResult:
        started_at = utc_now()
        evidence_id = f"ev-{slugify(product.name)}-{scenario.id}-browser-use-local"
        task = self._build_task(product, scenario)
        errors: list[str] = []
        final_text = ""
        run_data: dict[str, Any] = {}
        status_reason = ""

        try:
            run_data = await self._run_with_optional_timeout(task)
            final_text = run_data["output"].strip()
            status, status_reason = self._classify_run(final_text, run_data)
            if status != "completed":
                errors.extend(run_data.get("errors", []))
                if not errors and status_reason:
                    errors.append(status_reason)
                final_text = final_text or status_reason
        except asyncio.TimeoutError:
            status = "blocked"
            status_reason = f"browser-use run timed out after {self.run_timeout_sec:g} seconds"
            errors.append(status_reason)
            final_text = (
                f"{status_reason}. The scenario was stopped so the full research report could still be generated."
            )
            run_data = {
                "output": final_text,
                "errors": [status_reason],
                "observations": [],
                "step_count": 0,
                "timed_out": True,
            }
        except Exception as exc:  # noqa: BLE001 - surfaced as walkthrough evidence.
            status = "blocked"
            errors.append(str(exc))
            final_text = f"browser-use run failed: {exc}"

        completed_at = utc_now()
        observations = run_data.get("observations", [])
        evidence = [
            EvidenceItem(
                id=evidence_id,
                product=product.name,
                scenario_id=scenario.id,
                kind="browser_run",
                title=f"browser-use run for {scenario.title}",
                summary=final_text[:2000],
                url=product.url,
                data={
                    "task": task,
                    "mode": "browser-use-local",
                    "final_output": final_text,
                    "model": self.model,
                    "provider": self.provider,
                    "base_url": self.openai_base_url,
                    "wire_api": self.openai_wire_api if self.provider == "openai" else None,
                    "config_source": self.codex_config.get("source"),
                    "executable_path": self.executable_path,
                    "headless": self.headless,
                    "run_timeout_sec": self.run_timeout_sec,
                    "user_data_dir": self.user_data_dir,
                    "storage_state": self.storage_state,
                    "timed_out": run_data.get("timed_out", False),
                    "history_file": run_data.get("history_file"),
                    "screenshot_paths": run_data.get("screenshot_paths", []),
                    "urls": run_data.get("urls", []),
                    "action_names": run_data.get("action_names", []),
                    "errors": run_data.get("errors", []),
                    "status_reason": status_reason,
                },
                confidence=0.8 if status == "completed" else 0.4,
            )
        ]

        steps: list[WalkStep] = []
        for index, observation in enumerate(observations[: self.max_steps], start=1):
            step_evidence_id = f"{evidence_id}-step-{index}"
            action_names = observation.get("action_names", [])
            action = ", ".join(action_names) if action_names else "Observe browser state"
            step_status = "blocked" if status == "blocked" and observation.get("errors") else "passed"
            evidence.append(
                EvidenceItem(
                    id=step_evidence_id,
                    product=product.name,
                    scenario_id=scenario.id,
                    kind="browser_step",
                    title=f"Browser step {observation.get('step_number', index)}",
                    summary=str(observation.get("summary", ""))[:1200],
                    url=str(observation.get("url", product.url)),
                    screenshot=observation.get("screenshot_path"),
                    data=observation,
                    confidence=0.75 if step_status == "passed" else 0.45,
                )
            )
            steps.append(
                WalkStep(
                    index=index,
                    action=action,
                    status=step_status,
                    observation=str(observation.get("summary", ""))[:1000],
                    url=str(observation.get("url", product.url)),
                    screenshot=observation.get("screenshot_path"),
                    evidence_ids=[step_evidence_id],
                )
            )

        if not steps:
            steps.append(
                WalkStep(
                    index=1,
                    action="Run browser-use task",
                    status=status,
                    observation=final_text[:1000],
                    url=product.url,
                    evidence_ids=[evidence_id],
                )
            )

        blocker_count = 1 if status == "blocked" else 0
        return WalkthroughResult(
            product=product.name,
            product_kind=product.kind,
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            steps=steps,
            evidence=evidence,
            metrics={
                "step_count": len(steps),
                "friction_count": 0,
                "blocker_count": blocker_count,
                "completion_score": 1.0 if status == "completed" else 0.0,
                "browser_steps": run_data.get("step_count", 0),
                "run_timeout_sec": self.run_timeout_sec,
                "timed_out": run_data.get("timed_out", False),
            },
            errors=errors,
        )

    async def _run_with_optional_timeout(self, task: str) -> dict[str, Any]:
        if not self.run_timeout_sec:
            return await self._run_browser_use_local(task)
        return await asyncio.wait_for(self._run_browser_use_local(task), timeout=self.run_timeout_sec)

    def _build_task(self, product: ProductTarget, scenario: Scenario) -> str:
        credential_placeholders = (
            self._credential_placeholders(product) if self._credentials_available(product.credentials_ref) else None
        )
        if credential_placeholders:
            safe_credentials = (
                f"Safe credentials reference: {product.credentials_ref}. "
                f"If login is required, use username placeholder "
                f"<secret>{credential_placeholders['username']}</secret> and password placeholder "
                f"<secret>{credential_placeholders['password']}</secret>. Do not reveal these values in the final summary."
            )
        elif product.credentials_ref:
            safe_credentials = (
                f"Safe credentials reference: {product.credentials_ref}, but no matching credential environment "
                "variables are available. Do not guess credentials or use private data."
            )
        else:
            safe_credentials = "No credentials are provided. Do not bypass login or use private data."
        steps = "\n".join(f"{idx}. {step}" for idx, step in enumerate(scenario.steps, start=1))
        criteria = "\n".join(f"- {item}" for item in scenario.success_criteria)
        points = "\n".join(f"- {item}" for item in scenario.observation_points)
        notes = f"\nProduct notes: {product.notes}" if product.notes else ""
        return f"""
Open {product.url} and perform a product walkthrough.

Product: {product.name}
Product type: {product.kind}
{notes}
Scenario: {scenario.title}
Persona: {scenario.persona}
Goal: {scenario.goal}
{safe_credentials}

Steps:
{steps}

Success criteria:
{criteria}

Observation points:
{points}

Return a concise JSON-like summary with: completed, blockers, friction_points,
notable_copy, urls_seen, and evidence_needed. Do not perform destructive actions,
payments, or irreversible account changes. Stay on the product's own allowed
domains. Do not open external documentation, GitHub, support, or provider links;
record visible link labels or URLs only when useful. If login verification,
Altcha, CAPTCHA, or a manual challenge blocks progress after one login submit
attempt, stop immediately and return a partial summary with
manual_verification_required: true. Do not repeatedly retry human verification
inside browser-use. If loading or an external-domain block prevents progress,
stop and return a partial summary instead of retrying indefinitely. Keep the run
focused and stop after roughly {self.max_steps} meaningful browser steps.
""".strip()

    async def _run_browser_use_local(self, task: str) -> dict[str, Any]:
        try:
            from browser_use import Agent, BrowserProfile  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "browser-use is not installed. Run `pip install -e .[browser-use-local]` "
                "or use `--mode mock`."
            ) from exc

        llm = self._load_llm()
        sensitive_data = self._sensitive_data_for_task(task)
        allowed_domains = self._allowed_domains_from_task(task)
        profile_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "executable_path": self.executable_path,
        }
        if allowed_domains:
            profile_kwargs["allowed_domains"] = allowed_domains
        if self.user_data_dir:
            profile_kwargs["user_data_dir"] = self.user_data_dir
        if self.storage_state:
            profile_kwargs["storage_state"] = self.storage_state
        if self.record_video_dir:
            profile_kwargs["record_video_dir"] = self.record_video_dir

        browser_profile = BrowserProfile(**profile_kwargs)
        history_file = self._history_file_for_task(task)
        agent = Agent(
            task=task,
            llm=llm,
            browser_profile=browser_profile,
            sensitive_data=sensitive_data or None,
            save_conversation_path=None,
            use_vision=True,
        )
        try:
            history = await agent.run(max_steps=self.max_steps)
        except asyncio.CancelledError:
            await self._stop_agent_after_cancel(agent)
            raise
        try:
            history.save_to_file(history_file, sensitive_data=sensitive_data or None)
            self._redact_sensitive_file(history_file, sensitive_data)
        except Exception:
            history_file = None
        observations = self._extract_observations(history_file)
        errors = [error for observation in observations for error in observation.get("errors", [])]

        return {
            "output": self._redact_sensitive_text(str(history.final_result() or ""), sensitive_data),
            "history_file": history_file,
            "screenshot_paths": history.screenshot_paths(),
            "urls": history.urls(),
            "action_names": history.action_names(),
            "step_count": history.number_of_steps(),
            "observations": observations,
            "errors": errors,
        }

    async def _stop_agent_after_cancel(self, agent: Any) -> None:
        stop = getattr(agent, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                pass

        close = getattr(agent, "close", None)
        if callable(close):
            try:
                result = close()
                if inspect.isawaitable(result):
                    await asyncio.wait_for(result, timeout=10)
            except Exception:
                pass

    def _credential_placeholders(self, product: ProductTarget) -> dict[str, str] | None:
        if not product.credentials_ref:
            return None
        ref = normalize_ref(product.credentials_ref)
        username = f"{ref}_username"
        password = f"{ref}_password"
        return {"username": username, "password": password}

    def _credentials_available(self, credentials_ref: str | None) -> bool:
        if not credentials_ref:
            return False
        username, password = self._credential_values_from_env(credentials_ref)
        if username and password:
            return True
        return CredentialStore().get(credentials_ref) is not None

    def _sensitive_data_for_task(self, task: str) -> dict[str, dict[str, str]]:
        url = self._first_url_from_task(task)
        if not url:
            return {}
        host = urlparse(url).netloc
        if not host:
            return {}

        refs = self._credential_refs_from_task(task)
        secrets: dict[str, str] = {}
        for ref in refs:
            normalized = normalize_ref(ref)
            username, password = self._credential_values_from_env(ref)
            if username and password:
                secrets[f"{normalized}_username"] = username
                secrets[f"{normalized}_password"] = password
                continue

            stored = CredentialStore().sensitive_data_for_ref(ref)
            if stored:
                return stored
        if not secrets:
            return {}

        domains = {host}
        parts = host.split(".")
        if len(parts) >= 2:
            domains.add(f"*.{'.'.join(parts[-2:])}")
        return {domain: dict(secrets) for domain in sorted(domains)}

    def _credential_values_from_env(self, credentials_ref: str) -> tuple[str | None, str | None]:
        normalized = normalize_ref(credentials_ref).upper()
        username = (
            os.getenv(f"{normalized}_USERNAME")
            or os.getenv(f"{normalized}_EMAIL")
            or os.getenv(f"{normalized}_USER")
        )
        password = os.getenv(f"{normalized}_PASSWORD")
        return username, password

    def _allowed_domains_from_task(self, task: str) -> list[str]:
        url = self._first_url_from_task(task)
        if not url:
            return []
        host = urlparse(url).netloc
        if not host:
            return []
        parts = host.split(".")
        parent_domain = ".".join(parts[-2:]) if len(parts) >= 2 else host
        domains = [host]
        if parent_domain != host:
            domains.append(f"*.{parent_domain}")
        extra = os.getenv("BROWSER_USE_ALLOWED_DOMAINS")
        if extra:
            domains.extend(item.strip() for item in extra.split(",") if item.strip())
        return domains

    def _first_url_from_task(self, task: str) -> str:
        for token in task.replace("\n", " ").split():
            if token.startswith("http://") or token.startswith("https://"):
                return token.rstrip(".,)")
        return ""

    def _credential_refs_from_task(self, task: str) -> list[str]:
        marker = "Safe credentials reference:"
        refs: list[str] = []
        for line in task.splitlines():
            if marker not in line:
                continue
            ref = line.split(marker, 1)[1].split(".", 1)[0].strip()
            if ref:
                refs.append(ref)
        return refs

    def _redact_sensitive_text(self, text: str, sensitive_data: dict[str, dict[str, str]]) -> str:
        redacted = text
        for values in sensitive_data.values():
            for key, secret in sorted(values.items(), key=lambda item: len(item[1]), reverse=True):
                if secret:
                    redacted = redacted.replace(secret, f"<secret>{key}</secret>")
        return self._redact_potential_secrets(redacted)

    def _redact_potential_secrets(self, text: str) -> str:
        redacted = text
        patterns = [
            r"\b(?:sk|pk)_(?:live|test|prod|uat)?_?[A-Za-z0-9][A-Za-z0-9_\-]{12,}\b",
            r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b",
            r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}",
        ]
        for pattern in patterns:
            redacted = re.sub(pattern, "<secret>api_token</secret>", redacted)

        labeled_key_pattern = re.compile(
            r"(?i)((?:secret|publishable)\s*key\s*[:=]?\s*)([A-Za-z0-9][A-Za-z0-9_\-]{12,})"
        )
        return labeled_key_pattern.sub(r"\1<secret>api_key</secret>", redacted)

    def _redact_sensitive_file(self, path: str | None, sensitive_data: dict[str, dict[str, str]]) -> None:
        if not path or not sensitive_data:
            return
        file_path = Path(path)
        if not file_path.exists():
            return
        text = file_path.read_text(encoding="utf-8")
        redacted = self._redact_sensitive_text(text, sensitive_data)
        if redacted != text:
            file_path.write_text(redacted, encoding="utf-8")

    def _classify_run(self, final_text: str, run_data: dict[str, Any]) -> tuple[str, str]:
        final = final_text.strip()
        final_lower = final.lower()
        explicit_blocked_markers = [
            '"completed": false',
            "completed: false",
            "'completed': false",
            '"status": "blocked"',
            '"status":"blocked"',
        ]
        for marker in explicit_blocked_markers:
            if marker in final_lower:
                return "blocked", f"browser-use final result reported a blocker: {marker}"

        fatal_final_markers = [
            "404 page not found",
            "net::err",
            "stopping due to",
        ]
        for marker in fatal_final_markers:
            if marker in final_lower:
                return "blocked", f"browser-use final result reported a blocker: {marker}"

        # browser-use can recover from intermediate step errors, including model-call
        # timeouts. A non-empty final result means the agent reached a terminal answer.
        if final:
            return "completed", ""

        errors = [str(error) for error in run_data.get("errors", []) if str(error).strip()]
        error_text = " ".join(errors).lower()
        error_markers = [
            "404 page not found",
            "net::err",
            "timeout",
            "timed out",
            "stopping due to",
        ]
        for marker in error_markers:
            if marker in error_text:
                return "blocked", f"browser-use reported a blocker: {marker}"
        if not final:
            return "blocked", "browser-use finished without a final result; inspect the saved history file."
        return "completed", ""

    def _history_file_for_task(self, task: str) -> str:
        digest = hashlib.sha1(task.encode("utf-8")).hexdigest()[:10]
        return f"browser_use_history_{slugify(task[:60])}_{digest}.json"

    def _extract_observations(self, history_file: str | None) -> list[dict[str, Any]]:
        if not history_file:
            return []
        path = Path(history_file)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        entries = payload.get("history", [])
        if not isinstance(entries, list):
            return []

        observations: list[dict[str, Any]] = []
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                continue
            state = entry.get("state") if isinstance(entry.get("state"), dict) else {}
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            results = entry.get("result") if isinstance(entry.get("result"), list) else []
            errors: list[str] = []
            summary_parts: list[str] = []
            for result in results:
                if not isinstance(result, dict):
                    continue
                error = result.get("error")
                if error:
                    errors.append(str(error))
                    summary_parts.append(f"Error: {error}")
                    continue
                for key in ("extracted_content", "long_term_memory"):
                    value = result.get(key)
                    if value:
                        summary_parts.append(str(value))

            action_names = self._action_names_from_entry(entry)
            observations.append(
                {
                    "step_number": metadata.get("step_number", index),
                    "action_names": action_names,
                    "summary": " | ".join(summary_parts)[:2000],
                    "url": state.get("url", ""),
                    "title": state.get("title", ""),
                    "screenshot_path": state.get("screenshot_path"),
                    "errors": errors,
                }
            )
        return observations

    def _action_names_from_entry(self, entry: dict[str, Any]) -> list[str]:
        model_output = entry.get("model_output")
        if not isinstance(model_output, dict):
            return []
        actions = model_output.get("action")
        if not isinstance(actions, list):
            return []
        names: list[str] = []
        for action in actions:
            if isinstance(action, dict):
                names.extend(str(name) for name in action.keys())
        return names

    def _load_llm(self) -> Any:
        api_key = os.getenv("BROWSER_USE_LLM_API_KEY")
        if self.provider == "openai":
            key = api_key or os.getenv("OPENAI_API_KEY") or self.codex_config.get("api_key")
            if not key:
                raise RuntimeError(
                    "OPENAI_API_KEY, BROWSER_USE_LLM_API_KEY, or Codex ~/.codex/auth.json OPENAI_API_KEY "
                    "is required for local OpenAI-compatible runs."
                )
            if self.openai_wire_api == "responses":
                from prodwalk.llm_adapters import OpenAIResponsesChatModel

                return OpenAIResponsesChatModel(
                    model=self.model,
                    api_key=key,
                    base_url=self.openai_base_url,
                    reasoning_effort=os.getenv("BROWSER_USE_REASONING_EFFORT") or "low",
                )
            from browser_use.llm.openai.chat import ChatOpenAI  # type: ignore

            return ChatOpenAI(model=self.model, api_key=key, base_url=self.openai_base_url)
        if self.provider == "anthropic":
            from browser_use.llm.anthropic.chat import ChatAnthropic  # type: ignore

            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY or BROWSER_USE_LLM_API_KEY is required for local Anthropic runs.")
            return ChatAnthropic(model=self.model, api_key=key)
        if self.provider == "google":
            from browser_use.llm.google.chat import ChatGoogle  # type: ignore

            key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GOOGLE_API_KEY, GEMINI_API_KEY, or BROWSER_USE_LLM_API_KEY is required for local Google runs.")
            return ChatGoogle(model=self.model, api_key=key)
        if self.provider == "ollama":
            from browser_use.llm.ollama.chat import ChatOllama  # type: ignore

            return ChatOllama(model=self.model, host=os.getenv("OLLAMA_HOST"))
        if self.provider == "openrouter":
            from browser_use.llm.openrouter.chat import ChatOpenRouter  # type: ignore

            key = api_key or os.getenv("OPENROUTER_API_KEY")
            if not key:
                raise RuntimeError("OPENROUTER_API_KEY or BROWSER_USE_LLM_API_KEY is required for local OpenRouter runs.")
            return ChatOpenRouter(model=self.model, api_key=key)
        raise RuntimeError(f"Unsupported BROWSER_USE_LLM_PROVIDER: {self.provider}")

    def _load_codex_llm_config(self) -> dict[str, str]:
        if self._bool_env("BROWSER_USE_INHERIT_CODEX", default=True) is False:
            return {}
        codex_home = Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")
        config_path = codex_home / "config.toml"
        auth_path = codex_home / "auth.json"
        data: dict[str, Any] = {}
        if tomllib is not None and config_path.exists():
            try:
                data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        model = data.get("model")
        provider_name = data.get("model_provider")
        provider_config: dict[str, Any] = {}
        providers = data.get("model_providers")
        if isinstance(providers, dict) and isinstance(provider_name, str):
            maybe_provider = providers.get(provider_name)
            if isinstance(maybe_provider, dict):
                provider_config = maybe_provider

        auth: dict[str, Any] = {}
        if auth_path.exists():
            try:
                auth = json.loads(auth_path.read_text(encoding="utf-8"))
            except Exception:
                auth = {}

        result: dict[str, str] = {}
        api_key = auth.get("OPENAI_API_KEY")
        if isinstance(api_key, str) and api_key:
            result["api_key"] = api_key
        base_url = provider_config.get("base_url")
        wire_api = provider_config.get("wire_api")
        if isinstance(base_url, str) and base_url:
            result["base_url"] = base_url
        if isinstance(wire_api, str) and wire_api:
            result["wire_api"] = wire_api
        if isinstance(model, str) and model:
            result["model"] = model
        if provider_config.get("wire_api") in {"responses", "chat"} or provider_config.get("requires_openai_auth"):
            result["provider"] = "openai"
        if result:
            result["source"] = "codex"
        return result

    def _default_model(self, provider: str) -> str:
        defaults = {
            "openai": "gpt-4.1-mini",
            "anthropic": "claude-sonnet-4-5",
            "google": "gemini-2.5-flash",
            "ollama": "llama3.1",
            "openrouter": "openai/gpt-4.1-mini",
        }
        return defaults.get(provider, "gpt-4.1-mini")

    def _find_local_browser(self) -> str | None:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return None

    def _resolve_runtime_path(
        self,
        value: str | None,
        *,
        create_dir: bool = False,
        create_parent: bool = False,
    ) -> str | None:
        if not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        if create_dir:
            path.mkdir(parents=True, exist_ok=True)
        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _float_env(self, name: str) -> float | None:
        value = os.getenv(name)
        if not value:
            return None
        return float(value)

    def _bool_env(self, name: str, default: bool | None) -> bool | None:
        value = os.getenv(name)
        if value is None or value == "":
            return default
        return value.lower() in {"1", "true", "yes", "on"}
