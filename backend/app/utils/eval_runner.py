import argparse
import copy
import json
import os
import time
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings(
    "ignore",
    message=r"Importing .* from 'ragas\.metrics' is deprecated.*",
    category=DeprecationWarning,
)

from langchain_groq import ChatGroq
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from langchain_core.embeddings import Embeddings
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.run_config import RunConfig
from app.core.config import settings


METRICS = {
    "faithfulness": faithfulness,
    "answer_relevancy": answer_relevancy,
    "context_precision": context_precision,
    "context_recall": context_recall,
}


class LocalChromaEmbeddings(Embeddings):
    """Local embeddings for Ragas, with no API credentials required."""

    def __init__(self) -> None:
        self.embedding_function = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(vector) for vector in self.embedding_function(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate saved graph states with a cloud-hosted Groq judge."
    )
    parser.add_argument("--metric", choices=[*METRICS, "all"], default="all")
    parser.add_argument("--record", type=int, help="Evaluate only this zero-based row.")
    parser.add_argument("--start", type=int, default=0, help="Inclusive zero-based row.")
    parser.add_argument("--end", type=int, help="Exclusive zero-based row.")
    
    # UPGRADE: Target a high-capacity 70B/89B structural model on Groq
    parser.add_argument("--model", default="llama-3.3-70b-versatile")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds per Ragas job.")
    
    parser.add_argument("--max-context-chars", type=int, default=48000)
    parser.add_argument("--max-contexts", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    
    # THROTTLE CEILING: Provide a solid cooldown delay to respect the free API limits
    parser.add_argument("--cooldown", type=int, default=15, help="Seconds to sleep between pairs.")
    parser.add_argument("--max-load", type=float, default=20.0) # Bypassed load checking for cloud
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_progress() -> dict[str, Any]:
    if not settings.PROGRESS_FILE.exists() or settings.PROGRESS_FILE.stat().st_size == 0:
        return {"version": 2, "records": {}}

    data = load_json(settings.PROGRESS_FILE)
    if isinstance(data, dict) and data.get("version") == 2:
        data.setdefault("records", {})
        return data

    # Do not silently overwrite the older list-based progress format.
    backup = settings.PROGRESS_FILE.with_suffix(".legacy.json")
    settings.PROGRESS_FILE.replace(backup)
    print(f"Moved old progress format to {backup}", flush=True)
    return {"version": 2, "records": {}}


def save_progress(progress: dict[str, Any]) -> None:
    """Atomically replace the checkpoint so an interrupted write cannot corrupt it."""

    settings.PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.PROGRESS_FILE.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(progress, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(settings.PROGRESS_FILE)


def limited_contexts(
    contexts: list[str], max_contexts: int, max_chars: int
) -> list[str]:
    """Keep retrieval order while fitting the local judge's practical context size."""

    selected: list[str] = []
    seen: set[str] = set()
    remaining = max_chars

    for raw_context in contexts:
        context = str(raw_context).strip()
        if not context or context in seen or remaining <= 0:
            continue
        seen.add(context)
        selected.append(context[:remaining])
        remaining -= len(selected[-1])
        if len(selected) >= max_contexts:
            break

    return selected


def semantic_response(state: dict[str, Any]) -> str:
    audit_verdict = str(state.get("audit_verdict", "")).strip()
    if audit_verdict:
        return audit_verdict

    extracted = state.get("extracted_metrics", {})
    value = float(extracted.get("transaction_value", 0.0))
    ceiling = float(extracted.get("allowed_ceiling", 0.0))
    lineage = extracted.get("lineage", "")
    return (
        f"Transaction value parsed as ${value:,.2f} USD. "
        f"Corporate constraint ceiling identified as ${ceiling:,.2f} USD. "
        f"Lineage Trace and Governance Analysis: {lineage}"
    )


def is_successful(progress: dict[str, Any], index: int, metric_name: str) -> bool:
    entry = (
        progress.get("records", {})
        .get(str(index), {})
        .get("metrics", {})
        .get(metric_name, {})
    )
    return entry.get("status") == "success"


def store_result(
    progress: dict[str, Any],
    index: int,
    query: str,
    metric_name: str,
    result: dict[str, Any],
) -> None:
    record = progress["records"].setdefault(
        str(index), {"query": query, "metrics": {}}
    )
    record["query"] = query
    record.setdefault("metrics", {})[metric_name] = result
    save_progress(progress)


def build_llm(args: argparse.Namespace) -> ChatGroq:
    """Initialize a cloud-hosted, high-capacity model judge layer."""
    return ChatGroq(
        model=args.model,
        temperature=0.0,
        groq_api_key=settings.GROQ_API_KEY.get_secret_value(),
        timeout=args.timeout,
        max_retries=2
    )

def wait_for_safe_load(max_load: float) -> None:
    """Avoid adding another sustained job while the machine is already busy."""

    while True:
        one_minute_load = os.getloadavg()[0]
        if one_minute_load <= max_load:
            return
        print(
            f"COOL system load={one_minute_load:.2f} exceeds {max_load:.2f}; "
            "waiting 30 seconds",
            flush=True,
        )
        time.sleep(30)


def selected_indices(args: argparse.Namespace, total: int) -> range:
    if args.record is not None:
        if not 0 <= args.record < total:
            raise ValueError(f"--record must be between 0 and {total - 1}")
        return range(args.record, args.record + 1)

    start = max(0, args.start)
    end = total if args.end is None else min(args.end, total)
    if end < start:
        raise ValueError("--end must be greater than or equal to --start")
    return range(start, end)


def compute_metrics_incrementally(args: argparse.Namespace) -> None:
    saved_states = load_json(settings.STATES_OUTPUT_FILE)
    progress = load_progress()
    indices = selected_indices(args, len(saved_states))

    active_metrics = METRICS if args.metric == "all" else {args.metric: METRICS[args.metric]}

    print(
        f"Loaded {len(saved_states)} states; rows {indices.start}:{indices.stop}; "
        f"metrics={','.join(active_metrics)}; results={settings.PROGRESS_FILE}",
        flush=True,
    )

    evaluator_embeddings = LocalChromaEmbeddings()
    run_config = RunConfig(
        timeout=args.timeout,
        max_retries=1,
        max_workers=1,
        log_tenacity=True,
    )

    for index in indices:
        state = saved_states[index]
        query = state["query"]
        all_contexts = state.get("retrieved_contexts", [])
        contexts = limited_contexts(
            all_contexts, args.max_contexts, args.max_context_chars
        )
        if state.get("graph_entities"):
            contexts.append(state["graph_entities"])
            
        full_chars = sum(len(str(context)) for context in all_contexts)
        selected_chars = sum(len(context) for context in contexts)

        record_metrics = progress.get("records", {}).get(str(index), {}).get("metrics", {})
        if all(record_metrics.get(m, {}).get("status") == "success" for m in active_metrics) and not args.force:
            print(f"SKIP row={index} (All requested metrics already completed successfully)", flush=True)
            continue

        sample = SingleTurnSample(
            user_input=query,
            retrieved_contexts=contexts,
            response=semantic_response(state),
            reference=state.get("ground_truth_answer", ""),
        )
        dataset = EvaluationDataset(samples=[sample])

        print(
            f"RUN  row={index} batch processing [{', '.join(active_metrics)}] "
            f"contexts={len(contexts)}/{len(all_contexts)} "
            f"chars={selected_chars}/{full_chars}",
            flush=True,
        )
        wait_for_safe_load(args.max_load)
        started = time.monotonic()

        try:
            evaluator_llm = build_llm(args)
            
            evaluation = evaluate(
                dataset=dataset,
                metrics=[copy.deepcopy(active_metrics[m]) for m in active_metrics],
                llm=evaluator_llm,
                embeddings=evaluator_embeddings,
                run_config=run_config,
                batch_size=1,
                raise_exceptions=True,
                show_progress=False,
            )

            elapsed = round(time.monotonic() - started, 2)
            for m_name in active_metrics:
                score = float(evaluation[m_name][0])
                result = {
                    "status": "success",
                    "score": score,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "elapsed_seconds": elapsed,
                    "model": args.model,
                    "context_count": len(contexts),
                    "context_chars": selected_chars,
                }
                store_result(progress, index, query, m_name, result)
                print(f"SAVE row={index} metric={m_name} score={score:.4f}", flush=True)

        except KeyboardInterrupt:
            print("Interrupted by user sequence control safely.", flush=True)
            raise
        except Exception as error:
            elapsed = round(time.monotonic() - started, 2)
            print(f"FAIL row={index} batch run crashed: {error}", flush=True)
            for m_name in active_metrics:
                result = {
                    "status": "error",
                    "error": f"{type(error).__name__}: {error}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "elapsed_seconds": elapsed,
                }
                store_result(progress, index, query, m_name, result)

        if args.cooldown > 0:
            print(f"COOL idle for {args.cooldown} seconds to let cloud parameters clear...", flush=True)
            time.sleep(args.cooldown)

    successful = sum(
        metric.get("status") == "success"
        for record in progress["records"].values()
        for metric in record.get("metrics", {}).values()
    )
    print(f"Done. {successful} successful record/metric pairs saved.", flush=True)
    
if __name__ == "__main__":
    compute_metrics_incrementally(parse_args())
