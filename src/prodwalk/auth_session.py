from __future__ import annotations

import argparse
import asyncio
import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .credentials import CredentialStore, normalize_ref
from .models import slugify


@dataclass(slots=True)
class AuthSessionRequest:
    url: str
    credentials_ref: str | None = None
    user_data_dir: str | Path | None = None
    storage_state: str | Path | None = None
    success_url_contains: list[str] = field(default_factory=list)
    login_url_contains: str = "/auth/login"
    timeout_sec: float = 300.0
    browser_path: str | None = None
    manual_confirm: bool = True


@dataclass(slots=True)
class ManualAuthSession:
    request: AuthSessionRequest
    playwright: Any
    context: Any
    page: Any
    user_data_dir: Path
    storage_state: Path | None
    credentials_filled: bool = False


def add_auth_session_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "auth-session",
        help="Create a reusable local browser profile with a human-assisted login",
    )
    parser.add_argument("--url", required=True, help="Login or product URL to open")
    parser.add_argument(
        "--credentials-ref",
        default=None,
        help="Credential ref to auto-fill before the human completes verification",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Persistent browser profile directory. Defaults to .prodwalk/browser-profiles/<ref-or-host>",
    )
    parser.add_argument(
        "--storage-state",
        default=None,
        help="Optional storage state JSON path to save in addition to the persistent profile",
    )
    parser.add_argument(
        "--success-url-contains",
        action="append",
        default=[],
        help="Substring that marks login success. Can be passed multiple times.",
    )
    parser.add_argument(
        "--login-url-contains",
        default="/auth/login",
        help="URL substring treated as the login page. Default: /auth/login",
    )
    parser.add_argument("--timeout-sec", type=float, default=300.0, help="How long to wait for manual login")
    parser.add_argument("--browser-path", default=None, help="Chrome/Edge executable path override")
    parser.add_argument(
        "--manual-confirm",
        action="store_true",
        help="Wait for Enter after the user confirms the authenticated page is visible.",
    )


def handle_auth_session_command(args: argparse.Namespace) -> None:
    asyncio.run(create_auth_session(args))


async def create_auth_session(args: argparse.Namespace) -> None:
    request = AuthSessionRequest(
        url=args.url,
        credentials_ref=args.credentials_ref,
        user_data_dir=args.user_data_dir,
        storage_state=args.storage_state,
        success_url_contains=list(args.success_url_contains or []),
        login_url_contains=args.login_url_contains,
        timeout_sec=args.timeout_sec,
        browser_path=args.browser_path,
        manual_confirm=args.manual_confirm,
    )
    await run_manual_auth_session(request)


async def ensure_auth_session(request: AuthSessionRequest) -> bool:
    user_data_dir = resolve_user_data_dir(str_or_none(request.user_data_dir), request.credentials_ref, request.url)
    storage_state = resolve_optional_path(str_or_none(request.storage_state), create_parent=True)
    browser_path = request.browser_path or os.getenv("BROWSER_USE_CHROME_PATH") or find_local_browser()

    async_playwright = load_async_playwright()
    user_data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Checking saved auth session for: {request.url}")
    async with async_playwright() as playwright:
        if await auth_session_is_valid(
            playwright=playwright,
            url=request.url,
            user_data_dir=user_data_dir,
            storage_state=storage_state,
            browser_path=browser_path,
            login_url_contains=request.login_url_contains,
            success_url_contains=request.success_url_contains,
        ):
            print(f"Saved auth session is already valid: {user_data_dir}")
            return False

    print("Manual verification is needed before the walkthrough can continue.")
    await run_manual_auth_session(request)
    return True


