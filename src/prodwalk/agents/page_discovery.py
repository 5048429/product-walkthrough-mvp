from __future__ import annotations

import asyncio
import os
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from ..models import utc_now


DEFAULT_KEEP_QUERY_KEYS = {"tab", "view", "section", "mode", "type", "status"}
TRACKING_QUERY_PREFIXES = ("utm_",)
SECRET_QUERY_MARKERS = ("token", "secret", "password", "key", "auth", "session", "credential")
SKIPPED_FILE_EXTENSIONS = {
    ".7z",
    ".avi",
    ".bmp",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}
DEFAULT_EXCLUDE_PATTERNS = [
    r"(?i)(?:^|/)(?:logout|log-out|signout|sign-out)(?:/|$)",
    r"(?i)(?:^|/)(?:delete|remove|archive|refund|void|payout|transfer)(?:/|$)",
    r"(?i)(?:^|/)(?:checkout|payment|payments)/(?:confirm|submit|complete)(?:/|$)",
]
UNSAFE_CLICK_TEXT_RE = re.compile(
    r"(?i)\b("
    r"delete|remove|archive|refund|void|payout|pay|transfer|submit|save|confirm|disable|enable|"
    r"revoke|logout|log\s*out|sign\s*out|export|download|import|upload|new|create|add|edit|"
    r"generate|invite|send|sync|connect|disconnect"
    r")\b"
)


@dataclass(slots=True)
class DiscoveryPage:
    url: str
    title: str = ""
    depth: int = 0
    source_url: str = ""
    source_label: str = ""
    links: list[str] = field(default_factory=list)
    click_candidates: list[dict[str, Any]] = field(default_factory=list)
    click_results: list[dict[str, Any]] = field(default_factory=list)
    discovered_at: str = field(default_factory=utc_now)
    errors: list[str] = field(default_factory=list)

    def to_observation(self, step_number: int) -> dict[str, Any]:
        source = f" from {self.source_url}" if self.source_url else ""
        return {
            "step_number": step_number,
            "action_names": ["discover_page"],
            "summary": f"Discovered page during full same-origin crawl{source}.",
            "url": self.url,
            "title": self.title,
            "screenshot_path": None,
            "errors": list(self.errors),
            "page_discovery": {
                "discovered_at": self.discovered_at,
                "depth": self.depth,
                "source_url": self.source_url,
                "source_label": self.source_label,
                "links": list(self.links),
                "click_candidates": list(self.click_candidates),
                "click_results": list(self.click_results),
            },
        }


def normalize_discovery_url(
    value: str,
    *,
    base_url: str | None = None,
    keep_query_keys: set[str] | None = None,
) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if base_url:
        raw = urljoin(base_url, raw)

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None

    host = parsed.hostname.lower()
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    keep_keys = keep_query_keys if keep_query_keys is not None else DEFAULT_KEEP_QUERY_KEYS
    query = _sanitize_query(parsed.query, keep_keys=keep_keys)
    fragment = _sanitize_fragment(parsed.fragment, keep_keys=keep_keys)

    return parsed._replace(netloc=netloc, path=path, params="", query=query, fragment=fragment).geturl()


