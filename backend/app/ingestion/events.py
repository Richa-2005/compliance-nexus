from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4
import hashlib

from pydantic import BaseModel, Field


class IngestionTopic(StrEnum):
    DOCUMENT_INGESTED = "document.ingested"
    DOCUMENT_PARSED = "document.parsed"
    EMBEDDING_CREATED = "embedding.created"
    AUDIT_REQUESTED = "audit.requested"
    AUDIT_COMPLETED = "audit.completed"
    DEAD_LETTER = "document.dead_letter"


class IngestionEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    document_id: str
    content_hash: str
    source_path: str
    original_filename: str
    produced_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    retry_count: int = 0
    metadata: dict[str, str] = Field(default_factory=dict)


class DeadLetterEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    failed_event: IngestionEvent
    failed_topic: str
    error_type: str
    error_message: str
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_id_for(content_hash: str) -> str:
    return f"doc_{content_hash[:16]}"