async def run_manual_auth_session(request: AuthSessionRequest) -> str:
    user_data_dir = resolve_user_data_dir(str_or_none(request.user_data_dir), request.credentials_ref, request.url)
    print(f"Opening browser for manual login: {request.url}")
    print(f"Persistent profile: {user_data_dir}")
    print("Complete Altcha/captcha/login in the browser window, then return here and press Enter.")

    session = await open_manual_auth_session(request)
    try:
        if session.credentials_filled:
            print("Credentials were filled. Please complete verification and click Login.")
        elif request.credentials_ref:
            print(f"Credential ref not found or incomplete: {request.credentials_ref}. Please fill login manually.")

        if request.manual_confirm:
            success_url = await wait_for_manual_confirmation(session.page)
        else:
            success_url = await wait_for_login_success(
                page=session.page,
                start_url=request.url,
                login_url_contains=request.login_url_contains,
                success_url_contains=request.success_url_contains,
                timeout_sec=request.timeout_sec,
            )
        if session.storage_state:
            await session.context.storage_state(path=str(session.storage_state))
        print("Auth session ready.")
        print(f"Current URL: {success_url}")
        print(f"Use with: --browser-user-data-dir {session.user_data_dir}")
        if session.storage_state:
            print(f"Storage state saved: {session.storage_state}")
        return success_url
    finally:
        await close_manual_auth_session(session)


async def open_manual_auth_session(request: AuthSessionRequest) -> ManualAuthSession:
    user_data_dir = resolve_user_data_dir(str_or_none(request.user_data_dir), request.credentials_ref, request.url)
    storage_state = resolve_optional_path(str_or_none(request.storage_state), create_parent=True)
    browser_path = request.browser_path or os.getenv("BROWSER_USE_CHROME_PATH") or find_local_browser()

    username, password = credential_values(request.credentials_ref)
    async_playwright = load_async_playwright()

    user_data_dir.mkdir(parents=True, exist_ok=True)
    playwright = await async_playwright().start()
    context = None
    try:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            executable_path=browser_path,
            viewport={"width": 1440, "height": 1000},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(request.url, wait_until="domcontentloaded", timeout=60000)
        credentials_filled = False
        if username and password:
            credentials_filled = await autofill_login(page, username, password)
        return ManualAuthSession(
            request=request,
            playwright=playwright,
            context=context,
            page=page,
            user_data_dir=user_data_dir,
            storage_state=storage_state,
            credentials_filled=credentials_filled,
        )
    except Exception:
        if context is not None:
            await context.close()
        await _stop_playwright(playwright)
        raise


async def complete_manual_auth_session(session: ManualAuthSession) -> str:
    if await page_has_login_form(session.page):
        raise RuntimeError(
            "The page still appears to show a login form or verification challenge. "
            "Complete login first, then confirm again."
        )
    await wait_for_stable_auth_page(session.page)
    current_url = str(getattr(session.page, "url", ""))
    if session.storage_state:
        await session.context.storage_state(path=str(session.storage_state))
    await close_manual_auth_session(session)
    return current_url


async def close_manual_auth_session(session: ManualAuthSession) -> None:
    try:
        await session.context.close()
    finally:
        await _stop_playwright(session.playwright)


async def _stop_playwright(playwright: Any) -> None:
    stop = getattr(playwright, "stop", None)
    if not callable(stop):
        return
    result = stop()
    if inspect.isawaitable(result):
        await result


def load_async_playwright() -> object:
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Playwright is required for auth-session. Install local browser-use dependencies with "
            '`pip install -e ".[browser-use-local]"`.'
        ) from exc
    return async_playwright


