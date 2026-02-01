"""Core domain models — authoritative definitions per design.md Section 3."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Enums ────────────────────────────────────────────────────────────────────


class ContentType(str, enum.Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    TRANSCRIPT = "transcript"
    CODE = "code"


class SourceKind(str, enum.Enum):
    USER = "user"
    FILE = "file"
    URL = "url"
    CLIPBOARD = "clipboard"


class TrustLabel(str, enum.Enum):
    USER = "user"
    TRUSTED = "trusted"
    UNKNOWN = "unknown"


class BeliefStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    CHALLENGED = "challenged"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class DecayModel(str, enum.Enum):
    EXPONENTIAL = "exponential"
    NONE = "none"


class EdgeFromType(str, enum.Enum):
    NOTE = "note"
    BELIEF = "belief"
    SOURCE = "source"


class EdgeRelType(str, enum.Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    RELATED = "related"


# Re-use EdgeFromType for to_type — same enum values
EdgeToType = EdgeFromType


# ── Domain Objects ───────────────────────────────────────────────────────────


class Source(BaseModel):
    source_id: str = Field(default_factory=_uuid)
    kind: SourceKind
    locator: str
    captured_at: datetime = Field(default_factory=_utcnow)
    trust_label: TrustLabel = TrustLabel.USER


class Note(BaseModel):
    note_id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_utcnow)
    content: str
    content_type: ContentType = ContentType.TEXT
    source_id: str
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    content_hash: str = ""  # sha256, computed at creation


class Belief(BaseModel):
    belief_id: str = Field(default_factory=_uuid)
    claim_text: str
    status: BeliefStatus = BeliefStatus.PROPOSED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    decay_model: DecayModel = DecayModel.EXPONENTIAL
    scope: dict[str, Any] = Field(default_factory=dict)
    derived_from_agent: str = ""


class Edge(BaseModel):
    edge_id: str = Field(default_factory=_uuid)
    from_type: EdgeFromType
    from_id: str
    rel_type: EdgeRelType
    to_type: EdgeToType
    to_id: str


class Signal(BaseModel):
    signal_id: str = Field(default_factory=_uuid)
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    processed_at: datetime | None = None


class AuditEntry(BaseModel):
    audit_id: str = Field(default_factory=_uuid)
    timestamp: datetime = Field(default_factory=_utcnow)
    entity_type: str  # "note", "belief", "edge", "source", "signal"
    entity_id: str
    action: str  # "create", "update", "delete"
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
