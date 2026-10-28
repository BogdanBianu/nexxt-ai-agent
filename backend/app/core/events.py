"""Emiterea evenimentelor agenților (pentru animația live din frontend)."""
from datetime import datetime, timezone
from typing import Any, Callable

from app.contracts import AgentEvent, AgentName, AgentStatus

EmitFn = Callable[[AgentName, AgentStatus, str, dict[str, Any] | None], None]


def now() -> datetime:
    return datetime.now(timezone.utc)


class EventSink:
    """Colectează evenimentele unui dosar. CaseStore le citește pentru SSE."""

    def __init__(self, case_id: str, on_event: Callable[[AgentEvent], None] | None = None):
        self.case_id = case_id
        self.events: list[AgentEvent] = []
        self._on_event = on_event

    def emit(self, agent: AgentName, status: AgentStatus, message: str,
             data: dict[str, Any] | None = None) -> None:
        ev = AgentEvent(case_id=self.case_id, seq=len(self.events) + 1, timestamp=now(),
                        agent=agent, status=status, message=message, data=data or {})
        self.events.append(ev)
        if self._on_event:
            self._on_event(ev)


def noop_emit(agent, status, message, data=None) -> None:
    return None
