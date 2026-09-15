"""Shared Pydantic models used across all KIRA packages."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ModelTier(str, Enum):
    FAST = "fast"
    SMART = "smart"
    CLOUD = "cloud"
    VISION = "vision"


class RiskLevel(int, Enum):
    READ = 0
    PERSONAL = 1
    EXECUTE = 2
    EXTERNAL = 3
    CRITICAL = 4


class EntityType(str, Enum):
    PERSON = "person"
    PROJECT = "project"
    TOPIC = "topic"
    PLACE = "place"
    TOOL = "tool"
    EVENT = "event"
    ORGANIZATION = "organization"


class MemoryCategory(str, Enum):
    PREFERENCE = "preference"
    FACT = "fact"
    DECISION = "decision"
    TASK = "task"
    OBSERVATION = "observation"


class KiraState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SEARCHING = "searching"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    ERROR = "error"
    SUCCESS = "success"


class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: Optional[UUID] = None
    role: Role
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Entity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: EntityType
    name: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Relationship(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID
    type: str
    weight: float = 1.0
    metadata: dict = Field(default_factory=dict)


class Memory(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    content: str
    category: MemoryCategory
    importance: float = 0.5
    source_type: str = "conversation"
    source_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[UUID] = None
    research_id: Optional[str] = None
    research_mode: Optional[str] = None  # "off" | "quick" | "deep"


class ChatResponse(BaseModel):
    message: Message
    conversation_id: UUID
    state: KiraState = KiraState.IDLE
    memories_used: list[UUID] = Field(default_factory=list)
    model_used: str = ""
    latency_ms: int = 0
