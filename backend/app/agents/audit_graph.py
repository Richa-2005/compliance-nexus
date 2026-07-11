from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
from app.core.retriever import get_retriever

retriever = get_retriever()

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

    

    
