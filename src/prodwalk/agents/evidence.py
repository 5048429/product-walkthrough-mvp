from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from ..models import EvidenceItem, WalkthroughResult, slugify


class EvidenceExtractor:
    def archive_screenshots(self, results: list[WalkthroughResult], run_dir: str | Path) -> dict[str, str]:
        """Copy browser screenshots into the run directory and rewrite evidence refs."""
        run_path = Path(run_dir).resolve()
        screenshots_dir = run_path / "screenshots"
        archived_by_source: dict[str, str] = {}
        used_names: set[str] = set()

        def archive(value: str, name_hint: str) -> str:
            if not value.strip():
                return value

            source = self._resolve_existing_path(value, run_path)
            if source is None:
                return value

            resolved = source.resolve()
            source_key = os.path.normcase(str(resolved))
            if source_key in archived_by_source:
                return archived_by_source[source_key]

            if resolved.is_relative_to(run_path):
                relative = resolved.relative_to(run_path).as_posix()
                archived_by_source[source_key] = relative
                used_names.add(resolved.name)
                return relative

            screenshots_dir.mkdir(parents=True, exist_ok=True)
            suffix = resolved.suffix or ".png"
            filename = self._unique_filename(f"{slugify(name_hint)}{suffix.lower()}", screenshots_dir, used_names)
            target = screenshots_dir / filename
            shutil.copy2(resolved, target)
            relative = target.relative_to(run_path).as_posix()
            archived_by_source[source_key] = relative
            return relative

        for result in results:
            for item in result.evidence:
                if item.screenshot:
                    item.screenshot = archive(item.screenshot, item.id)

        for result in results:
            for item in result.evidence:
                screenshot_path = item.data.get("screenshot_path")
                if isinstance(screenshot_path, str) and screenshot_path:
                    item.data["screenshot_path"] = archive(screenshot_path, item.id)

        for result in results:
            for step in result.steps:
                if step.screenshot:
                    step.screenshot = archive(
                        step.screenshot,
                        f"{result.product}-{result.scenario_id}-step-{step.index}",
                    )

        for result in results:
            for item in result.evidence:
                screenshot_paths = item.data.get("screenshot_paths")
                if isinstance(screenshot_paths, list):
                    item.data["screenshot_paths"] = [
                        archive(path, f"{item.id}-shot-{index}") if isinstance(path, str) else path
                        for index, path in enumerate(screenshot_paths, start=1)
                    ]
                page_evidence = item.data.get("page_evidence")
                if isinstance(page_evidence, dict):
                    for key in ("viewport_screenshot_path", "full_page_screenshot_path", "screenshot_path"):
                        value = page_evidence.get(key)
                        if isinstance(value, str) and value:
                            page_evidence[key] = archive(value, f"{item.id}-{key}")
                    nested_screenshots = page_evidence.get("screenshot_paths")
                    if isinstance(nested_screenshots, list):
                        page_evidence["screenshot_paths"] = [
                            archive(path, f"{item.id}-page-shot-{index}") if isinstance(path, str) else path
                            for index, path in enumerate(nested_screenshots, start=1)
                        ]

        return dict(archived_by_source)

    def archive_page_evidence_artifacts(self, results: list[WalkthroughResult], run_dir: str | Path) -> dict[str, str]:
        """Copy Playwright/CDP page evidence artifacts into the run directory."""
        run_path = Path(run_dir).resolve()
        page_evidence_dir = run_path / "page-evidence"
        archived_by_source: dict[str, str] = {}
        used_names_by_dir: dict[Path, set[str]] = {}

        def archive(value: str, name_hint: str) -> str:
            if not value.strip():
                return value

            source = self._resolve_existing_path(value, run_path)
            if source is None:
                return value

            resolved = source.resolve()
            source_key = os.path.normcase(str(resolved))
            if source_key in archived_by_source:
                return archived_by_source[source_key]

            if resolved.is_relative_to(run_path):
                relative = resolved.relative_to(run_path).as_posix()
                archived_by_source[source_key] = relative
                return relative

            target_dir = page_evidence_dir / slugify(name_hint)
            target_dir.mkdir(parents=True, exist_ok=True)
            used_names = used_names_by_dir.setdefault(target_dir, set())
            suffix = resolved.suffix or ".json"
            preferred = f"{slugify(resolved.stem)}{suffix.lower()}"
            filename = self._unique_filename(preferred, target_dir, used_names)
            target = target_dir / filename
            shutil.copy2(resolved, target)
            relative = target.relative_to(run_path).as_posix()
            archived_by_source[source_key] = relative
            return relative

        for result in results:
            for item in result.evidence:
                self._archive_page_evidence_for_data(item.data, item.id, archive)

        return dict(archived_by_source)

    def _archive_page_evidence_for_data(
        self,
        data: dict[str, object],
        name_hint: str,
        archive: Callable[[str, str], str],
    ) -> None:
        page_evidence = data.get("page_evidence")
        if isinstance(page_evidence, dict):
            for key in (
                "manifest_path",
                "html_path",
                "text_path",
                "elements_path",
                "dom_snapshot_path",
                "accessibility_tree_path",
                "network_log_path",
                "console_log_path",
            ):
                value = page_evidence.get(key)
                if isinstance(value, str) and value:
                    page_evidence[key] = archive(value, f"{name_hint}-{key}")
            artifact_paths = page_evidence.get("artifact_paths")
            if isinstance(artifact_paths, list):
                page_evidence["artifact_paths"] = [
                    archive(path, f"{name_hint}-page-evidence") if isinstance(path, str) else path
                    for path in artifact_paths
                ]

        artifact_paths = data.get("page_evidence_artifact_paths")
        if isinstance(artifact_paths, list):
            data["page_evidence_artifact_paths"] = [
                archive(path, f"{name_hint}-page-evidence") if isinstance(path, str) else path
                for path in artifact_paths
            ]

    def collect(self, results: list[WalkthroughResult]) -> list[EvidenceItem]:
        seen: set[str] = set()
        collected: list[EvidenceItem] = []
        for result in results:
            for item in result.evidence:
                if item.id in seen:
                    continue
                seen.add(item.id)
                collected.append(item)
        return collected

    def by_id(self, evidence: list[EvidenceItem]) -> dict[str, EvidenceItem]:
        return {item.id: item for item in evidence}

    def _resolve_existing_path(self, value: str, run_path: Path) -> Path | None:
        if value.startswith(("http://", "https://", "data:")):
            return None

        candidate = Path(value).expanduser()
        candidates = [candidate] if candidate.is_absolute() else [run_path / candidate, Path.cwd() / candidate]
        for path in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved.is_file():
                return resolved
        return None

    def _unique_filename(self, preferred: str, directory: Path, used_names: set[str]) -> str:
        candidate = preferred
        stem = Path(preferred).stem
        suffix = Path(preferred).suffix
        index = 2
        while candidate in used_names or (directory / candidate).exists():
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        used_names.add(candidate)
        return candidate
