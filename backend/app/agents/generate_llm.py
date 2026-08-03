from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.schemas import (
    ComplianceExtractionSchema, AuditRationaleSchema, AgentState
)
from app.core.llm_factory import get_chat_model
import os
import re
from app.core.config import settings

EXTRACTION_CONTEXT_CHAR_LIMIT = int(os.getenv("EXTRACTION_CONTEXT_CHAR_LIMIT", "18000"))
EXTRACTION_CONTEXT_BLOCK_LIMIT = int(os.getenv("EXTRACTION_CONTEXT_BLOCK_LIMIT", "14"))


def _normalize(value) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


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


def _query_terms(query: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", _normalize(query))
        if term not in {"with", "where", "from", "into", "that", "this", "than", "under"}
    }


def _query_money_terms(query: str) -> set[str]:
    terms = set()
    for match in re.findall(r"\$?\s*([0-9][0-9,]*(?:\.\d+)?)", query):
        raw = match.replace(",", "")
        try:
            terms.update(_money_terms(float(raw)))
        except ValueError:
            continue
    return {term.lower() for term in terms}


def _source_priority(source_document: str, query: str) -> int:
    query_text = _normalize(query)
    priority = 0
    if source_document == "nexus_holdings_global_inc.pdf":
        priority += 35
    if source_document == "kyc_rbi.pdf" and _contains_any(
        query_text, ("kyc", "wire", "beneficiary", "originator", "wallet", "crypto")
    ):
        priority += 30
    if source_document == "credit_Risk_RBI.pdf" and _contains_any(
        query_text, ("director", "promoter", "credit", "loan", "advance", "lending")
    ):
        priority += 30
    if source_document == "foreign_Investement_rbi.pdf" and _contains_any(
        query_text, ("foreign investment", "fdi", "equity", "acquisition", "ownership", "capital")
    ):
        priority += 30
    if source_document in {"apple-SEC.pdf", "microsoft-SEC.pdf"} and _contains_any(
        query_text, ("apple", "microsoft", "sec", "benchmark")
    ):
        priority += 18
    return priority


def rank_context_blocks_for_extraction(
    context_blocks: list[dict],
    query: str,
    max_blocks: int = EXTRACTION_CONTEXT_BLOCK_LIMIT,
    max_chars: int = EXTRACTION_CONTEXT_CHAR_LIMIT,
) -> str:
    query_text = _normalize(query)
    query_terms = _query_terms(query)
    money_terms = _query_money_terms(query)
    ranked = []

    for index, block in enumerate(context_blocks):
        source_document = block.get("metadata", {}).get("source_document", "")
        page_number = block.get("metadata", {}).get("page_number", "Unknown")
        text_content = str(block.get("text_content", ""))
        normalized_text = _normalize(text_content)
        score = _source_priority(source_document, query)
        score += sum(3 for term in query_terms if term in normalized_text)
        score += sum(12 for term in money_terms if term in normalized_text)
        score += sum(10 for term in settings.RULE_LANGUAGE_TERMS if term in normalized_text)

        if _contains_any(query_text, ("cumulative", "quarterly")) and _contains_any(
            normalized_text, ("cumulative", "quarterly", "5,000,000", "5000000")
        ):
            score += 35
        if _contains_any(query_text, ("split", "invoice", "identical contract")) and _contains_any(
            normalized_text, ("multi-invoice", "splitting", "identical contract", "deviations")
        ):
            score += 35
        if _contains_any(query_text, ("director", "promoter", "advance", "loan")) and _contains_any(
            normalized_text, ("2.5", "director", "promoter", "credit", "advance")
        ):
            score += 35
        if _contains_any(query_text, ("kyc", "wire", "beneficiary", "originator")) and _contains_any(
            normalized_text, ("beneficial owner", "wire transfer", "originator", "beneficiary", "kyc")
        ):
            score += 35
        if _contains_any(query_text, ("foreign investment", "equity", "acquisition")) and _contains_any(
            normalized_text, ("automatic route", "foreign investment", "equity", "approval route")
        ):
            score += 35

        if score:
            ranked.append((score, index, source_document, page_number, text_content))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    selected = []
    seen_sources = set()
    for row in ranked:
        if len(selected) >= max_blocks:
            break
        source_document = row[2]
        if source_document not in seen_sources:
            selected.append(row)
            seen_sources.add(source_document)
    for row in ranked:
        if len(selected) >= max_blocks:
            break
        if row not in selected:
            selected.append(row)

    parts = []
    remaining_chars = max_chars
    for rank, (_, original_index, source_document, page_number, text_content) in enumerate(selected, 1):
        if remaining_chars <= 0:
            break
        header = f"\n--- Ranked Evidence {rank}: {source_document or 'Unknown Document'} (Page {page_number}; Retrieved #{original_index + 1}) ---\n"
        available = remaining_chars - len(header)
        if available <= 0:
            break
        body = text_content[:available]
        parts.append(f"{header}{body}\n")
        remaining_chars -= len(parts[-1])
    return "".join(parts)


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


