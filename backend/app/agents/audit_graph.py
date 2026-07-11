from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
from ..core.retriever import get_retriever
import pickle 
import networkx as nx
from ..core.llm_factory import get_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

#In memory global setup to optimize each query processing speed
retriever = get_retriever()

with open("data/processed/knowledge_graph.pkl", "rb") as file:
    G = pickle.load(file)

llm = get_chat_model(temperature=0.0)

COMPLIANCE_AUDIT_PROMPT = """
    You are the core enterprise analytics brain of ComplianceNexus, a state-of-the-art multi-document automated regulatory auditing system. Your objective is to perform a rigorous, deterministic multi-criteria compliance evaluation of an operational transaction query against fetched multi-source corporate policy files and central banking statutory directions.

    Analyze the raw textual data and topological rules provided below to generate a formal compliance verdict.

    INPUT LAYER 1: UNIFIED TEXTUAL CONTEXT CORPORES
    These text chunks represent the uncorrupted 512-token Parent Context blocks retrieved from relevant files:
    {context_blocks_text}

    INPUT LAYER 2: SYSTEM TOPOLOGY MATRIX
    These represent the corporate inheritance lineage paths, edge parameters, and compliance constraints extracted dynamically from the NetworkX knowledge graph:
    {graph_entities_text}

    ACTIVE AUDIT USER QUERY:
    {user_query}
    
    CRITICAL EXECUTION CONSTRAINTS & GUARDRUILS:
    1. DETERMINISM OVERALL: Evaluate numbers, dates, ownership stakes, and currency ceilings with mathematical accuracy. Do not expand or loosely interpret thresholds.
    2. ZERO HALLUCINATION RULE: Rely strictly on the provided input layers. If a threshold or citation is absent, state that explicitly. Do not assume or extrapolate parameters.
    3. INHERITANCE EVALUATION: Evaluate if corporate ownership paths dictate policy inheritance (e.g., if a subsidiary inherits a parent policy requirement or must yield to a localized central banking ceiling).
    4. STRICT ANCHORING: Every analytical claim or metric match must be appended with an explicit layout citation indicating the exactly referenced source document name and page number.

    Your response must strictly utilize the following markdown hierarchy template. Do not deviate from these section headers:

    ## 1. OFFICIAL COMPLIANCE AUDIT VERDICT
    [Declare one of these precise tokens: **COMPLIANT**, **NON_COMPLIANT**, or **ACTION_REQUIRED**]
    *Summary Sentence*: Provide a direct, single-sentence operational summary detailing exactly why this transaction state was approved or flagged.

    ## 2. SYSTEMIC LINEAGE & JURISDICTION EVALUATION
    * Trace the corporate genealogy extracted from the topology map (e.g., identifying parent-subsidiary structures).
    * Define the geographic and statutory boundaries governing the active entity (e.g., matching the Indian entity to RBI circular frameworks).
    * Document which internal policy structures are inherited by this operating unit.

    ## 3. MULTI-CRITERIA COMPLIANCE EVALUATION MATRIX
    Provide a systematic evaluation cross-referencing the query metrics against individual operational bounds:

    | Compliance Dimension | Internal Corporate Rule | External Statutory Rule | Actual Query Metric | Variance / Evaluation |
    | :--- | :--- | :--- | :--- | :--- |
    | **Transactional Exposure** | [Internal spend limits / rules] | [Statutory banking limits] | [Query parameters] | [Pass/Fail Analysis] |
    | **Credential Verification** | [Required KYC mandates] | [Statutory KYC rules] | [Query attributes] | [Pass/Fail Analysis] |
    | **Governance / Exposure** | [Director ownership ceilings] | [Statutory exposure caps] | [Query context] | [Pass/Fail Analysis] |

    ## 4. DETAILED COMPLIANCE DEFICIENCY FINDINGS
    *If any dimension is NON_COMPLIANT or requires ACTION_REQUIRED, list the structural gaps sequentially. If completely COMPLIANT, explicitly state that no structural variance gaps were detected.*
    * **Finding 1**: [Describe the gap, the expected threshold, and the actual query metric value].

    ## 5. SOURCE CITATION FRAMEWORK
    List all specific source materials referenced to validate this verdict. Formulate each line strictly using this layout structure:
    * **[Citation Anchor]** - `document_name.pdf`, Page # (Section Reference)
    
    """

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

            if "chunks" in G.nodes[succ_node]:
                for chunk in G.nodes[succ_node]["chunks"]:
                    if chunk["parent_id"] not in existing_parent_ids:
                        state["context_blocks"].append(chunk)
                        existing_parent_ids.add(chunk["parent_id"])
        
        #Tracking predecessors
        ingoing = list(G.predecessors(node))
        
        for pred_node in ingoing:
            attributes = G[pred_node][node]
            overlay += f"\n- {pred_node} ──({attributes['relation']})──► {node}" 
            if len(attributes) > 1:
                overlay += " ["
                item_details = [f"{k}: {v}" for k, v in attributes.items() if k != "relation"]
                overlay += ", ".join(item_details) + "] "

            if "chunks" in G.nodes[pred_node]:
                for chunk in G.nodes[pred_node]["chunks"]:
                    if chunk["parent_id"] not in existing_parent_ids:
                        state["context_blocks"].append(chunk)
                        existing_parent_ids.add(chunk["parent_id"])
            
    state["graph_entities"] = f"SYSTEM TOPOLOGY MAP\n\n{lineage}\n\n{constraint}\n\n{overlay}"
    return state
        

