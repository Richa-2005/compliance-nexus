# ComplianceNexus Offline Evaluation

This benchmark is intentionally deterministic and does not require a paid
LLM-as-judge API. It evaluates the compliance RAG system along the parts that
matter most for a regulated audit workflow:

- retrieval quality against curated expected source documents,
- seeded audit correctness against known demo scenarios,
- citation/evidence grounding against selected evidence and citation sources,
- latency for the retrieval path.

## Run

```bash
PYTHONPATH=backend venv/bin/python evaluation/run_eval.py
```

The output is written to:

```text
evaluation/results/results.json
```

## Metrics

Retrieval:

- `Recall@5`
- `Recall@10`
- `MRR`
- `NDCG@10`
- `p95_latency_ms`

Audit correctness:

- status accuracy
- transaction value accuracy
- allowed ceiling accuracy
- primary source accuracy

Citation grounding:

- expected source coverage
- citation/evidence overlap

RAGAS and LLM judge evaluation can still remain optional, but this benchmark is
the zero-cost baseline suitable for CI and local development.
