from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..models import slugify, utc_now


class PageEvidenceCollector:
    """Collect page-level evidence with Playwright/CDP after browser-use visits pages."""

    def __init__(
        self,
        *,
        headless: bool = True,
        executable_path: str | None = None,
        user_data_dir: str | None = None,
        storage_state: str | None = None,
        timeout_ms: int | None = None,
        max_html_chars: int | None = None,
        redaction_values: list[str] | None = None,
    ) -> None:
        self.headless = headless
        self.executable_path = executable_path
        self.user_data_dir = user_data_dir
        self.storage_state = storage_state
        self.timeout_ms = timeout_ms or int(float(os.getenv("BROWSER_USE_PAGE_EVIDENCE_TIMEOUT_SEC", "20")) * 1000)
        self.settle_ms = int(float(os.getenv("BROWSER_USE_PAGE_EVIDENCE_SETTLE_MS", "700")))
        self.wait_for_network_idle = self._bool_env(
            "BROWSER_USE_PAGE_EVIDENCE_WAIT_FOR_NETWORK_IDLE",
            default=False,
        )
        self.max_html_chars = max_html_chars or int(os.getenv("BROWSER_USE_PAGE_EVIDENCE_MAX_HTML_CHARS", "2000000"))
        self.capture_viewport_screenshot = self._bool_env(
            "BROWSER_USE_PAGE_EVIDENCE_CAPTURE_VIEWPORT",
            default=False,
        )
        self._ephemeral_browser: Any | None = None
        self.redaction_values = sorted([value for value in redaction_values or [] if value], key=len, reverse=True)

    async def collect_for_observations(
        self,
        observations: list[dict[str, Any]],
        *,
        task_slug: str,
    ) -> list[dict[str, Any] | None]:
        targets = [self._target_for_observation(index, observation) for index, observation in enumerate(observations, start=1)]
        if not any(target["url"] for target in targets):
            return [None for _ in observations]

        try:
            from playwright.async_api import async_playwright  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return [self._error_result(target, f"Playwright unavailable: {exc}") if target["url"] else None for target in targets]

        output_root = Path(tempfile.mkdtemp(prefix="prodwalk-page-evidence-"))
        results: list[dict[str, Any] | None] = [None for _ in observations]

        async with async_playwright() as playwright:
            context = None
            try:
                context = await self._new_context(playwright)
                page = context.pages[0] if getattr(context, "pages", None) else await context.new_page()
                for offset, target in enumerate(targets):
                    if not target["url"]:
                        continue
                    capture_dir = output_root / self._capture_dir_name(task_slug, target)
                    capture_dir.mkdir(parents=True, exist_ok=True)
                    results[offset] = await self._capture_page(page, capture_dir, target)
            except Exception as exc:  # noqa: BLE001 - collection is best-effort evidence.
                for offset, target in enumerate(targets):
                    if target["url"] and results[offset] is None:
                        results[offset] = self._error_result(target, f"Page evidence collection failed: {exc}")
            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                if self._ephemeral_browser is not None:
                    try:
                        await self._ephemeral_browser.close()
                    except Exception:
                        pass
                    self._ephemeral_browser = None
        return results

    async def _new_context(self, playwright: Any) -> Any:
        launch_options = {
            "headless": self.headless,
            "executable_path": self.executable_path,
        }
        launch_options = {key: value for key, value in launch_options.items() if value is not None}
        if self.user_data_dir:
            return await playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                viewport={"width": 1440, "height": 1000},
                **launch_options,
            )

        browser = await playwright.chromium.launch(**launch_options)
        context_options: dict[str, Any] = {"viewport": {"width": 1440, "height": 1000}}
        if self.storage_state:
            context_options["storage_state"] = self.storage_state
        context = await browser.new_context(**context_options)
        self._ephemeral_browser = browser
        return context

    async def _capture_page(self, page: Any, capture_dir: Path, target: dict[str, Any]) -> dict[str, Any]:
        console_log: list[dict[str, Any]] = []
        network_log: list[dict[str, Any]] = []
        page_errors: list[str] = []

        def on_console(message: Any) -> None:
            console_log.append(
                {
                    "type": str(getattr(message, "type", "")),
                    "text": self._redact_text(str(getattr(message, "text", "")))[:4000],
                    "location": self._jsonable(getattr(message, "location", None)),
                }
            )

        def on_page_error(error: Exception) -> None:
            page_errors.append(self._redact_text(str(error))[:4000])

        def on_request_failed(request: Any) -> None:
            failure = request.failure if not callable(request.failure) else request.failure()
            network_log.append(
                {
                    "event": "requestfailed",
                    "method": str(getattr(request, "method", "")),
                    "url": self._safe_url(str(getattr(request, "url", ""))),
                    "resource_type": str(getattr(request, "resource_type", "")),
                    "failure": self._redact_text(str(failure))[:1000],
                }
            )

        def on_response(response: Any) -> None:
            request = getattr(response, "request", None)
            network_log.append(
                {
                    "event": "response",
                    "status": int(getattr(response, "status", 0) or 0),
                    "url": self._safe_url(str(getattr(response, "url", ""))),
                    "request_method": str(getattr(request, "method", "")) if request is not None else "",
                    "resource_type": str(getattr(request, "resource_type", "")) if request is not None else "",
                }
            )

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)

        errors: list[str] = []
        started_at = utc_now()
        try:
            await page.goto(target["url"], wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.settle_ms > 0:
                await page.wait_for_timeout(min(self.settle_ms, self.timeout_ms))
            await self._wait_for_page_ready(page)
            if self.wait_for_network_idle:
                with suppress_timeout():
                    await page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 5000))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Navigation/capture load issue: {exc}")

        files: dict[str, str] = {}
        metadata: dict[str, Any] = {
            "schema_version": "1.0",
            "captured_at": utc_now(),
            "started_at": started_at,
            "step_number": target["step_number"],
            "source_url": self._safe_url(target["url"]),
            "url": self._safe_url(str(getattr(page, "url", target["url"]))),
            "title": self._redact_text(await self._safe_page_title(page)),
            "viewport": await self._safe_viewport(page),
            "errors": errors,
            "page_errors": page_errors,
        }

        files.update(await self._write_text_artifact(capture_dir, "page.html", await self._safe_html(page)))
        files.update(await self._write_json_artifact(capture_dir, "text.json", await self._safe_text_snapshot(page)))
        files.update(await self._write_json_artifact(capture_dir, "elements.json", await self._safe_elements(page)))
        files.update(await self._write_json_artifact(capture_dir, "network_log.json", {"items": network_log}))
        files.update(await self._write_json_artifact(capture_dir, "console_log.json", {"items": console_log, "page_errors": page_errors}))
        files.update(await self._write_json_artifact(capture_dir, "dom_snapshot.json", await self._safe_dom_snapshot(page)))
        files.update(await self._write_json_artifact(capture_dir, "accessibility_tree.json", await self._safe_accessibility_tree(page)))

        screenshot_path = (
            await self._safe_screenshot(page, capture_dir / "viewport.png", full_page=False)
            if self.capture_viewport_screenshot
            else None
        )
        full_page_screenshot_path = await self._safe_screenshot(page, capture_dir / "full_page.png", full_page=True)
        if screenshot_path:
            files["viewport_screenshot"] = screenshot_path.name
        if full_page_screenshot_path:
            files["full_page_screenshot"] = full_page_screenshot_path.name

        metadata["files"] = files
        manifest_path = capture_dir / "manifest.json"
        manifest_path.write_text(json.dumps(self._jsonable(metadata), indent=2, ensure_ascii=False), encoding="utf-8")

        artifact_paths = [str(capture_dir / filename) for filename in files.values() if not filename.endswith(".png")]
        artifact_paths.append(str(manifest_path))
        screenshot_paths = [str(path) for path in (screenshot_path, full_page_screenshot_path) if path is not None]
        result = {
            "status": "completed" if not errors else "partial",
            "captured_at": metadata["captured_at"],
            "url": metadata["url"],
            "title": metadata["title"],
            "manifest_path": str(manifest_path),
            "artifact_paths": artifact_paths,
            "screenshot_paths": screenshot_paths,
            "viewport_screenshot_path": str(screenshot_path) if screenshot_path else None,
            "full_page_screenshot_path": str(full_page_screenshot_path) if full_page_screenshot_path else None,
            "network_event_count": len(network_log),
            "console_message_count": len(console_log),
            "page_error_count": len(page_errors),
            "errors": errors,
        }
        for event_name, handler in (
            ("console", on_console),
            ("pageerror", on_page_error),
            ("requestfailed", on_request_failed),
            ("response", on_response),
        ):
            try:
                page.remove_listener(event_name, handler)
            except Exception:
                pass
        return result

    async def _safe_page_title(self, page: Any) -> str:
        try:
            return str(await page.title())
        except Exception:
            return ""

    async def _wait_for_page_ready(self, page: Any) -> None:
        ready_script = r"""
() => {
  const body = document.body;
  if (!body) return false;
  const text = (body.innerText || "").replace(/\s+/g, " ").trim();
  const interactiveCount = document.querySelectorAll('a, button, input, select, textarea, [role], [aria-label], summary').length;
  const loadingText = /^(clink|loading|加载中|请稍候|please wait)$/i.test(text);
  return (text.length > 30 || interactiveCount > 2) && !loadingText;
}
"""
        deadline_ms = min(self.timeout_ms, int(float(os.getenv("BROWSER_USE_PAGE_EVIDENCE_READY_TIMEOUT_SEC", "8")) * 1000))
        if deadline_ms <= 0:
            return
        with suppress_timeout():
            await page.wait_for_function(ready_script, timeout=deadline_ms, polling=250)

    async def _safe_viewport(self, page: Any) -> dict[str, Any]:
        try:
            return await page.evaluate(
                "() => ({ width: window.innerWidth, height: window.innerHeight, deviceScaleFactor: window.devicePixelRatio })"
            )
        except Exception:
            return {}

    async def _safe_html(self, page: Any) -> str:
        try:
            html = await page.content()
        except Exception as exc:  # noqa: BLE001
            return f"<!-- page.content failed: {self._redact_text(str(exc))} -->"
        redacted = self._redact_text(html)
        if len(redacted) > self.max_html_chars:
            return redacted[: self.max_html_chars] + "\n<!-- truncated by prodwalk page evidence collector -->"
        return redacted

    async def _safe_text_snapshot(self, page: Any) -> dict[str, Any]:
        try:
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception as exc:  # noqa: BLE001
            return {"error": self._redact_text(str(exc))}
        return {"text": self._redact_text(str(text))}

    async def _safe_elements(self, page: Any) -> dict[str, Any]:
        script = r"""
() => {
  const candidates = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role], [aria-label], summary'));
  return candidates.slice(0, 800).map((el) => {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim();
    return {
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      text: text.slice(0, 300),
      aria_label: el.getAttribute('aria-label') || '',
      placeholder: el.getAttribute('placeholder') || '',
      name: el.getAttribute('name') || '',
      type: el.getAttribute('type') || '',
      href: el instanceof HTMLAnchorElement ? el.href : '',
      to: el.getAttribute('to') || '',
      data_href: el.getAttribute('data-href') || '',
      data_url: el.getAttribute('data-url') || '',
      data_route: el.getAttribute('data-route') || '',
      data_path: el.getAttribute('data-path') || '',
      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
      rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
    };
  });
}
"""
        try:
            payload = await page.evaluate(script)
        except Exception as exc:  # noqa: BLE001
            return {"error": self._redact_text(str(exc)), "items": []}
        return {"items": self._redact_jsonish(payload)}

    async def _safe_dom_snapshot(self, page: Any) -> dict[str, Any]:
        try:
            session = await page.context.new_cdp_session(page)
            payload = await session.send(
                "DOMSnapshot.captureSnapshot",
                {"computedStyles": ["display", "visibility", "position", "z-index", "color", "background-color"]},
            )
            await session.detach()
            return self._redact_jsonish(payload)
        except Exception as exc:  # noqa: BLE001
            return {"error": self._redact_text(str(exc))}

    async def _safe_accessibility_tree(self, page: Any) -> dict[str, Any]:
        try:
            session = await page.context.new_cdp_session(page)
            payload = await session.send("Accessibility.getFullAXTree")
            await session.detach()
            return self._redact_jsonish(payload)
        except Exception as exc:  # noqa: BLE001
            return {"error": self._redact_text(str(exc))}

    async def _safe_screenshot(self, page: Any, path: Path, *, full_page: bool) -> Path | None:
        try:
            await page.screenshot(path=str(path), full_page=full_page, timeout=self.timeout_ms)
            return path
        except Exception:
            return None

    async def _write_json_artifact(self, directory: Path, filename: str, payload: Any) -> dict[str, str]:
        path = directory / filename
        path.write_text(json.dumps(self._jsonable(payload), indent=2, ensure_ascii=False), encoding="utf-8")
        return {Path(filename).stem: filename}

    async def _write_text_artifact(self, directory: Path, filename: str, text: str) -> dict[str, str]:
        path = directory / filename
        path.write_text(text, encoding="utf-8")
        return {Path(filename).stem: filename}

    def _target_for_observation(self, index: int, observation: dict[str, Any]) -> dict[str, Any]:
        url = str(observation.get("url") or "").strip()
        if not self._is_http_url(url):
            url = ""
        return {
            "step_number": observation.get("step_number", index),
            "url": url,
        }

    def _capture_dir_name(self, task_slug: str, target: dict[str, Any]) -> str:
        digest = hashlib.sha1(f"{target['step_number']}|{target['url']}".encode("utf-8")).hexdigest()[:8]
        parsed = urlparse(str(target["url"]))
        host = slugify(parsed.netloc or "page")
        return f"{slugify(task_slug)[:40]}-step-{target['step_number']}-{host}-{digest}"

    def _error_result(self, target: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "captured_at": utc_now(),
            "url": self._safe_url(str(target.get("url") or "")),
            "title": "",
            "manifest_path": None,
            "artifact_paths": [],
            "screenshot_paths": [],
            "network_event_count": 0,
            "console_message_count": 0,
            "page_error_count": 0,
            "errors": [self._redact_text(message)],
        }

    def _redact_jsonish(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._redact_jsonish(item) for item in value]
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                lowered = key_text.lower()
                if any(marker in lowered for marker in ("authorization", "cookie", "set-cookie", "password", "token", "secret", "api_key")):
                    redacted[key_text] = "<redacted>"
                else:
                    redacted[key_text] = self._redact_jsonish(item)
            return redacted
        if isinstance(value, str):
            return self._redact_text(value)
        return value

    def _redact_text(self, text: str) -> str:
        redacted = str(text)
        for value in self.redaction_values:
            redacted = redacted.replace(value, "<redacted>")
        patterns = [
            r"<secret>.*?</secret>",
            r"\b(?:sk|pk)_(?:live|test|prod|uat)?_?[A-Za-z0-9][A-Za-z0-9_\-]{12,}\b",
            r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b",
            r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}",
            r"(?i)((?:password|token|secret|credential|api[_ -]?key)\s*[:=]\s*)([^\s\"'<>;,]+)",
        ]
        for pattern in patterns:
            redacted = re.sub(pattern, lambda match: f"{match.group(1)}<redacted>" if match.lastindex else "<redacted>", redacted)
        return redacted

    def _safe_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ""
        clean_query: list[str] = []
        for part in parsed.query.split("&"):
            if not part:
                continue
            key = part.split("=", 1)[0].lower()
            if any(marker in key for marker in ("token", "secret", "password", "key", "auth", "session")):
                continue
            clean_query.append(part)
        return parsed._replace(query="&".join(clean_query)).geturl()

    def _is_http_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        if isinstance(value, tuple):
            return [self._jsonable(item) for item in value]
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    def _bool_env(self, name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None or value == "":
            return default
        return value.lower() in {"1", "true", "yes", "on"}


class suppress_timeout:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> bool:
        return exc_type is asyncio.TimeoutError
