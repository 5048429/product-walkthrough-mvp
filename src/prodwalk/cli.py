from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from .agents.director import ResearchDirector
from .agents.walker import BrowserUseLocalWalker, MockBrowserWalker
from .config_loader import load_research_plan


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
    run_parser.add_argument("--browser-max-steps", type=int, default=25)

    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    plan = load_research_plan(args.config)
    is_browser_use = args.mode in {"browser-use", "browser-use-local"}
    concurrency = args.concurrency if args.concurrency is not None else (1 if is_browser_use else 3)
    walker = (
        BrowserUseLocalWalker(model=args.browser_model, max_steps=args.browser_max_steps)
        if is_browser_use
        else MockBrowserWalker()
    )
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) / f"run-{timestamp}"
    director = ResearchDirector(walker=walker, concurrency=concurrency)
    paths = await director.run(plan, run_dir)
    print("MVP walkthrough run completed")
    print(f"Run dir: {paths['run_dir']}")
    print(f"Evidence: {paths['evidence']}")
    print(f"Report: {paths['report']}")
    print(f"Evaluation: {paths['evaluation']}")


if __name__ == "__main__":
    main()
