from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from .agents.director import ResearchDirector
from .agents.walker import BrowserUseLocalWalker, BrowserWalker, MockBrowserWalker
from .auth_session import (
    AuthSessionRequest,
    add_auth_session_subcommand,
    ensure_auth_session,
    handle_auth_session_command,
    run_manual_auth_session,
    resolve_user_data_dir,
)
from .config_loader import load_research_plan
from .credentials import add_credential_subcommands, handle_credential_command
from .models import ProductTarget, ResearchPlan, Scenario, WalkthroughResult


def main() -> None:
    parser = argparse.ArgumentParser(description="Run product walkthrough research MVP.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a research plan")
    run_parser.add_argument("--config", required=True, help="Path to research plan JSON")
    run_parser.add_argument("--out", default="runs", help="Output directory root")
    run_parser.add_argument("--mode", choices=["mock", "browser-use", "browser-use-local"], default="mock")
    run_parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Parallel walkthrough count. Defaults to 1 for browser-use and 3 for mock.",
    )
    run_parser.add_argument("--browser-model", default=None)
    run_parser.add_argument(
        "--report-language",
        choices=["en", "zh"],
        default=None,
        help="Language for the generated Markdown report. Defaults to the config value or en.",
    )
    run_parser.add_argument("--browser-max-steps", type=int, default=25)
    run_parser.add_argument(
        "--browser-timeout-sec",
        type=float,
        default=600.0,
        help="Maximum seconds per browser-use scenario. Use 0 to disable.",
    )
    run_parser.add_argument(
        "--browser-user-data-dir",
        default=None,
        help="Browser profile directory for local browser-use runs.",
    )
    run_parser.add_argument(
        "--browser-storage-state",
        default=None,
        help="Storage state JSON file for reusing authenticated sessions.",
    )
    run_parser.add_argument(
        "--browser-discover-all-pages",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="After browser-use finishes, crawl same-origin pages and collect page evidence for discovered pages.",
    )
    run_parser.add_argument(
        "--browser-discovery-max-pages",
        type=int,
        default=None,
        help="Maximum same-origin pages to discover when full-page discovery is enabled.",
    )
    run_parser.add_argument(
        "--browser-discovery-max-depth",
        type=int,
        default=None,
        help="Maximum link depth for same-origin page discovery.",
    )
    run_parser.add_argument(
        "--verification-mode",
        choices=["auto", "off"],
        default="auto",
        help="Auto-check login state before browser-use runs and pause for manual verification when needed.",
    )
    run_parser.add_argument(
        "--verification-timeout-sec",
        type=float,
        default=300.0,
        help="Maximum seconds to wait for manual login if automatic success detection is used.",
    )
    run_parser.add_argument(
        "--verification-success-url-contains",
        action="append",
        default=[],
        help="URL substring that marks manual verification/login success. Can be passed multiple times.",
    )
    run_parser.add_argument(
        "--verification-login-url-contains",
        default="/auth/login",
        help="URL substring treated as the login page during verification preflight.",
    )
    add_auth_session_subcommand(subparsers)
    add_credential_subcommands(subparsers)

    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(_run(args))
    elif args.command == "auth-session":
        handle_auth_session_command(args)
    elif args.command == "credentials":
        handle_credential_command(args)


async def _run(args: argparse.Namespace) -> None:
    plan = load_research_plan(args.config)
    is_browser_use = args.mode in {"browser-use", "browser-use-local"}
    concurrency = args.concurrency if args.concurrency is not None else (1 if is_browser_use else 3)
    browser_user_data_dir, browser_storage_state = await _prepare_verification_checkpoints(plan, args, is_browser_use)
    walker = (
        BrowserUseLocalWalker(
            model=args.browser_model,
            max_steps=args.browser_max_steps,
            run_timeout_sec=args.browser_timeout_sec,
            user_data_dir=browser_user_data_dir,
            storage_state=browser_storage_state,
            discover_all_pages=args.browser_discover_all_pages,
            discovery_max_pages=args.browser_discovery_max_pages,
            discovery_max_depth=args.browser_discovery_max_depth,
        )
        if is_browser_use
        else MockBrowserWalker()
    )
    if is_browser_use and args.verification_mode == "auto":
        walker = HumanVerificationRetryWalker(
            inner=walker,
            user_data_dir=browser_user_data_dir,
            storage_state=browser_storage_state,
            success_url_contains=list(args.verification_success_url_contains or []),
            login_url_contains=args.verification_login_url_contains,
            timeout_sec=args.verification_timeout_sec,
        )
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) / f"run-{timestamp}"
    director = ResearchDirector(walker=walker, concurrency=concurrency, report_language=args.report_language)
    paths = await director.run(plan, run_dir)
    print("MVP walkthrough run completed")
    print(f"Run dir: {paths['run_dir']}")
    print(f"Evidence: {paths['evidence']}")
    print(f"Report: {paths['report']}")
    print(f"Evaluation: {paths['evaluation']}")


