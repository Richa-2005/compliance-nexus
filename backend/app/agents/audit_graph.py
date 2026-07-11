from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
from app.core.retriever import get_retriever
import pickle 
import networkx as nx

#In memory global setup to optimize each query processing speed
retriever = get_retriever()
with open("data/processed/knowledge_graph.pkl", "rb") as file:
    G = pickle.load(file)

class AgentState(TypedDict):
    query : str
    retrieved_child_ids: List[str]
    context_blocks: list
    graph_entities: str
    audit_verdict: str
    citations: List[str]


def fetch_context(state : AgentState) -> AgentState:
    
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
    )
    
    lineage = "[LINEAGE]"
    contraint = "[CONSTRAINT]"
    overlay = "[OVERLAY]"
    cnt = 0

    existing_parent_ids = {block["parent_id"] for block in state["context_blocks"]}

    for node in retrieved_nodes:
        #Tracking Successors
        outgoing = list(G.successors(node))
        
        for succ_node in outgoing:
            attrs = G[node][succ_node]
            lineage += f"\n- {node} ──({attrs['relation']})──► {succ_node}"

            
            for key,value in attributes.items():
                if key != "relation":
                    cnt += 1
                    constraint += f"\n {cnt}) {node}->{succ_node} [{key}: {value}]"
        
            if "chunks" in G.nodes[succ_node]:
                for chunk in G.nodes[succ_node]["chunks"]:
                    if chunk["parent_id"] not in existing_parent_ids:
                        state["context_blocks"].append(chunk)
                        existing_parent_ids.add(chunk["parent_id"])

        #Tracking predecessors
        ingoing = list(G.predecessors(node))
        
        for pred_node in ingoing:
            attributes = G[pred_node][node]
            overlay += f"\n- {pred_node} ──({attrs['relation']})──► {node}" 
            if len(attrs) > 1:
                overlay += " ["
                item_details = [f"{k}: {v}" for k, v in attrs.items() if k != "relation"]
                overlay += ", ".join(item_details) + "] "
            
            if "chunks" in G.nodes[pred_node]:
                for chunk in G.nodes[pred_node]["chunks"]:
                    if chunk["parent_id"] not in existing_parent_ids:
                        state["context_blocks"].append(chunk)
                        existing_parent_ids.add(chunk["parent_id"])
        
    state["graph_entities"] = f"SYSTEM TOPOLOGY MAP\n\n{lineage}\n\n{constraint}\n\n{overlay}"
    return state
        

        






