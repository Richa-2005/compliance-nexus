from app.agents.schemas import  AgentState
from app.core.retriever import get_retriever
import pickle 

retriever = get_retriever()

with open("data/processed/knowledge_graph.pkl", "rb") as file:
    G = pickle.load(file)


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