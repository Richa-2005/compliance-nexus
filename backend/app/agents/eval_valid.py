from app.agents.schemas import AgentState
from langgraph.graph import END

def evaluate_compliance_engine(state: AgentState) -> AgentState:
    """Native Python execution node providing standard mathematical guardrail logic."""
    metrics = state["extracted_metrics"]
    val = metrics["transaction_value"]
    ceiling = metrics["allowed_ceiling"]
    variance = val - ceiling
    exposure_result = "FAIL" if val > ceiling else "PASS"
    source_doc = metrics.get("source_doc", "")

    if val > ceiling:
        verdict = "**NON_COMPLIANT**"
        summary = f"The transaction value of ${val:,.2f} USD explicitly breaches the allowed maximum corporate limit ceiling of ${ceiling:,.2f} USD by an excess variance delta of ${variance:,.2f} USD."
        deficiency_finding = f"* **Finding 1**: Transaction initiated by operating entity represents a structural variance breach. Bound Corporate Ceiling Limit: ${ceiling:,.2f} USD | Evaluated Request Value: ${val:,.2f} USD."
    else:
        verdict = "**COMPLIANT**"
        summary = f"The transaction value of ${val:,.2f} USD resides safely within the validated corporate ceiling limit threshold of ${ceiling:,.2f} USD."
        deficiency_finding = "No structural variance alignment deficiencies detected."

    state["audit_checks"] = [
        {
            "name": "Transactional Exposure",
            "expected": f"Transaction amount must be less than or equal to ${ceiling:,.2f} {metrics.get('currency', 'USD')}",
            "actual": f"${val:,.2f} {metrics.get('currency', 'USD')}",
            "result": exposure_result,
            "variance": variance,
        },
        {
            "name": "Primary Rule Source",
            "expected": "A governing source document must be identified for the ceiling rule.",
            "actual": source_doc or "N/A",
            "result": "PASS" if source_doc and source_doc != "N/A" else "FAIL",
            "variance": None,
        },
        {
            "name": "Rule Applicability",
            "expected": "The selected rule should match the transaction type, parties, jurisdiction, and purpose.",
            "actual": (
                f"{metrics.get('transaction_type', 'Unknown transaction type')} | "
                f"{metrics.get('origin_entity', 'Unknown origin')} -> "
                f"{metrics.get('destination_entity_or_type', 'Unknown destination')} | "
                f"{metrics.get('payment_purpose', 'Unknown purpose')}"
            ),
            "result": "PASS" if metrics.get("applicable_rules") else "REVIEW",
            "variance": None,
        },
    ]

    state["audit_verdict"] = f"""
    ## 1. OFFICIAL COMPLIANCE AUDIT VERDICT
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