"""Core domain models for Second Brain."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

# ── Enums ──────────────────────────────────────────────────────────────


class ContentType(enum.StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    TRANSCRIPT = "transcript"
    CODE = "code"


class SourceKind(enum.StrEnum):
    USER = "user"
    FILE = "file"
    URL = "url"
    CLIPBOARD = "clipboard"


class TrustLabel(enum.StrEnum):
    USER = "user"
    TRUSTED = "trusted"
    UNKNOWN = "unknown"


class BeliefStatus(enum.StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    CHALLENGED = "challenged"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class DecayModel(enum.StrEnum):
    EXPONENTIAL = "exponential"
    NONE = "none"


class EntityType(enum.StrEnum):
    NOTE = "note"
    BELIEF = "belief"
    SOURCE = "source"


class RelType(enum.StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    RELATED_TO = "related_to"


# ── Domain Models ──────────────────────────────────────────────────────


class Source(BaseModel):
    """Origin metadata for captured content."""

    model_config = {"frozen": True}

    source_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    kind: SourceKind
    locator: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trust_label: TrustLabel = TrustLabel.UNKNOWN


class Note(BaseModel):
    """An immutable unit of captured knowledge."""

    model_config = {"frozen": True}

    note_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str
    content_type: ContentType = ContentType.TEXT
    source_id: uuid.UUID
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    content_hash: str = ""

    MAX_CONTENT_LENGTH: ClassVar[int] = 102_400  # 100 KB

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Note content must not be empty")
        if len(v) > cls.MAX_CONTENT_LENGTH:
            raise ValueError(
                f"Note content exceeds maximum length of {cls.MAX_CONTENT_LENGTH} characters"
            )
        return v

    @field_validator("tags", "entities")
    @classmethod
    def normalize_string_lists(cls, v: list[str]) -> list[str]:
        return [item.strip().lower() for item in v if item.strip()]


class Signal(BaseModel):
    """An internal event that agents can subscribe to."""

    model_config = {"frozen": True}

    signal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None


class Belief(BaseModel):
    """A derived claim with confidence and lifecycle management."""

    model_config = {"frozen": True}

    belief_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    claim_text: str
    status: BeliefStatus = BeliefStatus.PROPOSED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decay_model: DecayModel = DecayModel.EXPONENTIAL
    scope: dict[str, Any] = Field(default_factory=dict)
    derived_from_agent: str = ""

    @field_validator("claim_text")
    @classmethod
    def claim_text_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Belief claim_text must not be empty")
        return v


class Edge(BaseModel):
    """A typed relationship between two entities (polymorphic)."""

    model_config = {"frozen": True}

    edge_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    from_type: EntityType
    from_id: uuid.UUID
    rel_type: RelType
    to_type: EntityType
    to_id: uuid.UUID


class AuditEntry(BaseModel):
    """A single row in the append-only audit log."""

    model_config = {"frozen": True}

    audit_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    entity_type: str
    entity_id: uuid.UUID
    action: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
