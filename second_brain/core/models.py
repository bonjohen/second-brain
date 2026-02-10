"""Core domain models for Second Brain."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

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

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Note content must not be empty")
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
