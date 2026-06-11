from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from .agents.director import ResearchDirector
from .agents.walker import BrowserUseLocalWalker, MockBrowserWalker
from .auth_session import add_auth_session_subcommand, handle_auth_session_command
from .config_loader import load_research_plan
from .credentials import add_credential_subcommands, handle_credential_command


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
    walker = (
        BrowserUseLocalWalker(
            model=args.browser_model,
            max_steps=args.browser_max_steps,
            run_timeout_sec=args.browser_timeout_sec,
            user_data_dir=args.browser_user_data_dir,
            storage_state=args.browser_storage_state,
        )
        if is_browser_use
        else MockBrowserWalker()
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


if __name__ == "__main__":
    main()
