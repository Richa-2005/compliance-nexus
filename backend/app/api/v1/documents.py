from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.models import Roles, Users
from app.ingestion.events import IngestionEvent
from app.ingestion.kafka_client import KafkaUnavailable, publish_event
from app.ingestion.status_store import list_statuses, persist_upload, read_status, update_status


documents_router = APIRouter(prefix="/documents")


@documents_router.get("")
async def list_documents(
    current_user: Users = Depends(get_current_user),
) -> dict:
    return {"documents": list_statuses()}


@documents_router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: Users = Depends(get_current_user),
) -> dict:
    if current_user.role not in {Roles.L2_RISK_OFFICER, Roles.COMPLIANCE_ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only L2 risk officers can upload knowledge source documents.",
        )

    if not settings.KAFKA_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka ingestion is disabled for this environment.",
        )

    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF uploads are supported for asynchronous ingestion.",
        )

    document = await persist_upload(file, current_user.email)
    event = IngestionEvent(
        event_type="document.ingested",
        document_id=document["document_id"],
        content_hash=document["content_hash"],
        source_path=document["source_path"],
        original_filename=document["original_filename"],
        metadata={"uploaded_by": current_user.email},
    )

    try:
        publish_event(settings.KAFKA_DOCUMENT_INGESTED_TOPIC, event)
    except KafkaUnavailable as exc:
        update_status(
            document["document_id"],
            status="publish_failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    update_status(
        document["document_id"],
        status="queued",
        ingested_event_id=event.event_id,
    )

    return {
        "document_id": document["document_id"],
        "content_hash": document["content_hash"],
        "status": "queued",
        "idempotent_replay": document["idempotent_replay"],
        "topic": settings.KAFKA_DOCUMENT_INGESTED_TOPIC,
    }


@documents_router.get("/{document_id}")
async def get_document_status(
    document_id: str,
    current_user: Users = Depends(get_current_user),
) -> dict:
    status_record = read_status(document_id)
    if not status_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document ingestion record not found.",
        )
    return status_record
