"""Working context — RAM-only, per-session state."""
from __future__ import annotations

from uuid import UUID

from kira.types import KiraState


class WorkingContext:
    def __init__(self):
        self.current_conversation_id: UUID | None = None
        self.current_topic: str | None = None
        self.recent_entities: list[str] = []
        self.recent_tools_used: list[str] = []
        self.session_facts: list[str] = []
        self.state: KiraState = KiraState.IDLE

    def update_topic(self, topic: str) -> None:
        self.current_topic = topic

    def add_entity(self, name: str) -> None:
        if name not in self.recent_entities:
            self.recent_entities.append(name)
            if len(self.recent_entities) > 20:
                self.recent_entities.pop(0)

    def add_tool_used(self, tool: str) -> None:
        self.recent_tools_used.append(tool)
        if len(self.recent_tools_used) > 10:
            self.recent_tools_used.pop(0)

    def add_fact(self, fact: str) -> None:
        self.session_facts.append(fact)

    def to_string(self) -> str:
        parts: list[str] = []
        if self.current_topic:
            parts.append(f"Current topic: {self.current_topic}")
        if self.recent_entities:
            parts.append(f"Recently mentioned: {', '.join(self.recent_entities[-5:])}")
        if self.session_facts:
            parts.append(f"Learned this session: {'; '.join(self.session_facts[-5:])}")
        return "\n".join(parts) if parts else "No prior context in this session."
