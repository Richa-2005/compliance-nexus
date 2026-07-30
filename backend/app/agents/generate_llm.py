from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.schemas import (
    ComplianceExtractionSchema, AuditRationaleSchema, AgentState
)
from app.core.llm_factory import get_chat_model
import re
from app.core.config import settings


def _normalize(value) -> str:
    return str(value or "").strip().lower()


def _money_terms(value) -> set[str]:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return set()

    if amount <= 0:
        return set()

    whole = int(amount)
    return {
        str(whole),
        f"{whole:,}",
        f"{amount:,.0f}",
        f"{amount:,.2f}",
    }


def _split_terms(value) -> set[str]:
    text = _normalize(value)
    if not text:
        return set()

    terms = {text}
    terms.update(part for part in text.replace("-", " ").split() if len(part) >= 4)
    return terms


def _looks_like_currency_or_amount(value) -> bool:
    text = _normalize(value)
    if not text:
        return True
    return text in {"usd", "inr", "eur", "gbp"} or bool(re.fullmatch(r"[$,\d.]+", text))


def _infer_destination_from_query(query: str) -> str:
    match = re.search(
        r"\bto\s+(?:an?\s+)?(?P<destination>[^.,]+?)(?:\s+violates|\s+for|\s+when|$)",
        query,
        flags=re.IGNORECASE,
    )
    if not match:
        return "Unknown counterparty"

    destination = " ".join(match.group("destination").split())
    return destination[:1].lower() + destination[1:] if destination else "Unknown counterparty"


def normalize_extracted_metrics(metrics: dict, query: str) -> dict:
    """Apply deterministic cleanup to fields LLMs commonly confuse."""
    normalized = dict(metrics)
    currency = normalized.get("currency")

    if _looks_like_currency_or_amount(normalized.get("destination_entity_or_type")):
        normalized["destination_entity_or_type"] = _infer_destination_from_query(query)

    if currency:
        normalized["currency"] = str(currency).upper()

    return normalized


def select_relevant_evidence(
    evidence_items: list[dict],
    metrics: dict,
    max_items: int = 8,
) -> list[dict]:
    """Select evidence using named audit relevance criteria, not sample-specific terms."""
    expected_doc = settings.NODE_TO_DOC.get(metrics.get("source_doc"))
    ceiling_terms = _money_terms(metrics.get("allowed_ceiling"))

    transaction_terms = set()
    for key in (
        "transaction_type",
        "origin_entity",
        "destination_entity_or_type",
        "jurisdiction",
        "payment_purpose",
    ):
        transaction_terms.update(_split_terms(metrics.get(key)))

    ranked = []
    for index, item in enumerate(evidence_items):
        snippet = _normalize(item.get("snippet"))
        source_document = item.get("source_document")
        criteria = []
        priority = 0

        has_ceiling_match = any(term and term.lower() in snippet for term in ceiling_terms)
        matched_transaction_terms = sorted(
            term for term in transaction_terms if term and term in snippet
        )
        matched_rule_terms = sorted(term for term in settings.RULE_LANGUAGE_TERMS if term in snippet)

        if has_ceiling_match and matched_transaction_terms and matched_rule_terms:
            criteria.append("direct_threshold_rule_match")
            priority += settings.EVIDENCE_SELECTION_CRITERIA["direct_threshold_rule_match"]

        if expected_doc and source_document == expected_doc:
            criteria.append("primary_source_match")
            priority += settings.EVIDENCE_SELECTION_CRITERIA["primary_source_match"]

        if has_ceiling_match:
            criteria.append("ceiling_value_match")
            priority += settings.EVIDENCE_SELECTION_CRITERIA["ceiling_value_match"]

        if matched_transaction_terms:
            criteria.append("transaction_fact_match")
            priority += settings.EVIDENCE_SELECTION_CRITERIA["transaction_fact_match"]

        if matched_rule_terms:
            criteria.append("rule_language_match")
            priority += settings.EVIDENCE_SELECTION_CRITERIA["rule_language_match"]

        if priority:
            enriched_item = {
                **item,
                "selection_priority": priority,
                "selection_criteria": criteria,
                "matched_terms": {
                    "transaction": matched_transaction_terms[:8],
                    "rule_language": matched_rule_terms[:8],
                    "ceiling": sorted(term for term in ceiling_terms if term.lower() in snippet),
                },
            }
            ranked.append((priority, index, enriched_item))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    selected = [item for _, _, item in ranked[:max_items]]
    if any("direct_threshold_rule_match" in item.get("selection_criteria", []) for item in selected):
        direct_items = [
            item
            for item in selected
            if "direct_threshold_rule_match" in item.get("selection_criteria", [])
        ]
        contextual_items = [
            item
            for item in selected
            if "direct_threshold_rule_match" not in item.get("selection_criteria", [])
            and "primary_source_match" in item.get("selection_criteria", [])
        ]
        return (direct_items + contextual_items)[:max_items]
    return selected