def _evidence_matches(item: dict, docs: set[str], terms: set[str]) -> bool:
    source_document = item.get("source_document")
    snippet = _normalize(item.get("snippet"))
    return source_document in docs or any(term in snippet for term in terms)


def _rank_check_evidence(items: list[dict], docs: set[str], terms: set[str], limit: int = 3) -> list[dict]:
    ranked = []
    for index, item in enumerate(items):
        snippet = _normalize(item.get("snippet"))
        score = 0
        source_matches = item.get("source_document") in docs
        if docs and not source_matches:
            continue
        if source_matches:
            score += 30
        score += sum(8 for term in terms if term in snippet)
        if score and "direct_threshold_rule_match" in item.get("selection_criteria", []):
            score += 20
        if score:
            ranked.append((score, index, item))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in ranked[:limit]]


def attach_evidence_to_checks(state: AgentState) -> list[dict]:
    evidence_items = state.get("evidence_items", [])
    selected_evidence = state.get("selected_evidence_items", [])
    all_evidence = selected_evidence + [
        item for item in evidence_items if item not in selected_evidence
    ]
    routed_checks = []

    route_config = {
        "Transactional Exposure": (
            {"nexus_holdings_global_inc.pdf"},
            {"ceiling", "capped", "cap", "limit", "threshold", "remittance"},
        ),
        "Primary Rule Source": (
            {"nexus_holdings_global_inc.pdf"},
            {"policy", "governing", "threshold", "ceiling", "inherited", "binding"},
        ),
        "Rule Applicability": (
            {"nexus_holdings_global_inc.pdf"},
            {"licensing", "software", "vendor", "nexus india", "overseas"},
        ),
        "Cross-Border Classification": (
            {"kyc_rbi.pdf", "nexus_holdings_global_inc.pdf"},
            {"cross-border", "wire transfer", "overseas", "foreign", "outbound"},
        ),
        "KYC / Wire Transfer Evidence": (
            {"kyc_rbi.pdf"},
            {"kyc", "wire transfer", "originator", "beneficiary", "customer identification"},
        ),
        "Regulatory Overlay": (
            {"nexus_holdings_global_inc.pdf", "foreign_Investement_rbi.pdf", "kyc_rbi.pdf", "credit_Risk_RBI.pdf"},
            {"statutory", "regulatory", "rbi", "foreign investment", "compliance", "overlay"},
        ),
        "Foreign Investment Route": (
            {"foreign_Investement_rbi.pdf"},
            {"foreign investment", "fdi", "equity", "acquisition", "automatic route", "approval"},
        ),
        "Director Exposure Risk": (
            {"credit_Risk_RBI.pdf", "nexus_holdings_global_inc.pdf"},
            {"director", "credit", "exposure", "lending", "vendor", "promoter"},
        ),
        "Cumulative Quarterly Exposure": (
            {"nexus_holdings_global_inc.pdf"},
            {"quarterly", "cumulative", "technology", "remittance", "threshold", "limit"},
        ),
        "Digital Asset Beneficiary Verification": (
            {"kyc_rbi.pdf", "nexus_holdings_global_inc.pdf"},
            {"digital", "wallet", "beneficiary", "kyc", "anonymous", "originator"},
        ),
    }

    for check in state.get("audit_checks", []):
        updated = dict(check)
        docs, terms = route_config.get(check.get("name"), (set(), set()))
        routed = _rank_check_evidence(all_evidence, docs, terms)
        if not routed and selected_evidence:
            routed = selected_evidence[:1]
        updated["evidence_items"] = routed
        routed_checks.append(updated)

    return routed_checks


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
        "| Check | Expected | Actual | Result | Evidence |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for check in checks:
        evidence = check.get("evidence_items") or []
        evidence_display = ", ".join(
            f"{item.get('source_document', 'Unknown')} p.{item.get('page_number', 'N/A')}"
            for item in evidence[:2]
        ) or "No evidence attached"
        rows.append(
            f"| {check.get('name', 'Unknown')} | "
            f"{check.get('expected', 'N/A')} | "
            f"{check.get('actual', 'N/A')} | "
            f"{check.get('result', 'REVIEW')} | "
            f"{evidence_display} |"
        )
    return "\n".join(rows)


