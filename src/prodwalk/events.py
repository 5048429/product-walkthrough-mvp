from __future__ import annotations

import inspect
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol

from .models import utc_now


RUN_EVENT_TYPES = frozenset(
    {
        "run_started",
        "run_completed",
        "run_failed",
        "agent_started",
        "agent_finished",
        "agent_blocked",
        "artifact_written",
    }
)

AGENT_NAMES = frozenset(
    {
        "ResearchDirector",
        "ScenarioPlanner",
        "BrowserWalker",
        "EvidenceExtractor",
        "ProductAnalyst",
        "CompetitiveAnalyst",
        "Reviewer",
        "MarkdownReportWriter",
        "Evaluator",
    }
)


def new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex}"


@dataclass(slots=True, kw_only=True)
class RunEvent:
    event_id: str = field(default_factory=new_event_id)
    run_id: str
    event_type: str
    agent: str | None = None
    status: str | None = None
    message: str = ""
    product: str | None = None
    scenario_id: str | None = None
    artifact_type: str | None = None
    artifact_path: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.event_type not in RUN_EVENT_TYPES:
            raise ValueError(f"Unsupported run event type: {self.event_type}")
        if self.agent is not None and self.agent not in AGENT_NAMES:
            raise ValueError(f"Unsupported run event agent: {self.agent}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunEventSink(Protocol):
    def emit(self, event: RunEvent) -> Any:
        raise NotImplementedError


RunEventCallback = Callable[[RunEvent], Any]


async def dispatch_run_event(target: Any, event: RunEvent) -> None:
    if target is None:
        return

    emit = getattr(target, "emit", None)
    if callable(emit):
        result = emit(event)
    else:
        append = getattr(target, "append", None)
        if callable(append):
            result = append(event)
        elif callable(target):
            result = target(event)
        else:
            raise TypeError("event sink must be callable or expose emit(event)/append(event)")

    if inspect.isawaitable(result):
        await result