def promote_primary_source_from_evidence(metrics: dict, selected_evidence: list[dict]) -> dict:
    """Prefer the document that directly states the threshold rule over a cross-reference node."""
    if not selected_evidence:
        return metrics

    strongest = selected_evidence[0]
    if "direct_threshold_rule_match" not in strongest.get("selection_criteria", []):
        return metrics

    promoted_source = settings.DOC_TO_NODE.get(strongest.get("source_document"))
    if not promoted_source:
        return metrics

    updated = dict(metrics)
    updated["source_doc"] = promoted_source
    updated["primary_evidence_summary"] = (
        f"{strongest.get('source_document')} page {strongest.get('page_number')} "
        "directly states the selected threshold rule."
    )
    return updated


def synchronize_checks_with_metrics(checks: list[dict], metrics: dict) -> list[dict]:
    synchronized = []
    for check in checks:
        updated = dict(check)
        if updated.get("name") == "Primary Rule Source":
            source_doc = metrics.get("source_doc") or "N/A"
            updated["actual"] = source_doc
            updated["result"] = "PASS" if source_doc != "N/A" else "FAIL"
        elif updated.get("name") == "Rule Applicability":
            updated["actual"] = (
                f"{metrics.get('transaction_type', 'Unknown transaction type')} | "
                f"{metrics.get('origin_entity', 'Unknown origin')} -> "
                f"{metrics.get('destination_entity_or_type', 'Unknown destination')} | "
                f"{metrics.get('payment_purpose', 'Unknown purpose')}"
            )
        synchronized.append(updated)
    return synchronized


def _format_money(value, currency: str = "USD") -> str:
    try:
        return f"${float(value):,.2f} {currency}"
    except (TypeError, ValueError):
        return f"UNRESOLVED {currency}"


