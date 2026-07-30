from langgraph.graph import StateGraph, START, END
from app.agents.schemas import AgentState
from app.agents.context import fetch_context, traverse_graph_entities
from app.agents.generate_llm import extract_audit_json, generate_audit_rationale
from app.agents.eval_valid import evaluate_compliance_engine, validate_citations, route_checkpoint

graph = StateGraph(AgentState)

graph.add_node("fetch_context",fetch_context)
graph.add_node("traverse_graph_entities",traverse_graph_entities)
graph.add_node("extract_audit_json", extract_audit_json)
graph.add_node("evaluate_compliance_engine", evaluate_compliance_engine)
graph.add_node("generate_audit_rationale", generate_audit_rationale)
graph.add_node("validate_citations", validate_citations)

graph.add_edge(START,"fetch_context")
graph.add_edge("fetch_context","traverse_graph_entities")
graph.add_edge("traverse_graph_entities","extract_audit_json")
graph.add_edge("extract_audit_json", "evaluate_compliance_engine")
graph.add_edge("evaluate_compliance_engine", "generate_audit_rationale")
graph.add_edge("generate_audit_rationale", "validate_citations")

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
        Verify if a technology software licensing transaction to an overseas vendor of 
        $1,800,000 USD initiated by Nexus India violates internal
        cross-border limits .
        """
    }
    
    print("\nInitializing multi-agent graph audit pass...\n")
    final_output = audit_graph.invoke(inputs)
    
    print("FINAL COMPLIANCE REPORT")
    report_content = final_output.get("audit_verdict")
    print(report_content)
    print(final_output.keys())
    print(final_output.get("extracted_metrics"))
    print(final_output.get("audit_checks"))
    print(final_output.get("audit_rationale"))
    
   
    