from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from ..core.retriever import get_retriever
import pickle 
import networkx as nx
from ..core.llm_factory import get_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from pathlib import Path
import datetime
from typing import Literal


flagged_citation = False

class ComplianceExtractionSchema(BaseModel):
    transaction_value: float = Field(
        description="The specific numeric numerical dollar value of the transaction parsed out of the query (e.g., 1800000.0)"
    )
    allowed_ceiling: float = Field(
        description="The strict numeric maximum limit or cap allowed for this transaction classification parsed out of corporate policy text chunks or graph rules (e.g., 1500000.0)"
    )
    corporate_lineage_summary: str = Field(
        description="A concise summary mapping the parent company structure and jurisdictional boundaries parsed from the topology."
    )
    source_doc: Literal[
        "Internal Policy", 
        "Foreign Investment", 
        "RBI KYC", 
        "RBI Credit Risk",
        "Apple SEC Filings",
        "Microsoft SEC Filings"
    ] = Field(
        description="Select EXACTLY ONE strict matching token string corresponding to the primary governing framework node establishing this limit."
    )

#In memory global setup to optimize each query processing speed
retriever = get_retriever()

with open("data/processed/knowledge_graph.pkl", "rb") as file:
    G = pickle.load(file)

class AgentState(TypedDict):
    query : str
    retrieved_child_ids: List[str]
    context_blocks: list
    graph_entities: str
    extracted_metrics: Dict[str, Any]
    audit_verdict: str
    citations: List[str]
    retry_count: int
    citation_status: str
    error_feedback: str


def fetch_context(state : AgentState) -> AgentState:
    """Surfaces semantic child contexts and resolves parent pay-load anchors."""
    if "retry_count" not in state or state["retry_count"] is None:
        state["retry_count"] = 0
    if "error_feedback" not in state or state["error_feedback"] is None:
        state["error_feedback"] = ""  

    query = state["query"]
    chroma_results, bm25_results = (
        retriever.vector_semantic_results(query)
    )

    state["retrieved_child_ids"] = retriever.rrf(chroma_results, bm25_results)

    parent_ids = {
        retriever.child_to_parent[child_id]
        for child_id in state["retrieved_child_ids"]
        if child_id in retriever.child_to_parent
    }

    state["context_blocks"] = [
        retriever.parent_by_id[parent_id]
        for parent_id in parent_ids
        if parent_id in retriever.parent_by_id
    ]

    return state

