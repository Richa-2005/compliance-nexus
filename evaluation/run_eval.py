from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bootstrap import PROJECT_ROOT

from audit_eval import evaluate_seeded_audits
from citation_eval import evaluate_citations
from retrieval_eval import evaluate_retrieval
from retrieval_pipeline_eval import evaluate_retrieval_pipelines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic ComplianceNexus evaluation without paid LLM judges."
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "golden_queries.json",
        help="Path to golden query definitions.",
    )
    parser.add_argument(
        "--seed-data",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "seed_data.json",
        help="Path to seeded audit records.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "results" / "results.json",
        help="Path for the benchmark JSON output.",
    )
    return parser.parse_args()


def load_golden_queries(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("golden query file must contain a JSON list")
    return data


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_summary(path: Path, results: dict) -> None:
    retrieval = results["retrieval"]["summary"]
    pipelines = results["retrieval_pipelines"]
    audit = results["audit_correctness"]["summary"]
    citation = results["citation_grounding"]["summary"]

    retrieval_gaps = [
        row
        for row in results["retrieval"]["queries"]
        if row["recall_at_10"] < 1.0
    ]
    audit_gaps = [
        row
        for row in results["audit_correctness"]["queries"]
        if row["matched_seed_record"]
        and not all(
            row[field]
            for field in (
                "status_match",
                "transaction_value_match",
                "allowed_ceiling_match",
                "primary_source_match",
            )
        )
    ]

    lines = [
        "# ComplianceNexus Offline Evaluation Results",
        "",
        f"Generated at: `{results['generated_at']}`",
        "",
        "This benchmark runs without paid LLM-as-judge APIs. It measures retrieval quality, seeded audit correctness, citation grounding, and retrieval latency using curated golden queries.",
        "",
        "## Summary",
        "",
        "| Area | Metric | Result |",
        "| :--- | :--- | ---: |",
        f"| Retrieval | Queries | {retrieval['queries']} |",
        f"| Retrieval | Recall@5 | {percent(retrieval['recall_at_5'])} |",
        f"| Retrieval | Recall@10 | {percent(retrieval['recall_at_10'])} |",
        f"| Retrieval | MRR | {retrieval['mrr']:.3f} |",
        f"| Retrieval | NDCG@10 | {retrieval['ndcg_at_10']:.3f} |",
        f"| Retrieval | p95 latency | {retrieval['p95_latency_ms']:.2f} ms |",
        "",
        "## Retrieval Pipeline Comparison",
        "",
        "| Pipeline | Recall@10 | MRR | NDCG@10 | p95 latency |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]

    pipeline_labels = {
        "bm25": "BM25",
        "dense": "Dense",
        "hybrid_rrf": "Hybrid RRF",
        "hybrid_rrf_lexical_rerank": "Hybrid RRF + lexical reranker",
    }
    for key, label in pipeline_labels.items():
        summary = pipelines[key]["summary"]
        lines.append(
            f"| {label} | {percent(summary['recall_at_10'])} | {summary['mrr']:.3f} | {summary['ndcg_at_10']:.3f} | {summary['p95_latency_ms']:.2f} ms |"
        )

    lines.extend([
        "",
        "## Seeded Audit And Citation Summary",
        "",
        "| Area | Metric | Result |",
        "| :--- | :--- | ---: |",
        f"| Audit | Seeded records matched | {audit['matched_seed_records']} / {audit['golden_queries']} |",
        f"| Audit | Status accuracy | {percent(audit['status_accuracy'])} |",
        f"| Audit | Transaction value accuracy | {percent(audit['transaction_value_accuracy'])} |",
        f"| Audit | Allowed ceiling accuracy | {percent(audit['allowed_ceiling_accuracy'])} |",
        f"| Audit | Primary source accuracy | {percent(audit['primary_source_accuracy'])} |",
        f"| Citation | Expected source coverage | {percent(citation['expected_source_coverage'])} |",
        f"| Citation | Citation/evidence overlap | {percent(citation['citation_evidence_overlap'])} |",
        "",
        "## Diagnostics",
        "",
    ])

    if retrieval_gaps:
        lines.append("Retrieval misses:")
        lines.extend(
            f"- `{row['id']}` Recall@10={row['recall_at_10']:.2f}; expected={row['expected_sources']}; retrieved={row['retrieved_sources']}"
            for row in retrieval_gaps
        )
    else:
        lines.append("Retrieval misses: none.")

    lines.append("")

    if audit_gaps:
        lines.append("Seeded audit mismatches:")
        lines.extend(
            "- `{id}` status={status_match} value={transaction_value_match} ceiling={allowed_ceiling_match} source={primary_source_match}".format(
                **row
            )
            for row in audit_gaps
        )
    else:
        lines.append("Seeded audit mismatches: none.")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The current retrieval path is strong on source recall for this curated set. The lower primary-source and citation/evidence-overlap scores are useful Phase 2 targets: they show where the platform should make source selection and finding-level provenance more precise before claiming full compliance-grade traceability.",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    golden_queries = load_golden_queries(args.golden)

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_type": "deterministic_offline",
        "notes": [
            "No paid LLM judge is required.",
            "Retrieval metrics use expected source documents from curated golden queries.",
            "Audit and citation metrics use existing seeded records when the query text matches.",
        ],
        "retrieval": evaluate_retrieval(golden_queries),
        "retrieval_pipelines": evaluate_retrieval_pipelines(golden_queries),
        "audit_correctness": evaluate_seeded_audits(golden_queries, args.seed_data),
        "citation_grounding": evaluate_citations(golden_queries, args.seed_data),
    }

    write_json(args.output, results)
    write_summary(args.output.with_name("summary.md"), results)
    print(json.dumps({
        "output": str(args.output),
        "summary": str(args.output.with_name("summary.md")),
        "retrieval": results["retrieval"]["summary"],
        "retrieval_pipelines": {
            name: payload["summary"]
            for name, payload in results["retrieval_pipelines"].items()
        },
        "audit_correctness": results["audit_correctness"]["summary"],
        "citation_grounding": results["citation_grounding"]["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