def build_audit_verdict(state: AgentState) -> str:
    metrics = state.get("extracted_metrics", {})
    checks = state.get("audit_checks", [])
    rationale = state.get("audit_rationale", {})
    evidence = state.get("selected_evidence_items", [])
    currency = metrics.get("currency", "USD")
    check_results = {c.get("result") for c in checks}
    if "FAIL" in check_results:
        status = "NON_COMPLIANT"
    elif "REVIEW" in check_results:
        status = "ACTION_REQUIRED"
    else:
        status = "COMPLIANT"

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

## 5. PRIMARY EVIDENCE TRAIL
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


def build_rule_application_reasoning(metrics: dict) -> str:
    return (
        f"The selected rule applies because {metrics.get('source_doc', 'the selected source')} "
        f"governs the {metrics.get('transaction_type', 'transaction')} involving "
        f"{metrics.get('origin_entity', 'the origin entity')} and "
        f"{metrics.get('destination_entity_or_type', 'the counterparty')} for "
        f"{metrics.get('payment_purpose', 'the stated payment purpose')} in "
        f"{metrics.get('jurisdiction', 'the recorded jurisdiction')}."
    )


def normalize_rationale_findings(
    findings: list[str],
    checks: list[dict],
    selected_evidence: list[dict],
) -> list[str]:
    normalized = []
    for check in checks:
        name = check.get("name", "Audit check")
        result = check.get("result")
        if result == "FAIL":
            normalized.append(
                f"{name} failed: actual value is {check.get('actual', 'N/A')}; expected {check.get('expected', 'N/A')}."
            )
        elif result == "REVIEW":
            normalized.append(
                f"{name} remains marked for reviewer confirmation based on attached evidence."
            )
    if not normalized:
        normalized.append("No deterministic compliance deficiency was identified.")
    return normalized