async def auth_session_is_valid(
    *,
    playwright: object,
    url: str,
    user_data_dir: Path,
    storage_state: Path | None,
    browser_path: str | None,
    login_url_contains: str,
    success_url_contains: list[str],
) -> bool:
    context = None
    try:
        context = await playwright.chromium.launch_persistent_context(  # type: ignore[attr-defined]
            user_data_dir=str(user_data_dir),
            headless=True,
            executable_path=browser_path,
            viewport={"width": 1440, "height": 1000},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await wait_for_stable_auth_page(page)
        current_url = str(getattr(page, "url", ""))
        has_login_form = await page_has_login_form(page)
        valid = is_auth_success_url(
            current_url=current_url,
            start_url=url,
            login_url_contains=login_url_contains,
            success_url_contains=success_url_contains,
            has_login_form=has_login_form,
        )
        if valid and storage_state:
            await context.storage_state(path=str(storage_state))
        return valid
    except Exception as exc:  # noqa: BLE001 - preflight should fall back to human verification.
        print(f"Auth preflight could not confirm a valid session: {exc}")
        return False
    finally:
        if context is not None:
            await context.close()


async def autofill_login(page: object, username: str, password: str) -> None:
    await fill_first_matching(
        page,
        [
            "input[type='email']",
            "input[name*='email' i]",
            "input[id*='email' i]",
            "input[placeholder*='email' i]",
            "input[name*='user' i]",
            "input[id*='user' i]",
            "input[type='text']",
        ],
        username,
    )
    await fill_first_matching(page, ["input[type='password']", "input[name*='password' i]"], password)


async def wait_for_manual_confirmation(page: object) -> str:
    print("When the authenticated product page is visible, return to this terminal and press Enter.")
    await asyncio.to_thread(input)
    if await page_has_login_form(page):
        raise RuntimeError(
            "The page still appears to show a login form. Complete login first, then rerun auth-session."
        )
    await wait_for_stable_auth_page(page)
    current_url = str(getattr(page, "url", ""))
    return current_url


async def fill_first_matching(page: object, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first  # type: ignore[attr-defined]
            if await locator.count() == 0:
                continue
            await locator.fill(value, timeout=2500)
            return True
        except Exception:
            continue
    return False


async def wait_for_login_success(
    *,
    page: object,
    start_url: str,
    login_url_contains: str,
    success_url_contains: list[str],
    timeout_sec: float,
) -> str:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_url = ""
    while asyncio.get_running_loop().time() < deadline:
        current_url = str(getattr(page, "url", ""))
        if current_url != last_url:
            print(f"Waiting for auth success. Current URL: {current_url}")
            last_url = current_url
        has_login_form = await page_has_login_form(page)
        if is_auth_success_url(
            current_url=current_url,
            start_url=start_url,
            login_url_contains=login_url_contains,
            success_url_contains=success_url_contains,
            has_login_form=has_login_form,
        ):
            await wait_for_stable_auth_page(page)
            return current_url
        await asyncio.sleep(1)
    raise TimeoutError(
        f"Manual login was not detected within {timeout_sec:g} seconds. "
        "Finish login and rerun auth-session, or pass a better --success-url-contains value."
    )


def is_auth_success_url(
    *,
    current_url: str,
    start_url: str,
    login_url_contains: str,
    success_url_contains: list[str],
    has_login_form: bool = False,
) -> bool:
    if not current_url:
        return False
    if has_login_form:
        return False
    if success_url_contains and any(marker in current_url for marker in success_url_contains):
        return True

    current = urlparse(current_url)
    start = urlparse(start_url)
    if current.netloc != start.netloc:
        return False
    if login_url_contains and login_url_contains in current_url:
        return False
    return current.path not in {"", "/"}


async def page_has_login_form(page: object) -> bool:
    selectors = [
        "input[type='password']",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
        "button:has-text('Sign In')",
        "input[id*='altcha' i]",
        "[class*='altcha' i]",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first  # type: ignore[attr-defined]
            if await locator.count() > 0 and await locator.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


async def wait_for_stable_auth_page(page: object) -> None:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)  # type: ignore[attr-defined]
    except Exception:
        pass
    await asyncio.sleep(2)


def credential_values(credentials_ref: str | None) -> tuple[str | None, str | None]:
    if not credentials_ref:
        return None, None
    normalized = normalize_ref(credentials_ref).upper()
    username = (
        os.getenv(f"{normalized}_USERNAME")
        or os.getenv(f"{normalized}_EMAIL")
        or os.getenv(f"{normalized}_USER")
    )
    password = os.getenv(f"{normalized}_PASSWORD")
    if username and password:
        return username, password

    credential = CredentialStore().get(credentials_ref)
    if credential is None:
        return None, None
    return credential.username, credential.password


def resolve_user_data_dir(value: str | None, credentials_ref: str | None, url: str) -> Path:
    if value:
        path = Path(value)
    else:
        name = normalize_ref(credentials_ref) if credentials_ref else slugify(urlparse(url).netloc or url)
        path = Path(".prodwalk") / "browser-profiles" / name
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resolve_optional_path(value: str | None, *, create_parent: bool = False) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def str_or_none(value: str | Path | None) -> str | None:
    return str(value) if value is not None else None


def find_local_browser() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None