async def _prepare_verification_checkpoints(
    plan: ResearchPlan,
    args: argparse.Namespace,
    is_browser_use: bool,
) -> tuple[str | None, str | None]:
    browser_storage_state = getattr(args, "browser_storage_state", None)
    if not is_browser_use or args.verification_mode == "off":
        return args.browser_user_data_dir, browser_storage_state

    products = [product for product in plan.products if product.credentials_ref]
    if not products:
        return args.browser_user_data_dir, browser_storage_state

    user_data_dir = args.browser_user_data_dir
    if not user_data_dir:
        credential_refs = {str(product.credentials_ref) for product in products if product.credentials_ref}
        if len(credential_refs) > 1:
            print(
                "Multiple credential refs are configured. Pass --browser-user-data-dir explicitly "
                "or use --verification-mode off for this run."
            )
            return args.browser_user_data_dir, browser_storage_state
        user_data_dir = str(resolve_user_data_dir(None, products[0].credentials_ref, products[0].url))
        print(f"Using verification browser profile: {user_data_dir}")

    storage_state = browser_storage_state or str(Path(user_data_dir) / "prodwalk_storage_state.json")
    print(f"Using verification storage state: {storage_state}")

    checked_refs: set[str] = set()
    for product in products:
        ref = str(product.credentials_ref)
        if ref in checked_refs:
            continue
        checked_refs.add(ref)
        await ensure_auth_session(
            AuthSessionRequest(
                url=product.url,
                credentials_ref=product.credentials_ref,
                user_data_dir=user_data_dir,
                storage_state=storage_state,
                success_url_contains=list(args.verification_success_url_contains or []),
                login_url_contains=args.verification_login_url_contains,
                timeout_sec=args.verification_timeout_sec,
                manual_confirm=True,
            )
        )

    return user_data_dir, storage_state


class HumanVerificationRetryWalker(BrowserWalker):
    def __init__(
        self,
        *,
        inner: BrowserWalker,
        user_data_dir: str | None,
        storage_state: str | None,
        success_url_contains: list[str],
        login_url_contains: str,
        timeout_sec: float,
    ) -> None:
        self.inner = inner
        self.user_data_dir = user_data_dir
        self.storage_state = storage_state
        self.success_url_contains = success_url_contains
        self.login_url_contains = login_url_contains
        self.timeout_sec = timeout_sec
        self._retried_refs: set[str] = set()

    async def walk(self, product: ProductTarget, scenario: Scenario) -> WalkthroughResult:
        result = await self.inner.walk(product, scenario)
        if not self._should_retry_with_manual_verification(product, result):
            return result

        ref = str(product.credentials_ref)
        self._retried_refs.add(ref)
        print("")
        print("=" * 72)
        print("Manual verification required during the walkthrough.")
        print("A visible browser will open. Complete Altcha/captcha/login there.")
        print("When the authenticated product page is visible, return here and press Enter.")
        print("=" * 72)
        print("")
        await run_manual_auth_session(
            AuthSessionRequest(
                url=product.url,
                credentials_ref=product.credentials_ref,
                user_data_dir=self.user_data_dir,
                storage_state=self.storage_state,
                success_url_contains=self.success_url_contains,
                login_url_contains=self.login_url_contains,
                timeout_sec=self.timeout_sec,
                manual_confirm=True,
            )
        )
        retry = await self.inner.walk(product, scenario)
        retry.metrics["manual_verification_retries"] = int(retry.metrics.get("manual_verification_retries", 0)) + 1
        retry.metrics["pre_retry_status"] = result.status
        return retry

    def _should_retry_with_manual_verification(
        self,
        product: ProductTarget,
        result: WalkthroughResult,
    ) -> bool:
        if not product.credentials_ref or not self.user_data_dir:
            return False
        if str(product.credentials_ref) in self._retried_refs:
            return False

        text_parts: list[str] = [result.status]
        text_parts.extend(result.errors)
        for step in result.steps:
            text_parts.extend([step.action, step.observation, step.url])
        for item in result.evidence:
            text_parts.extend([item.summary, item.url])
            final_output = item.data.get("final_output")
            if isinstance(final_output, str):
                text_parts.append(final_output)
            urls = item.data.get("urls")
            if isinstance(urls, list):
                text_parts.extend(str(url) for url in urls)
            errors = item.data.get("errors")
            if isinstance(errors, list):
                text_parts.extend(str(error) for error in errors)

        text = " ".join(part for part in text_parts if part).lower()
        auth_markers = [
            "manual_verification_required",
            "/auth/login",
            "altcha",
            "captcha",
            "verification expired",
            "authentication is required",
            "login page",
            "login failed",
            "login did not complete",
            "no authenticated dashboard",
        ]
        if not any(marker in text for marker in auth_markers):
            return False
        if result.status == "blocked":
            return True
        return any(
            marker in text
            for marker in (
                "manual_verification_required",
                "verification expired",
                "login failed",
                "login did not complete",
                "no authenticated dashboard",
            )
        )


if __name__ == "__main__":
    main()
