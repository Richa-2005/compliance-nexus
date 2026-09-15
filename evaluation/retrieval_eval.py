from __future__ import annotations

import math
import time
from dataclasses import dataclass
from statistics import mean
from typing import Any

import bootstrap  # noqa: F401
from app.core.retriever import get_retriever


@dataclass
class QueryRetrievalResult:
    query_id: str
    retrieved_sources: list[str]
    expected_sources: list[str]
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    latency_ms: float


def _source_for_child_id(retriever: Any, child_id: str) -> str:
    parent_id = retriever.child_to_parent.get(child_id)
    parent = retriever.parent_by_id.get(parent_id, {})
    return str(parent.get("metadata", {}).get("source_document", ""))


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _recall_at(retrieved: list[str], expected: set[str], k: int) -> float:
    if not expected:
        return 1.0
    hits = set(retrieved[:k]) & expected
    return len(hits) / len(expected)


def _mrr(retrieved: list[str], expected: set[str]) -> float:
    for index, source in enumerate(retrieved, start=1):
        if source in expected:
            return 1.0 / index
    return 0.0


def _dcg(relevances: list[int]) -> float:
    return sum(rel / math.log2(index + 2) for index, rel in enumerate(relevances))


def _ndcg_at(retrieved: list[str], expected: set[str], k: int) -> float:
    if not expected:
        return 1.0
    relevances = [1 if source in expected else 0 for source in retrieved[:k]]
    ideal_hits = min(len(expected), k)
    ideal = [1] * ideal_hits + [0] * (k - ideal_hits)
    ideal_dcg = _dcg(ideal)
    return _dcg(relevances) / ideal_dcg if ideal_dcg else 0.0


def evaluate_retrieval(golden_queries: list[dict], top_k: int = 10) -> dict:
    retriever = get_retriever()
    rows: list[QueryRetrievalResult] = []

    for item in golden_queries:
        started = time.perf_counter()
        chroma_results, bm25_results = retriever.vector_semantic_results(
            item["query"],
            n_results=max(top_k, 10),
        )
        child_ids = retriever.rrf(chroma_results, bm25_results)
        latency_ms = (time.perf_counter() - started) * 1000

        retrieved_sources = _dedupe_preserve_order(
            [_source_for_child_id(retriever, child_id) for child_id in child_ids]
        )
        expected_sources = item.get("expected_sources", [])
        expected = set(expected_sources)

        rows.append(
            QueryRetrievalResult(
                query_id=item["id"],
                retrieved_sources=retrieved_sources[:top_k],
                expected_sources=expected_sources,
                recall_at_5=_recall_at(retrieved_sources, expected, 5),
                recall_at_10=_recall_at(retrieved_sources, expected, 10),
                mrr=_mrr(retrieved_sources, expected),
                ndcg_at_10=_ndcg_at(retrieved_sources, expected, 10),
                latency_ms=latency_ms,
            )
        )

    latencies = sorted(row.latency_ms for row in rows)
    p95_index = min(len(latencies) - 1, math.ceil(len(latencies) * 0.95) - 1)

    return {
        "summary": {
            "queries": len(rows),
            "recall_at_5": mean(row.recall_at_5 for row in rows),
            "recall_at_10": mean(row.recall_at_10 for row in rows),
            "mrr": mean(row.mrr for row in rows),
            "ndcg_at_10": mean(row.ndcg_at_10 for row in rows),
            "p95_latency_ms": latencies[p95_index] if latencies else 0.0,
        },
        "queries": [
            {
                "id": row.query_id,
                "expected_sources": row.expected_sources,
                "retrieved_sources": row.retrieved_sources,
                "recall_at_5": row.recall_at_5,
                "recall_at_10": row.recall_at_10,
                "mrr": row.mrr,
                "ndcg_at_10": row.ndcg_at_10,
                "latency_ms": row.latency_ms,
            }
            for row in rows
        ],
    }