def _render_evidence_table(evidence_items: list[dict]) -> str:
    if not evidence_items:
        return "| Source | Page | Extracted Evidence | Selection Basis |\n| :--- | :--- | :--- | :--- |\n| N/A | N/A | No transaction-specific evidence selected. | Human review required. |"

    rows = [
        "| Source | Page | Extracted Evidence | Selection Basis |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for item in evidence_items[:6]:
        snippet = " ".join(str(item.get("snippet", "")).split())
        if len(snippet) > 280:
            snippet = f"{snippet[:277]}..."
        criteria = ", ".join(item.get("selection_criteria", [])) or "retrieved_context"
        rows.append(
            f"| {item.get('source_document', 'Unknown')} | "
            f"{item.get('page_number', 'Unknown')} | "
            f"{snippet} | {criteria} |"
        )
    return "\n".join(rows)


def _render_checks_table(checks: list[dict]) -> str:
    rows = [
        "| Check | Expected | Actual | Result | Variance |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for check in checks:
        variance = check.get("variance")
        variance_display = "N/A" if variance is None else f"{float(variance):,.2f}"
        rows.append(
            f"| {check.get('name', 'Unknown')} | "
            f"{check.get('expected', 'N/A')} | "
            f"{check.get('actual', 'N/A')} | "
            f"{check.get('result', 'REVIEW')} | "
            f"{variance_display} |"
        )
    return "\n".join(rows)


def build_audit_verdict(state: AgentState) -> str:
    metrics = state.get("extracted_metrics", {})
    checks = state.get("audit_checks", [])
    rationale = state.get("audit_rationale", {})
    evidence = state.get("selected_evidence_items", [])
    currency = metrics.get("currency", "USD")
    status = "NON_COMPLIANT" if any(c.get("result") == "FAIL" for c in checks) else "COMPLIANT"

    findings = rationale.get("deficiency_findings", [])
    findings_markdown = "\n".join(f"* {finding}" for finding in findings) or "* No deficiency findings returned."

    return f"""## 1. OFFICIAL COMPLIANCE AUDIT VERDICT
**{status}**

*Summary Sentence*: {rationale.get("executive_summary", "No rationale summary returned.")}

## 2. TRANSACTION FACTS EXTRACTED
| Field | Value |
| :--- | :--- |
| Transaction Type | {metrics.get("transaction_type", "Unknown")} |
| Origin Entity | {metrics.get("origin_entity", "Unknown")} |
| Destination / Counterparty Type | {metrics.get("destination_entity_or_type", "Unknown")} |
| Jurisdiction | {metrics.get("jurisdiction", "Unknown")} |
| Payment Purpose | {metrics.get("payment_purpose", "Unknown")} |
| Transaction Value | {_format_money(metrics.get("transaction_value"), currency)} |
| Allowed Ceiling | {_format_money(metrics.get("allowed_ceiling"), currency)} |
| Primary Rule Source | {metrics.get("source_doc", "Unknown")} |

## 3. APPLICABLE RULE AND RATIONALE
{rationale.get("rule_application_reasoning", "No rule rationale returned.")}

## 4. DETERMINISTIC AUDIT CHECKS
{_render_checks_table(checks)}

## 5. SELECTED EVIDENCE
{_render_evidence_table(evidence)}

## 6. DEFICIENCY FINDINGS
{findings_markdown}

## 7. RECOMMENDED ACTION
**{rationale.get("recommended_action", "HUMAN_REVIEW")}**
"""


def filter_deficiency_findings(findings: list[str], selected_evidence: list[dict]) -> list[str]:
    has_direct_evidence = any(
        "direct_threshold_rule_match" in item.get("selection_criteria", [])
        for item in selected_evidence
    )
    if not has_direct_evidence:
        return findings

    filtered = []
    for finding in findings:
        text = _normalize(finding)
        if "lack of evidence" in text and "primary rule source" in text:
            continue
        if "human review is needed" in text and "primary rule source" in text:
            continue
        filtered.append(finding)
    return filtered

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
    Choose the source that contains the actual governing text or exact numeric ceiling. If a graph edge only cross-references another framework but an internal policy chunk contains the exact threshold language, choose Internal Policy.
    DO NOT output comma-separated lists, multiple document names, or arrays of multiple nodes. Choose the single most relevant governing anchor.

    FIELD EXTRACTION RULES:
    - destination_entity_or_type must be the recipient or recipient category. It must never be a currency, amount, or jurisdiction.
    - currency must be only a currency code such as USD, INR, or EUR.
    - applicable_rules must include only rules supported by the supplied context or topology.
    - primary_evidence_summary must mention the document/page evidence that directly supports the ceiling or rule.

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
    
    extracted_metrics = {
        "transaction_value": extracted_data.transaction_value,
        "allowed_ceiling": extracted_data.allowed_ceiling,
        "lineage": extracted_data.corporate_lineage_summary,
        "source_doc": extracted_data.source_doc,
        "transaction_type" : extracted_data.transaction_type,
        "origin_entity" : extracted_data.origin_entity,
        "destination_entity_or_type" :extracted_data.destination_entity_or_type,
        "jurisdiction":extracted_data.jurisdiction,
        "payment_purpose":extracted_data.payment_purpose,
        "currency":extracted_data.currency,
        "applicable_rules" : extracted_data.applicable_rules,
        "risk_factors" :extracted_data.risk_factors,
        "primary_evidence_summary": extracted_data.primary_evidence_summary,
    }
    state["extracted_metrics"] = normalize_extracted_metrics(
        extracted_metrics,
        state["query"],
    )
    
    unique_citations = set(
        f"{b['metadata'].get('source_document')} (Page {b['metadata'].get('page_number')})" 
        for b in state["context_blocks"] 
        if b["metadata"].get("source_document")
    )
    state["citations"] = list(unique_citations)

    record = []
    for block in state["context_blocks"]:
        record.append({
            "source_document": block["metadata"].get("source_document"),
            "page_number": block["metadata"].get("page_number"),
            "snippet": block["text_content"][:600],
            "used_for": "",
            "extracted_fact": ""
        })
    state["evidence_items"] = record
    return state


def generate_audit_rationale(state: AgentState) -> AgentState:
    raw_llm = get_chat_model(temperature=0.0)
    structured_rationale = raw_llm.with_structured_output(AuditRationaleSchema)
    selected_evidence = select_relevant_evidence(
        state.get("evidence_items", []),
        state.get("extracted_metrics", {}),
    )
    state["selected_evidence_items"] = selected_evidence
    state["extracted_metrics"] = promote_primary_source_from_evidence(
        state.get("extracted_metrics", {}),
        selected_evidence,
    )
    selected_evidence = select_relevant_evidence(
        state.get("evidence_items", []),
        state.get("extracted_metrics", {}),
    )
    state["selected_evidence_items"] = selected_evidence
    state["audit_checks"] = synchronize_checks_with_metrics(
        state.get("audit_checks", []),
        state.get("extracted_metrics", {}),
    )

    has_failed_check = any(
        check.get("result") == "FAIL"
        for check in state.get("audit_checks", [])
    )

    prompt = f"""
    You are a compliance audit rationale writer.

    You must NOT calculate the verdict yourself.
    You must explain the deterministic audit result using only the supplied extracted facts,
    audit checks, and evidence items.

    USER QUERY:
    {state["query"]}

    EXTRACTED METRICS:
    {state["extracted_metrics"]}

    DETERMINISTIC AUDIT CHECKS:
    {state["audit_checks"]}

    SELECTED EVIDENCE ITEMS:
    {selected_evidence}

    Instructions:
    - Treat deterministic audit checks as controlling. If a check result is FAIL, your explanation must not recommend approval.
    - The selected rule source is EXTRACTED METRICS.source_doc. Do not call any other rule the selected rule.
    - Explain why the selected rule applies.
    - Explain the failed or passed checks.
    - Cite document names and page numbers from selected evidence items.
    - Prefer evidence items with primary_source_match and ceiling_value_match.
    - Do not invent document names, thresholds, parties, or regulations.
    - If evidence is weak or missing, say that human review is needed.
    """

    result = structured_rationale.invoke([
        SystemMessage(content="You write concise, evidence-backed audit reasoning. You do not invent facts."),
        HumanMessage(content=prompt)
    ])

    recommended_action = result.recommended_action
    if has_failed_check:
        recommended_action = "BLOCK_REMITTANCE"
    elif not selected_evidence:
        recommended_action = "REQUEST_MORE_EVIDENCE"

    state["audit_rationale"] = {
        "executive_summary": result.executive_summary,
        "rule_application_reasoning": result.rule_application_reasoning,
        "evidence_summary": result.evidence_summary,
        "deficiency_findings": filter_deficiency_findings(
            result.deficiency_findings,
            selected_evidence,
        ),
        "recommended_action": recommended_action,
    }
    state["audit_verdict"] = build_audit_verdict(state)

    return state
