from __future__ import annotations

import json
from typing import Iterable

from app.core.config import settings
from app.ingestion.events import IngestionEvent


class KafkaUnavailable(RuntimeError):
    pass


def _producer():
    try:
        from confluent_kafka import Producer
    except ImportError as exc:
        raise KafkaUnavailable(
            "confluent-kafka is not installed. Install requirements and enable Kafka locally."
        ) from exc

    return Producer({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})


def _consumer(topics: Iterable[str]):
    try:
        from confluent_kafka import Consumer
    except ImportError as exc:
        raise KafkaUnavailable(
            "confluent-kafka is not installed. Install requirements and enable Kafka locally."
        ) from exc

    consumer = Consumer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": settings.KAFKA_CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe(list(topics))
    return consumer


def publish_event(topic: str, event: IngestionEvent) -> None:
    producer = _producer()
    producer.produce(topic, key=event.document_id, value=event.model_dump_json())
    producer.flush()


def publish_json(topic: str, key: str, payload: dict) -> None:
    producer = _producer()
    producer.produce(
        topic,
        key=key,
        value=json.dumps(payload, default=str),
    )
    producer.flush()


def build_consumer(topics: Iterable[str]):
    return _consumer(topics)