class PageDiscoveryCrawler:
    """Deterministically discover same-origin product pages without using an LLM."""

    def __init__(
        self,
        *,
        headless: bool = True,
        executable_path: str | None = None,
        user_data_dir: str | None = None,
        storage_state: str | None = None,
        allowed_domains: list[str] | None = None,
        allowed_path_prefixes: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        keep_query_keys: list[str] | None = None,
        timeout_sec: float | None = None,
        max_pages: int | None = None,
        max_depth: int | None = None,
        max_clicks_per_page: int | None = None,
        click_navigation: bool | None = None,
    ) -> None:
        self.headless = headless
        self.executable_path = executable_path
        self.user_data_dir = user_data_dir
        self.storage_state = storage_state
        self.allowed_domains = [item.lower() for item in allowed_domains or [] if item.strip()]
        self.allowed_path_prefixes = [
            self._normalize_prefix(item) for item in (allowed_path_prefixes or []) if item.strip()
        ]
        configured_excludes = exclude_patterns if exclude_patterns is not None else self._csv_env(
            "BROWSER_USE_DISCOVERY_EXCLUDE_PATTERNS"
        )
        self.exclude_patterns = [re.compile(pattern) for pattern in (configured_excludes or DEFAULT_EXCLUDE_PATTERNS)]
        self.keep_query_keys = set(keep_query_keys or self._csv_env("BROWSER_USE_DISCOVERY_KEEP_QUERY_KEYS") or DEFAULT_KEEP_QUERY_KEYS)
        self.timeout_ms = int((timeout_sec or self._float_env("BROWSER_USE_DISCOVERY_TIMEOUT_SEC") or 20.0) * 1000)
        self.settle_ms = int(float(os.getenv("BROWSER_USE_DISCOVERY_SETTLE_MS", "500")))
        self.wait_for_network_idle = self._bool_env("BROWSER_USE_DISCOVERY_WAIT_FOR_NETWORK_IDLE", default=False)
        self.max_pages = max(1, max_pages or self._int_env("BROWSER_USE_DISCOVERY_MAX_PAGES") or 50)
        self.max_depth = max(0, max_depth if max_depth is not None else self._int_env("BROWSER_USE_DISCOVERY_MAX_DEPTH") or 3)
        self.max_clicks_per_page = max(
            0,
            max_clicks_per_page
            if max_clicks_per_page is not None
            else self._int_env("BROWSER_USE_DISCOVERY_MAX_CLICKS_PER_PAGE") or 50,
        )
        self.click_navigation = (
            click_navigation
            if click_navigation is not None
            else self._bool_env("BROWSER_USE_DISCOVERY_CLICK_NAVIGATION", default=True)
        )
        self._ephemeral_browser: Any | None = None

    async def discover(self, start_urls: list[str]) -> list[dict[str, Any]]:
        seeds = self._seed_urls(start_urls)
        if not seeds:
            return []

        try:
            from playwright.async_api import async_playwright  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return [
                asdict(DiscoveryPage(url=seeds[0], errors=[f"Playwright unavailable for page discovery: {exc}"]))
            ]

        pages: list[DiscoveryPage] = []
        seen: set[str] = set()
        queued: set[str] = set(seeds)
        queue: deque[tuple[str, int, str, str]] = deque((url, 0, "", "seed") for url in seeds)

        async with async_playwright() as playwright:
            context = None
            try:
                context = await self._new_context(playwright)
                page = context.pages[0] if getattr(context, "pages", None) else await context.new_page()
                while queue and len(pages) < self.max_pages:
                    url, depth, source_url, source_label = queue.popleft()
                    queued.discard(url)
                    if url in seen or not self.should_visit(url):
                        continue
                    seen.add(url)

                    discovered, links, click_candidates = await self._visit(page, url, depth, source_url, source_label)
                    pages.append(discovered)

                    if depth >= self.max_depth:
                        continue
                    self._enqueue_links(queue, queued, seen, links, depth + 1, discovered.url, "link")

                    if not self.click_navigation or self.max_clicks_per_page <= 0:
                        continue
                    candidates = click_candidates[: self.max_clicks_per_page]
                    for index, candidate in enumerate(candidates):
                        if len(pages) + len(queue) >= self.max_pages * 2:
                            break
                        clicked_links, click_result = await self._click_candidate(page, discovered.url, index, candidate)
                        if click_result:
                            discovered.click_results.append(click_result)
                        self._enqueue_links(
                            queue,
                            queued,
                            seen,
                            clicked_links,
                            depth + 1,
                            discovered.url,
                            self._candidate_label(candidate),
                        )
            except Exception as exc:  # noqa: BLE001
                if not pages:
                    pages.append(DiscoveryPage(url=seeds[0], errors=[f"Page discovery failed: {exc}"]))
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

        return [asdict(page) for page in pages[: self.max_pages]]

    def should_visit(self, url: str) -> bool:
        normalized = normalize_discovery_url(url, keep_query_keys=self.keep_query_keys)
        if not normalized:
            return False
        parsed = urlparse(normalized)
        if not self._host_allowed(parsed.hostname or ""):
            return False
        if self._has_skipped_extension(parsed.path):
            return False
        route = self._route_for_prefix_match(parsed)
        if self.allowed_path_prefixes and not any(route.startswith(prefix) for prefix in self.allowed_path_prefixes):
            return False
        return not any(pattern.search(normalized) or pattern.search(route) for pattern in self.exclude_patterns)

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

    async def _visit(
        self,
        page: Any,
        url: str,
        depth: int,
        source_url: str,
        source_label: str,
    ) -> tuple[DiscoveryPage, list[str], list[dict[str, Any]]]:
        errors: list[str] = []
        links: list[str] = []
        click_candidates: list[dict[str, Any]] = []
        current_url = url
        title = ""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.settle_ms > 0:
                await page.wait_for_timeout(min(self.settle_ms, self.timeout_ms))
            if self.wait_for_network_idle:
                with _suppress_playwright_timeout():
                    await page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 5000))
            current_url = normalize_discovery_url(str(getattr(page, "url", url)), keep_query_keys=self.keep_query_keys) or url
            title = await self._safe_title(page)
            links = await self._extract_links(page, current_url)
            click_candidates = await self._extract_click_candidates(page)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Discovery navigation issue: {exc}")
        return (
            DiscoveryPage(
                url=current_url,
                title=title,
                depth=depth,
                source_url=source_url,
                source_label=source_label,
                links=links[:80],
                click_candidates=[self._candidate_payload(candidate) for candidate in click_candidates[:80]],
                errors=errors,
            ),
            links,
            click_candidates,
        )

    async def _click_candidate(
        self,
        page: Any,
        source_url: str,
        candidate_index: int,
        candidate: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any]]:
        links: list[str] = []
        result = {
            **self._candidate_payload(candidate),
            "status": "blocked",
            "target_url": None,
            "same_url": False,
            "link_count": 0,
            "error": "",
        }
        try:
            await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.settle_ms > 0:
                await page.wait_for_timeout(min(self.settle_ms, self.timeout_ms))
            if self.wait_for_network_idle:
                with _suppress_playwright_timeout():
                    await page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 3000))
            candidates = await self._extract_click_candidates(page)
            if candidate_index >= len(candidates):
                result["error"] = "Candidate was no longer available after reload."
                return links, result
            refreshed = candidates[candidate_index]
            if self._candidate_label(refreshed) != self._candidate_label(candidate):
                result["error"] = "Candidate label changed after reload."
                return links, result
            selector = f'[data-prodwalk-discovery-id="{refreshed["id"]}"]'
            await page.locator(selector).first.click(timeout=min(self.timeout_ms, 3000))
            await asyncio.sleep(0.3)
            with _suppress_playwright_timeout():
                await page.wait_for_load_state("domcontentloaded", timeout=min(self.timeout_ms, 3000))
            if self.wait_for_network_idle:
                with _suppress_playwright_timeout():
                    await page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 3000))

            current_url = normalize_discovery_url(str(getattr(page, "url", "")), keep_query_keys=self.keep_query_keys)
            if current_url and current_url != source_url:
                links.append(current_url)
                result["target_url"] = current_url
            elif current_url:
                result["target_url"] = current_url
                result["same_url"] = True
            links.extend(await self._extract_links(page, current_url or source_url))
            result["status"] = "visited"
            result["link_count"] = len(links)
        except Exception:
            result["error"] = "Click did not complete within discovery timeout."
            return links, result
        return links, result

    async def _extract_links(self, page: Any, base_url: str) -> list[str]:
        script = r"""
() => {
  const attrs = ["href", "to", "data-href", "data-url", "data-route", "data-path"];
  const items = [];
  for (const el of Array.from(document.querySelectorAll("a[href], [href], [to], [data-href], [data-url], [data-route], [data-path]")).slice(0, 1500)) {
    for (const attr of attrs) {
      const value = el.getAttribute(attr);
      if (!value) continue;
      const trimmed = value.trim();
      if (!trimmed || (trimmed.startsWith("#") && !trimmed.startsWith("#/") && !trimmed.startsWith("#!/"))) continue;
      try {
        items.push(new URL(trimmed, document.baseURI).href);
      } catch {
        if (trimmed.startsWith("/")) items.push(window.location.origin + trimmed);
      }
    }
  }
  return Array.from(new Set(items));
}
"""
        try:
            values = await page.evaluate(script)
        except Exception:
            return []
        links: list[str] = []
        for value in values if isinstance(values, list) else []:
            normalized = normalize_discovery_url(str(value), base_url=base_url, keep_query_keys=self.keep_query_keys)
            if normalized and self.should_visit(normalized):
                links.append(normalized)
        return list(dict.fromkeys(links))

    async def _extract_click_candidates(self, page: Any) -> list[dict[str, Any]]:
        script = r"""
() => {
  const selectors = '[role="link"], [role="menuitem"], [role="tab"], button, [aria-label]';
  return Array.from(document.querySelectorAll(selectors)).slice(0, 500).map((el, index) => {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const text = (el.innerText || el.textContent || el.getAttribute("aria-label") || el.getAttribute("title") || "").trim();
    const id = `prodwalk-discovery-${index}`;
    el.setAttribute("data-prodwalk-discovery-id", id);
    return {
      id,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || "",
      text: text.slice(0, 120),
      aria_label: el.getAttribute("aria-label") || "",
      type: el.getAttribute("type") || "",
      href: el.getAttribute("href") || "",
      to: el.getAttribute("to") || "",
      data_route: el.getAttribute("data-route") || "",
      disabled: Boolean(el.disabled || el.getAttribute("aria-disabled") === "true"),
      inside_form: Boolean(el.closest("form")),
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none"
    };
  });
}
"""
        try:
            payload = await page.evaluate(script)
        except Exception:
            return []
        candidates = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
        return [candidate for candidate in candidates if self._is_safe_click_candidate(candidate)]

    def _enqueue_links(
        self,
        queue: deque[tuple[str, int, str, str]],
        queued: set[str],
        seen: set[str],
        links: list[str],
        depth: int,
        source_url: str,
        source_label: str,
    ) -> None:
        for link in links:
            normalized = normalize_discovery_url(link, keep_query_keys=self.keep_query_keys)
            if not normalized or normalized in seen or normalized in queued or not self.should_visit(normalized):
                continue
            queue.append((normalized, depth, source_url, source_label))
            queued.add(normalized)

    def _seed_urls(self, start_urls: list[str]) -> list[str]:
        seeds: list[str] = []
        for value in start_urls:
            normalized = normalize_discovery_url(value, keep_query_keys=self.keep_query_keys)
            if normalized and self.should_visit(normalized) and normalized not in seeds:
                seeds.append(normalized)
        return seeds[: self.max_pages]

    def _host_allowed(self, host: str) -> bool:
        normalized = host.lower()
        if not self.allowed_domains:
            return True
        for domain in self.allowed_domains:
            if domain.startswith("*."):
                suffix = domain[2:]
                if normalized == suffix or normalized.endswith(f".{suffix}"):
                    return True
            elif normalized == domain:
                return True
        return False

    def _route_for_prefix_match(self, parsed: Any) -> str:
        fragment = parsed.fragment
        if fragment.startswith("/") or fragment.startswith("!/"):
            route = f"#{fragment}" if fragment.startswith("/") else f"#{fragment}"
            return self._normalize_prefix(route)
        return self._normalize_prefix(parsed.path or "/")

    def _normalize_prefix(self, value: str) -> str:
        prefix = value.strip()
        if not prefix:
            return "/"
        if prefix.startswith("#"):
            return prefix
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        if len(prefix) > 1 and prefix.endswith("/"):
            prefix = prefix.rstrip("/")
        return prefix

    def _has_skipped_extension(self, path: str) -> bool:
        lowered = path.lower()
        return any(lowered.endswith(ext) for ext in SKIPPED_FILE_EXTENSIONS)

    def _is_safe_click_candidate(self, candidate: dict[str, Any]) -> bool:
        if not candidate.get("visible") or candidate.get("disabled") or candidate.get("inside_form"):
            return False
        label = self._candidate_label(candidate)
        if not label or UNSAFE_CLICK_TEXT_RE.search(label):
            return False
        tag = str(candidate.get("tag") or "").lower()
        role = str(candidate.get("role") or "").lower()
        input_type = str(candidate.get("type") or "").lower()
        if input_type in {"submit", "reset", "button"} and role not in {"link", "menuitem", "tab"}:
            return False
        if candidate.get("href"):
            return False
        if candidate.get("to") or candidate.get("data_route"):
            return True
        return role in {"link", "menuitem", "tab"} or tag == "button"

    def _candidate_label(self, candidate: dict[str, Any]) -> str:
        return str(candidate.get("text") or candidate.get("aria_label") or "").strip()

    def _candidate_payload(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "label": self._candidate_label(candidate)[:120],
            "tag": str(candidate.get("tag") or "")[:40],
            "role": str(candidate.get("role") or "")[:40],
            "type": str(candidate.get("type") or "")[:40],
            "href": str(candidate.get("href") or "")[:240],
            "to": str(candidate.get("to") or "")[:240],
            "data_route": str(candidate.get("data_route") or "")[:240],
        }

    async def _safe_title(self, page: Any) -> str:
        try:
            return str(await page.title())
        except Exception:
            return ""

    def _csv_env(self, name: str) -> list[str]:
        value = os.getenv(name)
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _int_env(self, name: str) -> int | None:
        value = os.getenv(name)
        if not value:
            return None
        return int(value)

    def _float_env(self, name: str) -> float | None:
        value = os.getenv(name)
        if not value:
            return None
        return float(value)

    def _bool_env(self, name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None or value == "":
            return default
        return value.lower() in {"1", "true", "yes", "on"}


def _sanitize_query(query: str, *, keep_keys: set[str]) -> str:
    clean: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith(TRACKING_QUERY_PREFIXES):
            continue
        if any(marker in lowered for marker in SECRET_QUERY_MARKERS):
            continue
        if keep_keys and lowered not in keep_keys:
            continue
        clean.append((key, value))
    return urlencode(clean, doseq=True)


def _sanitize_fragment(fragment: str, *, keep_keys: set[str]) -> str:
    if not fragment:
        return ""
    if not (fragment.startswith("/") or fragment.startswith("!/")):
        return ""
    route, separator, query = fragment.partition("?")
    if not separator:
        return route
    safe_query = _sanitize_query(query, keep_keys=keep_keys)
    return f"{route}?{safe_query}" if safe_query else route


class _suppress_playwright_timeout:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> bool:
        return exc_type is asyncio.TimeoutError or getattr(exc_type, "__name__", "") == "TimeoutError"