def analyze_compliance(state: AgentState) -> AgentState:
    query_terms = set(retriever._tokenize(state["query"]))

    def relevance(block):
        block_terms = set(retriever._tokenize(block["text_content"]))
        return len(query_terms & block_terms)

    blocks_by_source = {}
    for block in state["context_blocks"]:
        source = block["metadata"].get("source_document", "Unknown")
        blocks_by_source.setdefault(source, []).append(block)

    for blocks in blocks_by_source.values():
        blocks.sort(key=relevance, reverse=True)

    selected_blocks = []
    selected_parent_ids = set()
    context_characters = 0
    max_context_characters = 180_000

    while blocks_by_source:
        for source in list(blocks_by_source):
            blocks = blocks_by_source[source]
            if not blocks:
                del blocks_by_source[source]
                continue

            block = blocks.pop(0)
            parent_id = block["parent_id"]
            block_size = len(block["text_content"])

            if parent_id in selected_parent_ids:
                continue
            if context_characters + block_size > max_context_characters:
                del blocks_by_source[source]
                continue

            selected_blocks.append(block)
            selected_parent_ids.add(parent_id)
            context_characters += block_size

    formatted_context = ""
    for idx, block in enumerate(selected_blocks, 1):
        src = block["metadata"].get("source_document", "Unknown")
        pg = block["metadata"].get("page_number", "Unknown")
        sec = block["metadata"].get("section_inferred", "Unknown Section")
        formatted_context += f"\n--- Document {idx}: {src} | Page {pg} | Section: {sec} ---\n"
        formatted_context += f"{block['text_content']}\n"

    # Inject parameters into the prompt
    sys_prompt = COMPLIANCE_AUDIT_PROMPT.format(
        context_blocks_text=formatted_context,
        graph_entities_text=state["graph_entities"],
        user_query=state["query"]
    )
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"Execute compliance audit pass for: {state['query']}")
    ]

    response = llm.invoke(messages)

    unique_citations = set()
    for block in selected_blocks:
        src = block["metadata"].get("source_document")
        pg = block["metadata"].get("page_number")
        if src and pg:
            unique_citations.add(f"{src} (Page {pg})")
            
    state["citations"] = list(unique_citations)

    state["audit_verdict"] = response.content
    return state

graph = StateGraph(AgentState)

graph.add_node("fetch_context",fetch_context)
graph.add_node("traverse_graph_entities",traverse_graph_entities)
graph.add_node("analyze_compliance",analyze_compliance)

graph.add_edge(START,"fetch_context")
graph.add_edge("fetch_context","traverse_graph_entities")
graph.add_edge("traverse_graph_entities","analyze_compliance")
graph.add_edge("analyze_compliance",END)

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
    print(final_output.get("audit_verdict"))
    print("\nVerified Source Citations Document Registry:")
    print(final_output.get("citations"))
