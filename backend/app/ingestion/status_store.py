from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import json
import shutil
import time

from fastapi import UploadFile

from app.core.config import settings
from app.ingestion.events import document_id_for, file_sha256


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def document_dir(document_id: str) -> Path:
    return settings.INGESTION_DIR / "documents" / document_id


def status_path(document_id: str) -> Path:
    return document_dir(document_id) / "status.json"


def read_status(document_id: str) -> dict | None:
    path = status_path(document_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def list_statuses() -> list[dict]:
    documents_root = settings.INGESTION_DIR / "documents"
    if not documents_root.exists():
        return []

    statuses = []
    for path in sorted(documents_root.glob("*/status.json")):
        with path.open("r", encoding="utf-8") as file:
            statuses.append(json.load(file))
    return statuses


def ready_parent_chunk_paths(document_ids: set[str] | None = None) -> list[Path]:
    paths = []
    for status in list_statuses():
        if status.get("status") != "ready":
            continue
        if document_ids and status.get("document_id") not in document_ids:
            continue
        parent_chunks_path = status.get("parent_chunks_path")
        if parent_chunks_path and Path(parent_chunks_path).exists():
            paths.append(Path(parent_chunks_path))
    return paths


def write_status(document_id: str, status: dict) -> None:
    path = status_path(document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    status["updated_at"] = utc_now_iso()
    with path.open("w", encoding="utf-8") as file:
        json.dump(status, file, indent=2, sort_keys=True)


def update_status(document_id: str, **changes: object) -> dict:
    status = read_status(document_id) or {"document_id": document_id}
    status.update(changes)
    write_status(document_id, status)
    return status


async def persist_upload(upload: UploadFile, uploaded_by: str) -> dict:
    suffix = Path(upload.filename or "document.pdf").suffix or ".pdf"
    temp_dir = settings.INGESTION_DIR / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"upload_{time.time_ns()}{suffix}"

    with temp_path.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            output.write(chunk)

    content_hash = file_sha256(temp_path)
    document_id = document_id_for(content_hash)
    target_dir = document_dir(document_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{document_id}{suffix}"

    if not target_path.exists():
        shutil.move(str(temp_path), target_path)
    else:
        temp_path.unlink(missing_ok=True)

    existing = read_status(document_id)
    if existing:
        return {
            **existing,
            "source_path": str(target_path),
            "content_hash": content_hash,
            "idempotent_replay": True,
        }

    status = {
        "document_id": document_id,
        "content_hash": content_hash,
        "original_filename": upload.filename or target_path.name,
        "source_path": str(target_path),
        "status": "received",
        "uploaded_by": uploaded_by,
        "created_at": utc_now_iso(),
        "idempotent_replay": False,
    }
    write_status(document_id, status)
    return status