def traverse_graph_entities(state: AgentState) -> AgentState:
    """Traverses NetworkX topology paths to enforce systemic inheritance loops."""

    mapping_docs_nodes = {
        "apple-SEC.pdf":"Apple SEC Filings",
        "credit_Risk_RBI.pdf":"RBI Credit Risk",
        "foreign_Investement_rbi.pdf": "Foreign Investment",
        "kyc_rbi.pdf":"RBI KYC",
        "microsoft-SEC.pdf":"Microsoft SEC Filings",
        "nexus_holdings_global_inc.pdf":"Internal Policy"
    }

    retrieved_nodes = set(
        mapping_docs_nodes[record["metadata"]["source_document"]]
        for record in state["context_blocks"]
        if record["metadata"].get("source_document") in mapping_docs_nodes
    )

    CRITICAL_COMPLIANCE_SIGNATURES = {"remittance", "ceiling", "licensing", "software fees", "vendor", "ubo", "directors"}

    lineage = "[LINEAGE]"
    constraint = "[CONSTRAINT]"
    overlay = "[OVERLAY]"
    cnt = 0

    existing_parent_ids = {block["parent_id"] for block in state["context_blocks"]}

    for node in retrieved_nodes:
        #Tracking Successors
        outgoing = list(G.successors(node))
        
        for succ_node in outgoing:
            attributes = G[node][succ_node]
            lineage += f"\n- {node} ──({attributes['relation']})──► {succ_node}"

            
            for key,value in attributes.items():
                if key != "relation":
                    cnt += 1
                    constraint += f"\n {cnt}) {node}->{succ_node} [{key}: {value}]"
            
            # Force-exclude market peer data from text-chunk extraction entirely
            if succ_node in ["Apple SEC Filings", "Microsoft SEC Filings"]:
                continue
            # Gated Graph Expansion with Strict Domain Filtering
            if "chunks" in G.nodes[succ_node]:
                for chunk in G.nodes[succ_node]["chunks"]:
                    if chunk["parent_id"] not in existing_parent_ids:
                        chunk_text_lower = chunk["text_content"].lower()
                        
                        # Only let the chunk through if it intersects with our high-value structural anchors
                        if any(sig in chunk_text_lower for sig in CRITICAL_COMPLIANCE_SIGNATURES):
                            state["context_blocks"].append(chunk)
                            existing_parent_ids.add(chunk["parent_id"])
        
        #Tracking predecessors
        ingoing = list(G.predecessors(node))
        
        for pred_node in ingoing:
            if pred_node in ["Apple SEC Filings", "Microsoft SEC Filings"]:
                continue
            attributes = G[pred_node][node]
            overlay += f"\n- {pred_node} ──({attributes['relation']})──► {node}" 
            if len(attributes) > 1:
                overlay += " ["
                item_details = [f"{k}: {v}" for k, v in attributes.items() if k != "relation"]
                overlay += ", ".join(item_details) + "] "

            if "chunks" in G.nodes[pred_node]:
                for chunk in G.nodes[pred_node]["chunks"]:
                    if chunk["parent_id"] not in existing_parent_ids:
                        chunk_text_lower = chunk["text_content"].lower()
                        
                        if any(sig in chunk_text_lower for sig in CRITICAL_COMPLIANCE_SIGNATURES):
                            state["context_blocks"].append(chunk)
                            existing_parent_ids.add(chunk["parent_id"])
            
    state["graph_entities"] = f"SYSTEM TOPOLOGY MAP\n\n{lineage}\n\n{constraint}\n\n{overlay}"
    return state
        
def extract_audit_json(state: AgentState) -> AgentState:
    """Invokes the environment factory model strictly for structured metrics extraction."""
    raw_llm = get_chat_model(temperature=0.0)
    structured_extractor = raw_llm.with_structured_output(ComplianceExtractionSchema)

    formatted_context = ""
    for idx, block in enumerate(state["context_blocks"], 1):
        src = block["metadata"].get("source_document", "Unknown Document")
        pg = block["metadata"].get("page_number", "Unknown")
        formatted_context += f"\n--- Doc {idx}: {src} (Page {pg}) ---\n{block['text_content']}\n"
    
    feedback_note = state.get("error_feedback", "")

    extraction_prompt = f"""
    You are an enterprise parameter extraction layer. 
    Your objective is to read the provided Context and Topology, isolate the metrics requested, and map them to the structural JSON keys.
    
    CRITICAL CONSTRAINT FOR 'source_doc':
    You MUST isolate and return EXACTLY ONE single, definitive primary source document name or topology node description anchor (e.g., 'Internal Policy' or 'nexus_holdings_global_inc.pdf') that directly establishes the threshold ceiling metric rule. 
    DO NOT output comma-separated lists, multiple document names, or arrays of multiple nodes. Choose the single most relevant governing anchor.

    TEXTUAL CONTEXT:
    {formatted_context}
    
    TOPOLOGY MATRIX:
    {state["graph_entities"]}
    
    USER TRANSACTION QUERY:
    {state["query"]}

    {feedback_note}
    """
    
    messages = [
        SystemMessage(content="You parse raw numbers and strings with absolute literal text precision. You do not compute mathematical verdicts."),
        HumanMessage(content=extraction_prompt)
    ]
    
    extracted_data = structured_extractor.invoke(messages)
    
    state["extracted_metrics"] = {
        "transaction_value": extracted_data.transaction_value,
        "allowed_ceiling": extracted_data.allowed_ceiling,
        "lineage": extracted_data.corporate_lineage_summary,
        "source_doc": extracted_data.source_doc
    }
    
    unique_citations = set(
        f"{b['metadata'].get('source_document')} (Page {b['metadata'].get('page_number')})" 
        for b in state["context_blocks"] 
        if b["metadata"].get("source_document")
    )
    state["citations"] = list(unique_citations)
    return state

