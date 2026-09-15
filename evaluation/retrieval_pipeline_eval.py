from __future__ import annotations

import math
import time
from pathlib import Path
from statistics import mean
from typing import Any

import chromadb

from bootstrap import PROJECT_ROOT
from app.core.retriever import get_retriever


CHROMA_DIR = PROJECT_ROOT / "data" / "processed" / "chroma_db"
CHROMA_COLLECTION = "compliance_nexus_chunks"


def _tokenize(text: str) -> set[str]:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {token for token in cleaned.split() if len(token) >= 3}


def _source_for_child_id(retriever: Any, child_id: str) -> str:
    parent_id = retriever.child_to_parent.get(child_id)
    parent = retriever.parent_by_id.get(parent_id, {})
    return str(parent.get("metadata", {}).get("source_document", ""))


def _text_for_child_id(retriever: Any, child_id: str) -> str:
    for item in retriever.json_data:
        if item.get("child_id") == child_id:
            return str(item.get("text_content", ""))
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for index, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + index)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda row: (-row[1], row[0]))]


def _lexical_rerank(retriever: Any, query: str, child_ids: list[str]) -> list[str]:
    query_terms = _tokenize(query)
    scored = []
    for index, child_id in enumerate(child_ids):
        text_terms = _tokenize(_text_for_child_id(retriever, child_id))
        overlap = len(query_terms & text_terms)
        coverage = overlap / max(len(query_terms), 1)
        scored.append((coverage, overlap, -index, child_id))
    scored.sort(reverse=True)
    return [child_id for _, _, _, child_id in scored]


def _recall_at(retrieved_sources: list[str], expected_sources: set[str], k: int) -> float:
    if not expected_sources:
        return 1.0
    return len(set(retrieved_sources[:k]) & expected_sources) / len(expected_sources)


def _mrr(retrieved_sources: list[str], expected_sources: set[str]) -> float:
    for index, source in enumerate(retrieved_sources, start=1):
        if source in expected_sources:
            return 1.0 / index
    return 0.0


def _dcg(relevances: list[int]) -> float:
    return sum(value / math.log2(index + 2) for index, value in enumerate(relevances))


def _ndcg_at(retrieved_sources: list[str], expected_sources: set[str], k: int) -> float:
    if not expected_sources:
        return 1.0
    relevances = [1 if source in expected_sources else 0 for source in retrieved_sources[:k]]
    ideal_hits = min(len(expected_sources), k)
    ideal = [1] * ideal_hits + [0] * (k - ideal_hits)
    ideal_dcg = _dcg(ideal)
    return _dcg(relevances) / ideal_dcg if ideal_dcg else 0.0


def _summarize(rows: list[dict]) -> dict:
    latencies = sorted(row["latency_ms"] for row in rows)
    p95_index = min(len(latencies) - 1, math.ceil(len(latencies) * 0.95) - 1)
    return {
        "queries": len(rows),
        "recall_at_5": mean(row["recall_at_5"] for row in rows),
        "recall_at_10": mean(row["recall_at_10"] for row in rows),
        "mrr": mean(row["mrr"] for row in rows),
        "ndcg_at_10": mean(row["ndcg_at_10"] for row in rows),
        "p95_latency_ms": latencies[p95_index] if latencies else 0.0,
    }


def _score_query(
    retriever: Any,
    query_id: str,
    expected_sources: list[str],
    child_ids: list[str],
    latency_ms: float,
) -> dict:
    retrieved_sources = _dedupe([_source_for_child_id(retriever, child_id) for child_id in child_ids])
    expected = set(expected_sources)
    return {
        "id": query_id,
        "expected_sources": expected_sources,
        "retrieved_sources": retrieved_sources[:10],
        "recall_at_5": _recall_at(retrieved_sources, expected, 5),
        "recall_at_10": _recall_at(retrieved_sources, expected, 10),
        "mrr": _mrr(retrieved_sources, expected),
        "ndcg_at_10": _ndcg_at(retrieved_sources, expected, 10),
        "latency_ms": latency_ms,
    }


def _dense_ids(collection: Any, query: str, n_results: int) -> list[str]:
    result = collection.query(query_texts=[query], n_results=n_results)
    ids = result.get("ids") or [[]]
    return [str(item) for item in ids[0]]


def evaluate_retrieval_pipelines(golden_queries: list[dict], candidate_k: int = 50) -> dict:
    retriever = get_retriever()
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = chroma_client.get_collection(name=CHROMA_COLLECTION)

    pipeline_rows = {
        "bm25": [],
        "dense": [],
        "hybrid_rrf": [],
        "hybrid_rrf_lexical_rerank": [],
    }

    for item in golden_queries:
        query = item["query"]
        expected_sources = item.get("expected_sources", [])

        started = time.perf_counter()
        bm25_docs = retriever.bm25_search(query, n_results=candidate_k)
        bm25_ids = [doc["child_id"] for doc in bm25_docs if doc.get("child_id")]
        bm25_latency = (time.perf_counter() - started) * 1000
        pipeline_rows["bm25"].append(
            _score_query(retriever, item["id"], expected_sources, bm25_ids, bm25_latency)
        )

        started = time.perf_counter()
        dense_ids = _dense_ids(collection, query, n_results=candidate_k)
        dense_latency = (time.perf_counter() - started) * 1000
        pipeline_rows["dense"].append(
            _score_query(retriever, item["id"], expected_sources, dense_ids, dense_latency)
        )

        started = time.perf_counter()
        hybrid_ids = _rrf([bm25_ids, dense_ids])
        hybrid_latency = bm25_latency + dense_latency + ((time.perf_counter() - started) * 1000)
        pipeline_rows["hybrid_rrf"].append(
            _score_query(retriever, item["id"], expected_sources, hybrid_ids, hybrid_latency)
        )

        started = time.perf_counter()
        reranked_ids = _lexical_rerank(retriever, query, hybrid_ids[:candidate_k])
        rerank_latency = hybrid_latency + ((time.perf_counter() - started) * 1000)
        pipeline_rows["hybrid_rrf_lexical_rerank"].append(
            _score_query(retriever, item["id"], expected_sources, reranked_ids, rerank_latency)
        )

    return {
        name: {
            "summary": _summarize(rows),
            "queries": rows,
        }
        for name, rows in pipeline_rows.items()
    }
