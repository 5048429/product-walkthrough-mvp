from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from .credentials import CredentialStore, normalize_ref
from .models import slugify


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
    user_data_dir = resolve_user_data_dir(args.user_data_dir, args.credentials_ref, args.url)
    storage_state = resolve_optional_path(args.storage_state, create_parent=True)
    browser_path = args.browser_path or os.getenv("BROWSER_USE_CHROME_PATH") or find_local_browser()

    username, password = credential_values(args.credentials_ref)

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Playwright is required for auth-session. Install local browser-use dependencies with "
            '`pip install -e ".[browser-use-local]"`.'
        ) from exc

    user_data_dir.mkdir(parents=True, exist_ok=True)
    print(f"Opening browser for manual login: {args.url}")
    print(f"Persistent profile: {user_data_dir}")
    print("Complete Altcha/captcha and login in the browser window. This command will continue automatically.")

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            executable_path=browser_path,
            viewport={"width": 1440, "height": 1000},
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            if username and password:
                await autofill_login(page, username, password)
                print("Credentials were filled. Please complete verification and click Login.")
            elif args.credentials_ref:
                print(f"Credential ref not found or incomplete: {args.credentials_ref}. Please fill login manually.")

            if args.manual_confirm:
                success_url = await wait_for_manual_confirmation(page)
            else:
                success_url = await wait_for_login_success(
                    page=page,
                    start_url=args.url,
                    login_url_contains=args.login_url_contains,
                    success_url_contains=args.success_url_contains,
                    timeout_sec=args.timeout_sec,
                )
            if storage_state:
                await context.storage_state(path=str(storage_state))
            print("Auth session ready.")
            print(f"Current URL: {success_url}")
            print(f"Use with: --browser-user-data-dir {user_data_dir}")
            if storage_state:
                print(f"Storage state saved: {storage_state}")
        finally:
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
    current_url = str(getattr(page, "url", ""))
    if await page_has_login_form(page):
        raise RuntimeError(
            "The page still appears to show a login form. Complete login first, then rerun auth-session."
        )
    await wait_for_stable_auth_page(page)
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