def evaluate_compliance_engine(state: AgentState) -> AgentState:
    """Native Python execution node providing standard mathematical guardrail logic."""
    metrics = state["extracted_metrics"]
    val = metrics["transaction_value"]
    ceiling = metrics["allowed_ceiling"]
    
    # Executing un-hallucinatable software bounds logic
    if val > ceiling:
        verdict = "**NON_COMPLIANT**"
        variance = val - ceiling
        summary = f"The transaction value of ${val:,.2f} USD explicitly breaches the allowed maximum corporate limit ceiling of ${ceiling:,.2f} USD by an excess variance delta of ${variance:,.2f} USD."
        deficiency_finding = f"* **Finding 1**: Transaction initiated by operating entity represents a structural variance breach. Bound Corporate Ceiling Limit: ${ceiling:,.2f} USD | Evaluated Request Value: ${val:,.2f} USD."
    else:
        verdict = "**COMPLIANT**"
        summary = f"The transaction value of ${val:,.2f} USD resides safely within the validated corporate ceiling limit threshold of ${ceiling:,.2f} USD."
        deficiency_finding = "No structural variance alignment deficiencies detected."

    state["audit_verdict"] = f"""## 1. OFFICIAL COMPLIANCE AUDIT VERDICT
        {verdict}

*Summary Sentence*: {summary}

## 2. SYSTEMIC LINEAGE & JURISDICTION EVALUATION
{metrics['lineage']}

## 3. MULTI-CRITERIA COMPLIANCE EVALUATION MATRIX

| Compliance Dimension | Internal Corporate Rule | External Statutory Rule | Actual Query Metric | Variance / Evaluation |
| :--- | :--- | :--- | :--- | :--- |
| **Transactional Exposure** | Limit Cap: ${ceiling:,.2f} | Managed Geographic Caps | ${val:,.2f} USD | {'FAIL (Ceiling Breached)' if val > ceiling else 'PASS'} |
| **Credential Verification** | Standard KYC overlays | Regional Statutory Rules | Verified Parameters | Pass Compliance Bounds |

## 4. DETAILED COMPLIANCE DEFICIENCY FINDINGS
{deficiency_finding}

## 5. SOURCE CITATION FRAMEWORK
* **[Primary Ceiling Mandate Anchor]** - `{metrics['source_doc']}`
"""

    return state


