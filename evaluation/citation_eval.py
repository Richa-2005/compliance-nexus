from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any


NODE_TO_DOC = {
    "Apple SEC Filings": "apple-SEC.pdf",
    "RBI Credit Risk": "credit_Risk_RBI.pdf",
    "Foreign Investment": "foreign_Investement_rbi.pdf",
    "RBI KYC": "kyc_rbi.pdf",
    "Microsoft SEC Filings": "microsoft-SEC.pdf",
    "Internal Policy": "nexus_holdings_global_inc.pdf",
}


def _load_seed_records(seed_path: Path) -> dict[str, dict]:
    if not seed_path.exists():
        return {}
    with seed_path.open("r", encoding="utf-8") as file:
        rows = json.load(file)
    return {str(row.get("query", "")).strip(): row for row in rows}


def _parse_jsonish(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _citation_sources(record: dict) -> set[str]:
    citations = _parse_jsonish(record.get("citations_json") or record.get("citations"), [])
    sources = set()
    for citation in citations:
        text = citation if isinstance(citation, str) else json.dumps(citation)
        for source in NODE_TO_DOC.values():
            if source in text:
                sources.add(source)
    return sources


def _evidence_sources(record: dict) -> set[str]:
    evidence = _parse_jsonish(
        record.get("selected_evidence_items") or record.get("selected_evidence_json"),
        [],
    )
    return {
        item.get("source_document")
        for item in evidence
        if isinstance(item, dict) and item.get("source_document")
    }


def evaluate_citations(golden_queries: list[dict], seed_path: Path) -> dict:
    records_by_query = _load_seed_records(seed_path)
    rows = []

    for item in golden_queries:
        record = records_by_query.get(item["query"].strip())
        if not record:
            rows.append(
                {
                    "id": item["id"],
                    "matched_seed_record": False,
                    "expected_source_coverage": None,
                    "citation_evidence_overlap": None,
                }
            )
            continue

        expected = set(item.get("expected_sources", []))
        citation_sources = _citation_sources(record)
        evidence_sources = _evidence_sources(record)
        expected_source_coverage = len(expected & (citation_sources | evidence_sources)) / len(expected) if expected else 1.0
        citation_evidence_overlap = len(citation_sources & evidence_sources) / len(citation_sources) if citation_sources else 0.0

        rows.append(
            {
                "id": item["id"],
                "matched_seed_record": True,
                "expected_sources": sorted(expected),
                "citation_sources": sorted(citation_sources),
                "selected_evidence_sources": sorted(evidence_sources),
                "expected_source_coverage": expected_source_coverage,
                "citation_evidence_overlap": citation_evidence_overlap,
            }
        )

    matched_rows = [row for row in rows if row["matched_seed_record"]]

    return {
        "summary": {
            "matched_seed_records": len(matched_rows),
            "expected_source_coverage": mean(row["expected_source_coverage"] for row in matched_rows) if matched_rows else 0.0,
            "citation_evidence_overlap": mean(row["citation_evidence_overlap"] for row in matched_rows) if matched_rows else 0.0,
        },
        "queries": rows,
    }
