from pydantic import BaseModel, Field
from typing import Literal
from typing import TypedDict, List, Dict, Any

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
        description="Select EXACTLY ONE allowed framework node label. Do not return PDF filenames."
    )

    transaction_type: str = Field(
        description="Classify the transaction purpose, e.g. software licensing remittance, royalty payment, dividend remittance, cloud service payment, equity acquisition."
    )

    origin_entity: str = Field(
        description="The entity initiating the payment, e.g. Nexus India. Must not be a currency."
    )

    destination_entity_or_type: str = Field(
        description="The recipient or recipient category, e.g. overseas vendor, AWS US East, overseas parent entity. Must not be currency, amount, or jurisdiction."
    )

    jurisdiction: str = Field(
        description="The relevant legal/geographic jurisdiction, e.g. India outbound remittance."
    )

    payment_purpose: str = Field(
        description="Business purpose of payment, e.g. technology software licensing fees."
    )

    currency: str = Field(
        description="Currency code only, e.g. USD, INR, EUR."
    )

    applicable_rules: list[dict] = Field(
        description=(
            "Rules that apply to this transaction. Each item should include rule_name, "
            "source_doc, threshold if any, condition, and why_applicable. Use only rules "
            "supported by the supplied context or topology."
        )
    )

    risk_factors: list[dict] = Field(
        description=(
            "Transaction-specific risk factors supported by the query, context, or topology. "
            "Each item should include factor and source/reason where possible."
        )
    )

    primary_evidence_summary: str = Field(
        description=(
            "A concise summary of the exact evidence establishing the governing rule or "
            "threshold. Prefer the document text containing the numeric ceiling over a graph "
            "cross-reference that merely points to another framework."
        )
    )

class AuditRationaleSchema(BaseModel):
    executive_summary: str = Field(
        description="Short business-readable explanation of the final compliance outcome."
    )
    rule_application_reasoning: str = Field(
        description="Explain why the selected rule applies to this transaction."
    )
    evidence_summary: str = Field(
        description="Summarize the strongest evidence used, referencing document names and pages."
    )
    deficiency_findings: list[str] = Field(
        description="Specific compliance deficiencies or reasons no deficiency exists."
    )
    recommended_action: Literal[
        "APPROVE",
        "BLOCK_REMITTANCE",
        "ESCALATE_TO_L2",
        "REQUEST_MORE_EVIDENCE",
        "HUMAN_REVIEW"
    ]

class AgentState(TypedDict):
    query: str
    retrieved_child_ids: List[str]
    context_blocks: list
    graph_entities: str

    extracted_metrics: Dict[str, Any]
    evidence_items: List[Dict[str, Any]]
    selected_evidence_items: List[Dict[str, Any]]
    audit_checks: List[Dict[str, Any]]
    audit_rationale: Dict[str, Any]

    audit_verdict: str
    citations: List[str]
    retry_count: int
    citation_status: str
    error_feedback: str

   
