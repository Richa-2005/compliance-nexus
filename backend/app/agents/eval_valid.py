from app.agents.schemas import AgentState
from langgraph.graph import END
import re


def _text_blob(state: AgentState, metrics: dict) -> str:
    return " ".join(
        str(value)
        for value in (
            state.get("query", ""),
            metrics.get("transaction_type", ""),
            metrics.get("origin_entity", ""),
            metrics.get("destination_entity_or_type", ""),
            metrics.get("jurisdiction", ""),
            metrics.get("payment_purpose", ""),
            metrics.get("risk_factors", ""),
            metrics.get("applicable_rules", ""),
        )
    ).lower()


def _scenario_blob(state: AgentState, metrics: dict) -> str:
    return " ".join(
        str(value)
        for value in (
            state.get("query", ""),
            metrics.get("transaction_type", ""),
            metrics.get("origin_entity", ""),
            metrics.get("destination_entity_or_type", ""),
            metrics.get("jurisdiction", ""),
            metrics.get("payment_purpose", ""),
        )
    ).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _percent_values(text: str) -> list[float]:
    return [float(match) for match in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]


def _money_after(text: str, anchor_terms: tuple[str, ...]) -> float:
    for anchor in anchor_terms:
        match = re.search(
            rf"{anchor}[^$0-9]{{0,80}}\$?\s*([0-9][0-9,]*(?:\.\d+)?)",
            text,
        )
        if match:
            return float(match.group(1).replace(",", ""))
    return 0.0


def _status_from_checks(checks: list[dict]) -> str:
    results = {check.get("result") for check in checks}
    if "FAIL" in results:
        return "NON_COMPLIANT"
    if "REVIEW" in results:
        return "ACTION_REQUIRED"
    return "COMPLIANT"

def evaluate_compliance_engine(state: AgentState) -> AgentState:
    metrics = state["extracted_metrics"]
    val = metrics["transaction_value"]
    ceiling = metrics["allowed_ceiling"]
    variance = val - ceiling
    exposure_result = "FAIL" if val > ceiling else "PASS"
    source_doc = metrics.get("source_doc", "")
    transaction_text = _text_blob(state, metrics)
    scenario_text = _scenario_blob(state, metrics)
    is_cross_border = any(
        term in scenario_text
        for term in ("cross-border", "overseas", "foreign", "offshore", "outbound")
    )
    kyc_gap = _contains_any(
        scenario_text,
        ("anonymous", "no verified beneficiary", "newly onboarded", "kyc", "originator information"),
    )
    crypto_wallet = _contains_any(
        scenario_text,
        ("crypto", "cryptocurrency", "digital wallet"),
    )
    needs_foreign_investment_check = any(
        term in scenario_text
        for term in ("equity", "acquisition", "foreign investment", "fdi", "capital")
    )
    needs_director_exposure_check = _contains_any(
        scenario_text,
        ("director", "promoter", "credit", "loan", "lending", "advance"),
    )
    ownership_values = _percent_values(scenario_text)
    max_ownership = max(ownership_values) if ownership_values else 0.0
    cumulative_amount = _money_after(scenario_text, ("cumulative", "quarterly"))
    cumulative_total = cumulative_amount + val if cumulative_amount else val
    director_conflict = (
        max_ownership > 2.5
        and _contains_any(scenario_text, ("director", "promoter"))
        and _contains_any(scenario_text, ("vendor", "advance", "loan", "credit", "lending"))
    )
    foreign_investment_breach = (
        needs_foreign_investment_check
        and (val > 10_000_000 or max_ownership > 40)
    )
    cumulative_breach = cumulative_amount > 0 and cumulative_total > 5_000_000

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
            "evidence_items": []
        },
        {
            "name": "Primary Rule Source",
            "expected": "A governing source document must be identified for the ceiling rule.",
            "actual": source_doc or "N/A",
            "result": "PASS" if source_doc and source_doc != "N/A" else "FAIL",
            "variance": None,
            "evidence_items": []
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
            "evidence_items": []
        },
        {
            "name": "Cross-Border Classification",
            "expected": "The transaction should be classified for cross-border treatment when overseas, foreign, offshore, or outbound parties are involved.",
            "actual": (
                f"{metrics.get('origin_entity', 'Unknown origin')} -> "
                f"{metrics.get('destination_entity_or_type', 'Unknown destination')} | "
                f"{metrics.get('jurisdiction', 'Unknown jurisdiction')}"
            ),
            "result": "PASS" if is_cross_border else "REVIEW",
            "variance": None,
            "evidence_items": []
        },
        {
            "name": "KYC / Wire Transfer Evidence",
            "expected": "Cross-border transfers should have KYC or wire-transfer evidence available for reviewer traceability.",
            "actual": "Beneficiary/originator verification requires review" if kyc_gap else "No explicit KYC evidence gap detected",
            "result": "REVIEW" if kyc_gap or crypto_wallet else "PASS",
            "variance": None,
            "evidence_items": []
        },
        {
            "name": "Regulatory Overlay",
            "expected": "The audit should identify whether internal policy or external regulatory overlays govern the transaction.",
            "actual": source_doc or "N/A",
            "result": "PASS" if source_doc and source_doc != "N/A" else "REVIEW",
            "variance": None,
            "evidence_items": []
        },
    ]

    if needs_foreign_investment_check:
        state["audit_checks"].append(
            {
                "name": "Foreign Investment Route",
                "expected": "Equity, acquisition, FDI, or capital-route transactions should be checked against foreign-investment evidence.",
                "actual": metrics.get("payment_purpose", "Unknown purpose"),
                "result": "FAIL" if foreign_investment_breach else "REVIEW",
                "variance": None,
                "evidence_items": []
            }
        )

    if needs_director_exposure_check:
        state["audit_checks"].append(
            {
                "name": "Director Exposure Risk",
                "expected": "Vendor, credit, lending, or director-exposure risk should be checked against credit-risk or internal conflict evidence.",
                "actual": metrics.get("destination_entity_or_type", "Unknown counterparty"),
                "result": "FAIL" if director_conflict else "REVIEW",
                "variance": None,
                "evidence_items": []
            }
        )

    if cumulative_amount:
        state["audit_checks"].append(
            {
                "name": "Cumulative Quarterly Exposure",
                "expected": "Cumulative quarterly technology remittances should remain at or below $5,000,000.00 USD.",
                "actual": f"${cumulative_total:,.2f} USD including current transaction",
                "result": "FAIL" if cumulative_breach else "PASS",
                "variance": cumulative_total - 5_000_000,
                "evidence_items": []
            }
        )

    if crypto_wallet:
        state["audit_checks"].append(
            {
                "name": "Digital Asset Beneficiary Verification",
                "expected": "Digital asset treasury transfers should identify a verified beneficiary and wallet counterparty.",
                "actual": metrics.get("destination_entity_or_type", "Anonymous or unresolved digital wallet"),
                "result": "REVIEW",
                "variance": None,
                "evidence_items": []
            }
        )

    status = _status_from_checks(state["audit_checks"])
    if status == "ACTION_REQUIRED":
        verdict = "**ACTION_REQUIRED**"
        summary = "The transaction is within the numeric ceiling but contains unresolved compliance facts that require reviewer confirmation before approval."
        deficiency_finding = "* **Finding 1**: One or more deterministic checks returned REVIEW because the transaction requires additional evidence or beneficiary verification."

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
