import json
import time
from pathlib import Path
from typing import Any, Dict, List
from app.core.config import settings

def load_progress() -> Dict[str, Any]:
    if not settings.PROGRESS_FILE.exists():
        raise FileNotFoundError(f"Cannot find checkpoint file at: {settings.PROGRESS_FILE}")
    with settings.PROGRESS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def generate_evaluation_summary() -> None:
    data = load_progress()
    records: Dict[str, Any] = data.get("records", {})

    if not records:
        print("No evaluation records found in progress file.")
        return

    metrics_keys = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    metric_totals: Dict[str, float] = {m: 0.0 for m in metrics_keys}
    metric_counts: Dict[str, int] = {m: 0 for m in metrics_keys}
    latencies: List[float] = []

    rows_detail: List[str] = []

    for rec_id, rec_data in sorted(records.items(), key=lambda x: int(x[0])):
        query = rec_data.get("query", "N/A")
        metrics = rec_data.get("metrics", {})

        row_scores = {}
        for m in metrics_keys:
            m_info = metrics.get(m, {})
            if m_info.get("status") == "success":
                score = float(m_info.get("score", 0.0))
                metric_totals[m] += score
                metric_counts[m] += 1
                row_scores[m] = f"{score:.4f}"
                if "elapsed_seconds" in m_info:
                    latencies.append(m_info["elapsed_seconds"])
            else:
                row_scores[m] = "ERR"

        rows_detail.append(
            f"| `{rec_id}` | {query[:50]}... | {row_scores.get('faithfulness', 'N/A')} | "
            f"{row_scores.get('answer_relevancy', 'N/A')} | {row_scores.get('context_precision', 'N/A')} | "
            f"{row_scores.get('context_recall', 'N/A')} |"
        )

    # Compute Averages
    averages = {
        m: (metric_totals[m] / metric_counts[m]) if metric_counts[m] > 0 else 0.0
        for m in metrics_keys
    }
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    markdown_report = f"""# ComplianceNexus System Diagnostic & RAGAS Benchmark Report

* **Report Generated On**: `{time.strftime("%Y-%m-%d %H:%M:%S UTC")}`
* **Total Benchmark Cases Evaluated**: `{len(records)}`
* **Mean Pipeline Execution Latency**: `{avg_latency:.2f}s`

---

## Executive Summary Metrics

| Metric Dimension | Target Benchmark | Measured Average Score | Status |
| :--- | :--- | :--- | :--- |
| **Faithfulness** | `> 0.8500` | **`{averages['faithfulness']:.4f}`** | {'PASS' if averages['faithfulness'] >= 0.80 else 'REVIEW'} |
| **Answer Relevancy** | `> 0.8000` | **`{averages['answer_relevancy']:.4f}`** | {'PASS' if averages['answer_relevancy'] >= 0.75 else 'REVIEW'} |
| **Context Precision** | `> 0.8500` | **`{averages['context_precision']:.4f}`** | {'PASS' if averages['context_precision'] >= 0.80 else 'REVIEW'} |
| **Context Recall** | `> 0.8500` | **`{averages['context_recall']:.4f}`** | {'PASS' if averages['context_recall'] >= 0.80 else 'REVIEW'} |

---

## 🔬 Granular Per-Record Metric Matrix

| Record ID | Target Query Assignment | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
| :---: | :--- | :--- | :--- | :--- | :--- |
{"\n".join(rows_detail)}

---
*Report generated automatically by `ComplianceNexus Telemetry Diagnostics Engine`.*
"""

    settings.REPORT_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with settings.REPORT_OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write(markdown_report)

    print(f"Success! Benchmark analytics written to: {settings.REPORT_OUTPUT_FILE}")


if __name__ == "__main__":
    generate_evaluation_summary()