def extract_audit_json(state: AgentState) -> AgentState:
    """Invokes the environment factory model strictly for structured metrics extraction."""
    raw_llm = get_chat_model(temperature=0.0)
    structured_extractor = raw_llm.with_structured_output(ComplianceExtractionSchema)

    formatted_context = rank_context_blocks_for_extraction(
        state["context_blocks"],
        state["query"],
    )
    
    feedback_note = state.get("error_feedback", "")

    extraction_prompt = f"""
    You are an enterprise parameter extraction layer. 
    Your objective is to read the provided Context and Topology, isolate the metrics requested, and map them to the structural JSON keys.
    
    CRITICAL CONSTRAINT FOR 'source_doc':
    You MUST return EXACTLY ONE of these allowed framework node labels:
    - Internal Policy
    - Foreign Investment
    - RBI KYC
    - RBI Credit Risk
    - Apple SEC Filings
    - Microsoft SEC Filings

    PDF filename to node-label mapping:
    - nexus_holdings_global_inc.pdf => Internal Policy
    - foreign_Investement_rbi.pdf => Foreign Investment
    - kyc_rbi.pdf => RBI KYC
    - credit_Risk_RBI.pdf => RBI Credit Risk
    - apple-SEC.pdf => Apple SEC Filings
    - microsoft-SEC.pdf => Microsoft SEC Filings

    Do NOT return PDF filenames in source_doc. If a PDF contains the governing text, return its mapped node label.
    Choose the node label that contains the actual governing text or exact numeric ceiling. If a graph edge only cross-references another framework but an internal policy chunk contains the exact threshold language, choose Internal Policy.

    FIELD EXTRACTION RULES:
    - destination_entity_or_type must be the recipient or recipient category. It must never be a currency, amount, or jurisdiction.
    - currency must be only a currency code such as USD, INR, or EUR.
    - applicable_rules must include only rules supported by the supplied context or topology.
    - applicable_rules must be a simple list. Each object must use short string values only; use "N/A" instead of null.
    - risk_factors must appear exactly once. Each object must contain only "factor" and "source" string fields.
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
        SystemMessage(content="You parse raw numbers and strings with absolute literal text precision. You do not compute mathematical verdicts. You must return one valid structured tool call only."),
        HumanMessage(content=extraction_prompt)
    ]

    try:
        extracted_data = structured_extractor.invoke(messages)
    except Exception as error:
        retry_messages = [
            SystemMessage(content="Your previous structured tool call was invalid. Return one valid ComplianceExtractionSchema tool call only. Do not duplicate fields. Close every string."),
            HumanMessage(content=f"{extraction_prompt}\n\nPrevious tool-call error: {type(error).__name__}: {error}")
        ]
        extracted_data = structured_extractor.invoke(retry_messages)
    
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
    state["audit_checks"] = attach_evidence_to_checks(state)

    has_failed_check = any(
        check.get("result") == "FAIL"
        for check in state.get("audit_checks", [])
    )
    has_review_check = any(
        check.get("result") == "REVIEW"
        for check in state.get("audit_checks", [])
    )

    prompt = f"""
    You are a compliance audit rationale writer.

    You must NOT calculate the verdict yourself.
    You must explain the deterministic audit result using only the supplied extracted facts,
    audit checks, and the evidence_items attached to each audit check.

    USER QUERY:
    {state["query"]}

    EXTRACTED METRICS:
    {state["extracted_metrics"]}

    DETERMINISTIC AUDIT CHECKS:
    {state["audit_checks"]}

    PRIMARY EVIDENCE TRAIL:
    {selected_evidence}

    Instructions:
    - Treat deterministic audit checks as controlling. If a check result is FAIL, your explanation must not recommend approval.
    - The selected rule source is EXTRACTED METRICS.source_doc. Do not call any other rule the selected rule.
    - Explain each check using only that check's attached evidence_items.
    - Cite document names and page numbers from the evidence_items attached to the relevant check.
    - Use PRIMARY EVIDENCE TRAIL only as the overall threshold evidence trail, not as a substitute for missing check evidence.
    - Do not mention the literal strings "EXTRACTED METRICS", "PRIMARY EVIDENCE TRAIL", or "evidence_items" in the final rationale.
    - Do not claim the ceiling is missing when any attached evidence states the ceiling.
    - Deficiency findings must be short separate findings, not a long paragraph.
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
    elif has_review_check:
        recommended_action = "REQUEST_MORE_EVIDENCE"
    elif not selected_evidence:
        recommended_action = "REQUEST_MORE_EVIDENCE"

    state["audit_rationale"] = {
        "executive_summary": result.executive_summary,
        "rule_application_reasoning": build_rule_application_reasoning(
            state.get("extracted_metrics", {})
        ),
        "evidence_summary": result.evidence_summary,
        "deficiency_findings": normalize_rationale_findings(
            result.deficiency_findings,
            state.get("audit_checks", []),
            selected_evidence,
        ),
        "recommended_action": recommended_action,
    }
    state["audit_verdict"] = build_audit_verdict(state)

    return state
