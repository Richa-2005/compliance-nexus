from __future__ import annotations

import json
from pathlib import Path
from statistics import mean


def _load_seed_records(seed_path: Path) -> dict[str, dict]:
    if not seed_path.exists():
        return {}
    with seed_path.open("r", encoding="utf-8") as file:
        rows = json.load(file)
    return {str(row.get("query", "")).strip(): row for row in rows}


def _status(record: dict) -> str:
    return str(record.get("state") or record.get("status") or "").upper()


def _near(expected: float, actual: float, tolerance: float = 0.01) -> bool:
    return abs(float(expected) - float(actual)) <= tolerance


def evaluate_seeded_audits(golden_queries: list[dict], seed_path: Path) -> dict:
    records_by_query = _load_seed_records(seed_path)
    rows = []

    for item in golden_queries:
        record = records_by_query.get(item["query"].strip())
        if not record:
            rows.append(
                {
                    "id": item["id"],
                    "matched_seed_record": False,
                    "status_match": None,
                    "transaction_value_match": None,
                    "allowed_ceiling_match": None,
                    "primary_source_match": None,
                }
            )
            continue

        expected_value = float(item.get("expected_transaction_value", 0))
        actual_value = float(record.get("transaction_value", 0))
        value_match = True if expected_value == 0 else _near(expected_value, actual_value)

        expected_ceiling = float(item.get("expected_allowed_ceiling", 0))
        actual_ceiling = float(record.get("allowed_ceiling", 0))

        rows.append(
            {
                "id": item["id"],
                "matched_seed_record": True,
                "status_match": _status(record) == str(item.get("expected_status", "")).upper(),
                "transaction_value_match": value_match,
                "allowed_ceiling_match": _near(expected_ceiling, actual_ceiling),
                "primary_source_match": str(record.get("source_doc", "")) == str(item.get("expected_primary_source", "")),
            }
        )

    matched_rows = [row for row in rows if row["matched_seed_record"]]

    def rate(field: str) -> float:
        if not matched_rows:
            return 0.0
        return mean(1.0 if row[field] else 0.0 for row in matched_rows)

    return {
        "summary": {
            "golden_queries": len(golden_queries),
            "matched_seed_records": len(matched_rows),
            "status_accuracy": rate("status_match"),
            "transaction_value_accuracy": rate("transaction_value_match"),
            "allowed_ceiling_accuracy": rate("allowed_ceiling_match"),
            "primary_source_accuracy": rate("primary_source_match"),
        },
        "queries": rows,
    }
