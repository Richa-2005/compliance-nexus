# ComplianceNexus Offline Evaluation Results

Generated at: `2026-09-15T05:06:59.243839+00:00`

This benchmark runs without paid LLM-as-judge APIs. It measures retrieval quality, seeded audit correctness, citation grounding, and retrieval latency using curated golden queries.

## Summary

| Area | Metric | Result |
| :--- | :--- | ---: |
| Retrieval | Queries | 16 |
| Retrieval | Recall@5 | 96.9% |
| Retrieval | Recall@10 | 96.9% |
| Retrieval | MRR | 1.000 |
| Retrieval | NDCG@10 | 0.958 |
| Retrieval | p95 latency | 5.49 ms |

## Retrieval Pipeline Comparison

| Pipeline | Recall@10 | MRR | NDCG@10 | p95 latency |
| :--- | ---: | ---: | ---: | ---: |
| BM25 | 100.0% | 1.000 | 0.977 | 5.36 ms |
| Dense | 96.9% | 0.906 | 0.868 | 296.11 ms |
| Hybrid RRF | 100.0% | 1.000 | 0.973 | 300.75 ms |
| Hybrid RRF + lexical reranker | 100.0% | 1.000 | 0.975 | 304.55 ms |

## Seeded Audit And Citation Summary

| Area | Metric | Result |
| :--- | :--- | ---: |
| Audit | Seeded records matched | 8 / 16 |
| Audit | Status accuracy | 100.0% |
| Audit | Transaction value accuracy | 87.5% |
| Audit | Allowed ceiling accuracy | 100.0% |
| Audit | Primary source accuracy | 50.0% |
| Citation | Expected source coverage | 100.0% |
| Citation | Citation/evidence overlap | 20.0% |

## Diagnostics

Retrieval misses:
- `q016` Recall@10=0.50; expected=['kyc_rbi.pdf', 'nexus_holdings_global_inc.pdf']; retrieved=['kyc_rbi.pdf']

Seeded audit mismatches:
- `q003` status=True value=True ceiling=True source=False
- `q004` status=True value=True ceiling=True source=False
- `q005` status=True value=True ceiling=True source=False
- `q006` status=True value=False ceiling=True source=True
- `q008` status=True value=True ceiling=True source=False

## Interpretation

The current retrieval path is strong on source recall for this curated set. The lower primary-source and citation/evidence-overlap scores are useful Phase 2 targets: they show where the platform should make source selection and finding-level provenance more precise before claiming full compliance-grade traceability.
