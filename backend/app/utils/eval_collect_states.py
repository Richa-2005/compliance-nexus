import json
from json import JSONDecodeError
import time
from pathlib import Path
from app.agents.audit_graph import audit_graph

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
EVAL_DATA_FILE = PROJECT_ROOT / "data" / "processed" / "eval_ground_truth.json"
STATES_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "eval_states.json"

def collect_graph_states():
    with open(EVAL_DATA_FILE, "r", encoding="utf-8") as file:
        eval_data = json.load(file)
    # Load existing progress if any to ensure resume capability
    collected_states = []
    if STATES_OUTPUT_FILE.exists() and STATES_OUTPUT_FILE.stat().st_size > 0:
        with open(STATES_OUTPUT_FILE, "r", encoding="utf-8") as file:
            try:
                collected_states = json.load(file)
            except JSONDecodeError:
                collected_states = []
    
    completed_queries = {state["query"] for state in collected_states}
    
    print(f"Found {len(eval_data)} benchmark cases. {len(collected_states)} already extracted.")

    for idx, case in enumerate(eval_data, start=1):
        query = case["query"]
        if query in completed_queries:
            continue

        print(f"Run graph pass {idx}/{len(eval_data)}: {query[:50]}...")
        
        # Invoke the multi-agent graph with validation guardrails active
        output_state = audit_graph.invoke({"query": query})

        # Capture metrics safely
        extracted = output_state.get("extracted_metrics", {})
        record = {
            "query": query,
            "ground_truth_answer": case["ground_truth_answer"],
            "retrieved_contexts": [
                block.get("text_content", "")
                for block in output_state.get("context_blocks", [])
            ],
            "audit_verdict": output_state.get("audit_verdict", ""),
            "extracted_metrics": {
                "transaction_value": extracted.get("transaction_value", 0.0),
                "allowed_ceiling": extracted.get("allowed_ceiling", 0.0),
                "lineage": extracted.get("lineage", "")
            }
        }
        collected_states.append(record)
        
        # Append progress snapshot directly to disk
        STATES_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATES_OUTPUT_FILE, "w", encoding="utf-8") as file:
            json.dump(collected_states, file, indent=4)
            
        time.sleep(2.0) # Minor backoff for laptop thermals

    print(f"State extraction complete. Captured snapshots written to {STATES_OUTPUT_FILE}")

if __name__ == "__main__":
    collect_graph_states()
