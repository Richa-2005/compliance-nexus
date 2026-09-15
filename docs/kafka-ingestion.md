# Kafka Async Ingestion

ComplianceNexus keeps Kafka ingestion disabled by default so the deployed audit
demo remains isolated from Phase 2 infrastructure work.

## Why Kafka

Document processing is slower and more failure-prone than serving an audit
request. Kafka lets the API accept a document quickly, then move expensive work
through durable stages:

```text
POST /api/v1/documents
  -> document.ingested
  -> parser worker
  -> document.parsed
  -> indexing worker
  -> embedding.created
```

The existing `/api/v1/audits/evaluate` endpoint is not changed by this flow.

## Topics

| Topic | Purpose |
| --- | --- |
| `document.ingested` | A user uploaded a source document. |
| `document.parsed` | The worker produced structured JSON from the PDF. |
| `embedding.created` | The document has been chunked and is ready for retrieval/indexing work. |
| `audit.requested` | Reserved for future async audit execution. |
| `audit.completed` | Reserved for future async audit completion events. |
| `document.dead_letter` | Failed events after retry exhaustion. |

## Reliability Controls

- Consumer group: `KAFKA_CONSUMER_GROUP`
- Idempotency: `document_id` is derived from the file SHA-256 content hash.
- Retry: failed events are republished with an incremented `retry_count`.
- DLQ: events move to `document.dead_letter` after `KAFKA_MAX_RETRIES`.
- Status tracking: each document writes a status record under
  `data/ingestion/documents/{document_id}/status.json`.

## Local Configuration

Start Kafka locally:

```bash
docker compose -f docker-compose.kafka.yml up
```

Or start the full reproducible stack:

```bash
docker compose up --build
```

Add these values to `backend/.env` only when running the async ingestion path:

```env
KAFKA_ENABLED=true
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_GROUP=compliance-nexus-ingestion
KAFKA_MAX_RETRIES=3
```

Start the backend as usual:

```bash
PYTHONPATH=backend venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the worker in a separate terminal:

```bash
PYTHONPATH=backend venv/bin/python -m app.ingestion.worker
```

The startup order is:

```text
Kafka compose
  -> FastAPI backend
  -> ingestion worker
  -> PDF upload request
```

## API Surface

Upload a document:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/raw/example.pdf"
```

Check ingestion status:

```bash
curl http://127.0.0.1:8000/api/v1/documents/$DOCUMENT_ID \
  -H "Authorization: Bearer $TOKEN"
```

List uploaded documents:

```bash
curl http://127.0.0.1:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN"
```

Run an audit that includes ready uploaded sources:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/audits/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"Audit this transaction against uploaded policy evidence.","include_ingested_sources":true}'
```