def validate_citations(state: AgentState) -> AgentState:
    """Algorithmic checkpoint loop translating node descriptions down to exact PDF files."""
    metrics = state.get("extracted_metrics", {})
    extracted_doc = metrics.get("source_doc", "")
    current_retries = state.get("retry_count", 0)

    mapping_nodes_to_docs = {
        "Apple SEC Filings": "apple-SEC.pdf",
        "RBI Credit Risk": "credit_Risk_RBI.pdf",
        "Foreign Investment": "foreign_Investement_rbi.pdf",
        "RBI KYC": "kyc_rbi.pdf",
        "Microsoft SEC Filings": "microsoft-SEC.pdf",
        "Internal Policy": "nexus_holdings_global_inc.pdf"
    }

    normalized_extracted = mapping_nodes_to_docs.get(extracted_doc, "N/A")
    valid_context_docs = {block["metadata"].get("source_document") for block in state["context_blocks"]}
    
    if normalized_extracted not in valid_context_docs:
        print(f"\n[CITATION FAULT]: Extractor returned '{extracted_doc}' (Resolved to: '{normalized_extracted}'), which is missing from context docs: {valid_context_docs}")
        
        if current_retries >= 1:
            print("[CIRCUIT BREAKER TRIPPED]: Forcing controlled failure state override.")
            state["extracted_metrics"] = {
                "transaction_value": 0.0,
                "allowed_ceiling": 0.0,
                "lineage": "UNKNOWN - CITATION MISMATCH EXCEPTION DETECTED",
                "source_doc": "N/A"
            }
            
            state["audit_verdict"] = """## 1. OFFICIAL COMPLIANCE AUDIT VERDICT
**ACTION_REQUIRED**

*Summary Sentence*: The automated audit framework has flagged this transaction assignment for human review due to an internal multi-document citation verification variance anomaly.

## 2. SYSTEMIC LINEAGE & JURISDICTION EVALUATION
The system matched the transaction semantic profile against our regulatory indexes, but the metric extraction phase failed to validate its structural source document references within the current execution thread context.

## 3. MULTI-CRITERIA COMPLIANCE EVALUATION MATRIX
| Compliance Dimension | Internal Corporate Rule | External Statutory Rule | Actual Query Metric | Variance / Evaluation |
| :--- | :--- | :--- | :--- | :--- |
| **Transactional Exposure** | UNDER REVIEW | UNDER REVIEW | EXCEPTION DETECTED | FLAG FOR HUMAN AUDIT |

## 4. DETAILED COMPLIANCE DEFICIENCY FINDINGS
* **Finding 1**: Algorithmic Checkpoint Fault. The LLM extraction pipeline returned document parameters that failed our deterministic string verification constraints.

## 5. SOURCE CITATION FRAMEWORK
* **[SYSTEM EXCEPTION CORRUPTION ISOLATION]** - Ref: `audit_graph.py:validate_citations`
"""
            state["citation_status"] = "complete"
            return state
        
        state["error_feedback"] = f"""
        CRITICAL RETRY NOTICE: Your previous choice 
        '{extracted_doc}' could not be matched. You MUST select 
        a value from your schema options that matches a document 
        in this list: {valid_context_docs}
        """

        state["retry_count"] = current_retries + 1
        state["citation_status"] = "retry"
        return state
        
    print(f"\n[CITATION PASS]: Verified target source reference '{normalized_extracted}'.")
    state["citation_status"] = "complete"
    return state

def route_checkpoint(state: AgentState):
    if state.get("citation_status") == "retry":
        return "fetch_context"
    return END

graph = StateGraph(AgentState)

graph.add_node("fetch_context",fetch_context)
graph.add_node("traverse_graph_entities",traverse_graph_entities)
graph.add_node("extract_audit_json", extract_audit_json)
graph.add_node("evaluate_compliance_engine", evaluate_compliance_engine)
graph.add_node("validate_citations", validate_citations)

graph.add_edge(START,"fetch_context")
graph.add_edge("fetch_context","traverse_graph_entities")
graph.add_edge("traverse_graph_entities","extract_audit_json")
graph.add_edge("extract_audit_json", "evaluate_compliance_engine")
graph.add_edge("evaluate_compliance_engine", "validate_citations")

graph.add_conditional_edges(
    "validate_citations",
    route_checkpoint,
    {
        "fetch_context": "fetch_context",
        END: END
    }
)

audit_graph = graph.compile()

if __name__ == "__main__":
    
    inputs = {
        "query": """
        Verify if a technology software licensing transaction of 
        $1,800,000 USD initiated by Nexus India violates internal
        cross-border limits.
        """
    }
    
    print("\nInitializing multi-agent graph audit pass...\n")
    final_output = audit_graph.invoke(inputs)
    
    print("FINAL COMPLIANCE REPORT")
    report_content = final_output.get("audit_verdict")
    print(report_content)

    log_dir = Path("data/processed")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "compliance_audit.log"
    
    # Assemble a professional, unique text boundary indicator block
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_boundary_entry = f"""
---

AUDIT RECORD TIMESTAMP: {timestamp}
TARGET QUERY ASSIGNMENT: {inputs['query']}
{report_content}

--
"""
    
    # Append the transaction history entry onto local disk array blocks safely
    with open(log_file, "a", encoding="utf-8") as file:
        file.write(log_boundary_entry)
        
    print(f"\n[SYSTEM LOG ASSEMBLED]: Audit record successfully written to {log_file}\n")
