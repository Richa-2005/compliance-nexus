from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from app.core.config import settings
from app.ingestion.events import DeadLetterEvent, IngestionEvent
from app.ingestion.kafka_client import build_consumer, publish_event, publish_json
from app.ingestion.status_store import update_status
from app.utils.chunker import Chunker
from app.utils.parser import Parser, save_file


def parse_document(event: IngestionEvent) -> IngestionEvent:
    source_path = Path(event.source_path)
    parser = Parser(str(source_path))
    parser.processing()
    for record in parser.data:
        record["source_document"] = event.original_filename
        record["document_id"] = event.document_id
        record["source_type"] = "uploaded_document"
    save_file(parser.new_path, parser.data)

    update_status(
        event.document_id,
        status="parsed",
        parsed_path=parser.new_path,
        parser_version="pdfplumber-structured-v1",
    )

    return IngestionEvent(
        event_type="document.parsed",
        document_id=event.document_id,
        content_hash=event.content_hash,
        source_path=parser.new_path,
        original_filename=event.original_filename,
        metadata={**event.metadata, "source_pdf": str(source_path)},
    )


def create_chunks(event: IngestionEvent) -> IngestionEvent:
    chunk_output_dir = Path(event.source_path).parent
    chunker = Chunker(event.source_path, output_dir=chunk_output_dir)
    chunker.parent_chunker()
    chunker.store_parent_chunks()
    chunker.child_chunker()

    update_status(
        event.document_id,
        status="indexed",
        parent_chunks_path=str(chunk_output_dir / "parent_chunks.json"),
        child_chunks_path=str(chunk_output_dir / "child_chunks.json"),
        chunker_version="token-window-v1",
    )

    return IngestionEvent(
        event_type="embedding.created",
        document_id=event.document_id,
        content_hash=event.content_hash,
        source_path=event.source_path,
        original_filename=event.original_filename,
        metadata=event.metadata,
    )


def send_to_dlq(topic: str, event: IngestionEvent, error: Exception) -> None:
    update_status(
        event.document_id,
        status="dead_lettered",
        error_type=type(error).__name__,
        error_message=str(error),
    )
    dead_letter = DeadLetterEvent(
        failed_event=event,
        failed_topic=topic,
        error_type=type(error).__name__,
        error_message=f"{error}\n{traceback.format_exc()}",
    )
    publish_json(
        settings.KAFKA_DEAD_LETTER_TOPIC,
        event.document_id,
        dead_letter.model_dump(mode="json"),
    )


def handle_event(topic: str, event: IngestionEvent) -> None:
    if topic == settings.KAFKA_DOCUMENT_INGESTED_TOPIC:
        update_status(event.document_id, status="parsing")
        next_event = parse_document(event)
        publish_event(settings.KAFKA_DOCUMENT_PARSED_TOPIC, next_event)
        return

    if topic == settings.KAFKA_DOCUMENT_PARSED_TOPIC:
        update_status(event.document_id, status="indexing")
        next_event = create_chunks(event)
        publish_event(settings.KAFKA_EMBEDDING_CREATED_TOPIC, next_event)
        return

    if topic == settings.KAFKA_EMBEDDING_CREATED_TOPIC:
        update_status(event.document_id, status="ready")
        return

    raise ValueError(f"Unsupported topic: {topic}")


def retry_or_dead_letter(topic: str, event: IngestionEvent, error: Exception) -> None:
    if event.retry_count >= settings.KAFKA_MAX_RETRIES:
        send_to_dlq(topic, event, error)
        return

    retry_event = event.model_copy(update={"retry_count": event.retry_count + 1})
    publish_event(topic, retry_event)


def run_worker() -> None:
    topics = [
        settings.KAFKA_DOCUMENT_INGESTED_TOPIC,
        settings.KAFKA_DOCUMENT_PARSED_TOPIC,
        settings.KAFKA_EMBEDDING_CREATED_TOPIC,
    ]
    consumer = build_consumer(topics)
    print(f"Kafka ingestion worker subscribed to: {', '.join(topics)}")

    try:
        while True:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                print(f"Kafka consumer error: {message.error()}")
                continue

            topic = message.topic()
            payload = json.loads(message.value().decode("utf-8"))
            event = IngestionEvent.model_validate(payload)

            try:
                handle_event(topic, event)
                consumer.commit(message)
            except Exception as exc:
                retry_or_dead_letter(topic, event, exc)
                consumer.commit(message)
    finally:
        consumer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Kafka ingestion worker.")
    parser.parse_args()
    run_worker()


if __name__ == "__main__":
    main()
