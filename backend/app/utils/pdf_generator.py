"""Generate publication-ready ComplianceNexus audit PDFs with ReportLab."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


TITLE = "ComplianceNexus Transaction Audit Registry"
PAGE_SIZE = landscape(letter)
NAVY = colors.HexColor("#17324D")
BODY_TEXT = colors.HexColor("#263238")
MUTED_TEXT = colors.HexColor("#607D8B")
LIGHT_BORDER = colors.HexColor("#CFD8DC")


@dataclass(frozen=True)
class PreparedAudit:
    """Validated values in the exact display form required by the PDF."""

    query: str
    verdict: str
    verdict_label: str
    accent_color: colors.Color
    summary: str
    transaction_value: Any
    allowed_ceiling: Any
    transaction_display: str
    ceiling_display: str
    variance_display: str
    exposure_evaluation: str
    lineage: str
    source_document: str
    citations: list[str]
    citation_status: str
    selected_evidence: list[dict]
    audit_checks: list[dict]
    audit_rationale: dict


def validate_inputs(state_data: dict, output_path: str) -> Path:
    """Validate the graph state and return a writable PDF destination."""

    if not isinstance(state_data, dict):
        raise TypeError("state_data must be a dictionary")

    required_keys = {
        "query",
        "audit_verdict",
        "extracted_metrics",
        "citations",
    }
    missing_keys = required_keys - state_data.keys()
    if missing_keys:
        names = ", ".join(sorted(missing_keys))
        raise ValueError(f"state_data is missing required fields: {names}")

    if not isinstance(state_data["extracted_metrics"], dict):
        raise TypeError("state_data['extracted_metrics'] must be a dictionary")

    if not isinstance(output_path, str) or not output_path.strip():
        raise ValueError("output_path must be a non-empty string")

    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".pdf":
        raise ValueError("output_path must end with .pdf")

    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def build_styles() -> dict[str, ParagraphStyle]:
    """Create all paragraph styles once and expose them by descriptive name."""

    sample = getSampleStyleSheet()
    cell = ParagraphStyle(
        "AuditTableCell",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=BODY_TEXT,
        alignment=TA_LEFT,
    )

    return {
        "title": ParagraphStyle(
            "AuditTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=4 * mm,
        ),
        "metadata": ParagraphStyle(
            "AuditMetadata",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED_TEXT,
            alignment=TA_LEFT,
        ),
        "metadata_label": ParagraphStyle(
            "AuditMetadataLabel",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=MUTED_TEXT,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "AuditSectionHeading",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=NAVY,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "AuditBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=BODY_TEXT,
            alignment=TA_LEFT,
        ),
        "cell": cell,
        "table_header": ParagraphStyle(
            "AuditTableHeader",
            parent=cell,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "verdict": ParagraphStyle(
            "AuditVerdict",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
    }


def make_paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    """Escape dynamic content and make it wrap as a ReportLab Paragraph."""

    return Paragraph(escape(str(value)), style)


def detect_verdict(audit_verdict: Any) -> tuple[str, str, colors.Color, str]:
    """Convert the Markdown verdict report into PDF presentation values."""

    if not isinstance(audit_verdict, str) or not audit_verdict.strip():
        raise ValueError("state_data['audit_verdict'] must be a non-empty string")

    normalized = audit_verdict.upper()
    if "NON_COMPLIANT" in normalized or "NON-COMPLIANT" in normalized:
        return (
            "NON_COMPLIANT",
            "NON-COMPLIANT",
            colors.HexColor("#D32F2F"),
            "The automated evaluation detected a breach of the permitted "
            "compliance threshold.",
        )
    if "ACTION_REQUIRED" in normalized or "ACTION REQUIRED" in normalized:
        return (
            "ACTION_REQUIRED",
            "ACTION REQUIRED",
            colors.HexColor("#F57C00"),
            "The automated evaluation requires human review before a final "
            "compliance decision can be issued.",
        )
    if "COMPLIANT" in normalized:
        return (
            "COMPLIANT",
            "COMPLIANT",
            colors.HexColor("#388E3C"),
            "The automated evaluation found the transaction within the "
            "permitted compliance threshold.",
        )

    return (
        "ACTION_REQUIRED",
        "ACTION REQUIRED",
        colors.HexColor("#F57C00"),
        "No recognized automated verdict was recorded. Human review is required.",
    )


def action_required_presentation(summary: str) -> tuple[str, str, colors.Color, str]:
    """Return the safe presentation used when state data cannot support a verdict."""

    return (
        "ACTION_REQUIRED",
        "ACTION REQUIRED",
        colors.HexColor("#F57C00"),
        summary,
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalize_citations(citations: Any, source_document: Any) -> list[str]:
    """Clean, de-duplicate, and preserve the order of source citations."""

    if not isinstance(citations, list):
        raise TypeError("state_data['citations'] must be a list")

    cleaned: list[str] = []
    for citation in citations:
        if isinstance(citation, str):
            value = citation.strip()
            if value and value not in cleaned:
                cleaned.append(value)

    if (
        not cleaned
        and isinstance(source_document, str)
        and source_document.strip()
        and source_document.strip().upper() != "N/A"
    ):
        cleaned.append(source_document.strip())

    return cleaned


def prepare_audit_data(state_data: dict) -> PreparedAudit:
    """Normalize nested state without crashing on controlled graph failures."""

    verdict, label, accent, summary = detect_verdict(state_data["audit_verdict"])
    metrics = state_data["extracted_metrics"]
    transaction_value = metrics.get("transaction_value")
    allowed_ceiling = metrics.get("allowed_ceiling")
    numeric_metrics_are_valid = _is_number(transaction_value) and _is_number(
        allowed_ceiling
    )


    if verdict != "ACTION_REQUIRED" and not numeric_metrics_are_valid:
        verdict, label, accent, summary = action_required_presentation(
            "The recorded verdict could not be reconciled with valid numeric "
            "metrics. Human review is required."
        )

    if verdict == "ACTION_REQUIRED":
        transaction_display = "UNDER REVIEW"
        ceiling_display = "UNDER REVIEW"
        variance_display = "NOT CALCULATED"
        exposure_evaluation = "HUMAN REVIEW REQUIRED"
    else:
        variance = transaction_value - allowed_ceiling
        transaction_display = f"${transaction_value:,.2f} USD"
        ceiling_display = f"${allowed_ceiling:,.2f} USD"
        variance_display = f"${variance:,.2f} USD"
        exposure_evaluation = (
            "FAIL - CEILING EXCEEDED"
            if transaction_value > allowed_ceiling
            else "PASS - WITHIN CEILING"
        )

    query = state_data["query"]
    if not isinstance(query, str) or not query.strip():
        query = "No transaction query was recorded."

    lineage = metrics.get("lineage")
    lineage_display = (
        lineage.strip()
        if isinstance(lineage, str) and lineage.strip()
        else "No corporate lineage summary was recorded."
    )
    source_document = metrics.get("source_doc")
    raw_citation_status = state_data.get("citation_status")
    citation_status = (
        raw_citation_status.strip().upper()
        if isinstance(raw_citation_status, str) and raw_citation_status.strip()
        else "NOT RECORDED"
    )

    return PreparedAudit(
        query=query.strip(),
        verdict=verdict,
        verdict_label=label,
        accent_color=accent,
        summary=summary,
        transaction_value=transaction_value,
        allowed_ceiling=allowed_ceiling,
        transaction_display=transaction_display,
        ceiling_display=ceiling_display,
        variance_display=variance_display,
        exposure_evaluation=exposure_evaluation,
        lineage=lineage_display,
        source_document=str(source_document or "N/A"),
        citations=normalize_citations(state_data["citations"], source_document),
        citation_status=citation_status,
        selected_evidence=state_data.get("selected_evidence_items", []),
        audit_checks=state_data.get("audit_checks", []),
        audit_rationale=state_data.get("audit_rationale", {}),
    )


def standard_table_style(extra_commands: list[tuple] | None = None) -> TableStyle:
    """Return shared borders, alignment, and padding for audit tables."""

    commands: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B0BEC5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#78909C")),
    ]
    commands.extend(extra_commands or [])
    return TableStyle(commands)


def build_header(
    doc: SimpleDocTemplate,
    styles: dict[str, ParagraphStyle],
    generated_at: datetime,
    record_id: str,
) -> list[Any]:
    """Build the title and timestamp metadata block."""

    metadata_data = [
        [
            make_paragraph("Generated at", styles["metadata_label"]),
            make_paragraph(
                generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
                styles["metadata"],
            ),
        ],
        [
            make_paragraph("Audit record ID", styles["metadata_label"]),
            make_paragraph(record_id, styles["metadata"]),
        ],
    ]
    metadata_table = Table(
        metadata_data,
        colWidths=[30 * mm, doc.width - (30 * mm)],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, LIGHT_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )
    return [
        Paragraph(TITLE, styles["title"]),
        metadata_table,
        Spacer(1, 5 * mm),
    ]


def build_executive_summary(
    doc: SimpleDocTemplate,
    audit: PreparedAudit,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Build the colored official-verdict section."""

    verdict_box = Table(
        [
            [make_paragraph(audit.verdict_label, styles["verdict"])],
            [make_paragraph(audit.summary, styles["body"])],
        ],
        colWidths=[doc.width],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), audit.accent_color),
                ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#F7F9FA")),
                ("BOX", (0, 0), (-1, -1), 1.2, audit.accent_color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        ),
    )
    return [
        KeepTogether(
            [
                Paragraph(
                    "EXECUTIVE SUMMARY - OFFICIAL VERDICT",
                    styles["section"],
                ),
                verdict_box,
            ]
        ),
        Spacer(1, 4 * mm),
    ]


def build_audit_scope(
    audit: PreparedAudit, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    return [
        Paragraph("AUDIT SCOPE", styles["section"]),
        make_paragraph(audit.query, styles["body"]),
        Spacer(1, 3 * mm),
    ]


def build_evaluation_matrix(
    doc: SimpleDocTemplate,
    audit: PreparedAudit,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Build the wrapping, five-column compliance matrix."""

    header = styles["table_header"]
    cell = styles["cell"]
    data = [
        [
            make_paragraph("Compliance Dimension", header),
            make_paragraph("Threshold / Rule", header),
            make_paragraph("Actual Query Metric", header),
            make_paragraph("Variance", header),
            make_paragraph("Evaluation", header),
        ],
        [
            make_paragraph("Transactional Exposure", cell),
            make_paragraph(audit.ceiling_display, cell),
            make_paragraph(audit.transaction_display, cell),
            make_paragraph(audit.variance_display, cell),
            make_paragraph(audit.exposure_evaluation, cell),
        ],
        [
            make_paragraph("Corporate Lineage", cell),
            make_paragraph("Ownership, jurisdiction, and regulatory overlays", cell),
            make_paragraph(audit.lineage, cell),
            make_paragraph("Qualitative", cell),
            make_paragraph("Lineage evidence reviewed", cell),
        ],
        [
            make_paragraph("Citation Integrity", cell),
            make_paragraph(
                "Every governing metric must have a traceable source", cell
            ),
            make_paragraph(f"{len(audit.citations)} source citation(s)", cell),
            make_paragraph("N/A", cell),
            make_paragraph(audit.citation_status, cell),
        ],
    ]
    table = Table(
        data,
        
        colWidths=[doc.width * part for part in (0.18, 0.19, 0.33, 0.10, 0.20)],
        repeatRows=1,
        style=standard_table_style(
            [
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F3F6F8")],
                ),
                ("BOX", (4, 1), (4, 1), 1.2, audit.accent_color),
            ]
        ),
    )
    return [
        Paragraph(
            "MULTI-CRITERIA COMPLIANCE EVALUATION MATRIX", styles["section"]
        ),
        table,
        Spacer(1, 4 * mm),
    ]


def build_audit_checks_section(
    doc: SimpleDocTemplate,
    audit: PreparedAudit,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    if not audit.audit_checks:
        return []

    header = styles["table_header"]
    cell = styles["cell"]
    data = [[
        make_paragraph("Check", header),
        make_paragraph("Expected", header),
        make_paragraph("Actual", header),
        make_paragraph("Result", header),
        make_paragraph("Attached Evidence", header),
    ]]
    for check in audit.audit_checks[:6]:
        evidence = check.get("evidence_items") or []
        evidence_display = ", ".join(
            f"{item.get('source_document', 'Unknown')} p.{item.get('page_number', 'N/A')}"
            for item in evidence[:2]
        ) or "No evidence attached"
        data.append([
            make_paragraph(check.get("name", "Audit Check"), cell),
            make_paragraph(check.get("expected", "N/A"), cell),
            make_paragraph(check.get("actual", "N/A"), cell),
            make_paragraph(check.get("result", "REVIEW"), cell),
            make_paragraph(evidence_display, cell),
        ])

    table = Table(
        data,
        colWidths=[doc.width * part for part in (0.18, 0.28, 0.26, 0.10, 0.18)],
        repeatRows=1,
        style=standard_table_style(),
    )
    return [
        Paragraph("DETERMINISTIC AUDIT CHECKS", styles["section"]),
        table,
        Spacer(1, 4 * mm),
    ]


def build_selected_evidence_section(
    doc: SimpleDocTemplate,
    audit: PreparedAudit,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    if not audit.selected_evidence:
        return []

    header = styles["table_header"]
    cell = styles["cell"]
    data = [[
        make_paragraph("Source", header),
        make_paragraph("Page", header),
        make_paragraph("Evidence Snippet", header),
        make_paragraph("Selection Basis", header),
    ]]
    for item in audit.selected_evidence[:6]:
        snippet = " ".join(str(item.get("snippet", "")).split())
        criteria = ", ".join(item.get("selection_criteria", []))
        data.append([
            make_paragraph(item.get("source_document", "Unknown"), cell),
            make_paragraph(item.get("page_number", "Unknown"), cell),
            make_paragraph(snippet[:500], cell),
            make_paragraph(criteria or "retrieved_context", cell),
        ])

    table = Table(
        data,
        colWidths=[doc.width * part for part in (0.20, 0.08, 0.52, 0.20)],
        repeatRows=1,
        style=standard_table_style(),
    )
    return [
        Paragraph("PRIMARY EVIDENCE TRAIL", styles["section"]),
        table,
        Spacer(1, 4 * mm),
    ]


def build_rationale_section(audit: PreparedAudit, styles: dict[str, ParagraphStyle]) -> list[Any]:
    if not audit.audit_rationale:
        return []

    rationale = audit.audit_rationale
    findings = rationale.get("deficiency_findings") or []
    flowables = [
        Paragraph("AUDIT RATIONALE AND ACTION", styles["section"]),
        make_paragraph(rationale.get("rule_application_reasoning", "No rationale recorded."), styles["body"]),
        Spacer(1, 2 * mm),
        Paragraph("Deficiency findings", styles["metadata_label"]),
    ]
    if findings:
        for finding in findings:
            flowables.append(make_paragraph(f"- {finding}", styles["body"]))
            flowables.append(Spacer(1, 1 * mm))
    else:
        flowables.append(make_paragraph("- No deficiency findings returned.", styles["body"]))
    flowables.extend([
        Spacer(1, 2 * mm),
        make_paragraph(f"Recommended action: {rationale.get('recommended_action', 'HUMAN_REVIEW')}", styles["body"]),
        Spacer(1, 4 * mm),
    ])
    return flowables


def build_citation_appendix(
    doc: SimpleDocTemplate,
    audit: PreparedAudit,
    fingerprint: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Keep a page-sized appendix and fingerprint together when possible."""

    header = styles["table_header"]
    cell = styles["cell"]
    data = [
        [
            make_paragraph("No.", header),
            make_paragraph("Document and Page Citation", header),
        ]
    ]
    if audit.citations:
        data.extend(
            [make_paragraph(index, cell), make_paragraph(citation, cell)]
            for index, citation in enumerate(audit.citations, start=1)
        )
    else:
        data.append(
            [
                make_paragraph("-", cell),
                make_paragraph(
                    "No verified source citation was recorded. Human review is required.",
                    cell,
                ),
            ]
        )

    table = Table(
        data,
        colWidths=[doc.width * 0.08, doc.width * 0.92],
        repeatRows=1,
        style=standard_table_style(
            [("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#ECEFF1"))]
        ),
    )
    appendix_flowables = [
        Paragraph("TRACEABLE APPENDIX - SOURCE DOCUMENTS", styles["section"]),
        table,
        *build_fingerprint_block(fingerprint, styles),
    ]
    measured_height = sum(
        flowable.wrap(doc.width, doc.height)[1] for flowable in appendix_flowables
    )
    
    required_height = min(measured_height, doc.height)
    return [
        CondPageBreak(required_height),
        KeepTogether(appendix_flowables, maxHeight=doc.height),
    ]


def calculate_fingerprint(audit: PreparedAudit, generated_at: datetime) -> str:
    """Calculate a stable SHA-256 fingerprint for the displayed audit data."""

    payload = {
        "generated_at": generated_at.isoformat(),
        "query": audit.query,
        "verdict": audit.verdict,
        "transaction_value": audit.transaction_value,
        "allowed_ceiling": audit.allowed_ceiling,
        "lineage": audit.lineage,
        "citations": audit.citations,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_fingerprint_block(
    fingerprint: str, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """Add a readable, wrapping fingerprint to the end of the record."""

    grouped = " ".join(
        fingerprint[index : index + 16] for index in range(0, len(fingerprint), 16)
    )
    return [
        Spacer(1, 5 * mm),
        Paragraph(
            f"<b>SHA-256 Record Fingerprint:</b><br/>{grouped}",
            styles["metadata"],
        ),
    ]


def make_page_footer(record_id: str) -> Callable[[Any, Any], None]:
    """Create a ReportLab page callback bound to this audit record ID."""

    def draw_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED_TEXT)
        canvas.drawString(
            15 * mm,
            8 * mm,
            f"ComplianceNexus - System Generated Audit Record {record_id}",
        )
        canvas.drawRightString(
            PAGE_SIZE[0] - (15 * mm),
            8 * mm,
            f"Page {document.page}",
        )
        canvas.restoreState()

    return draw_footer


def generate_compliance_pdf(state_data: dict, output_path: str) -> str:
    """Generate one compliance PDF and return its absolute filesystem path."""

    destination = validate_inputs(state_data, output_path)
    audit = prepare_audit_data(state_data)
    styles = build_styles()
    generated_at = datetime.now().astimezone()
    fingerprint = calculate_fingerprint(audit, generated_at)
    record_id = fingerprint[:12].upper()

    doc = SimpleDocTemplate(
        str(destination),
        pagesize=PAGE_SIZE,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=TITLE,
        author="ComplianceNexus",
        subject="Transaction compliance audit record",
    )

    story: list[Any] = []
    story.extend(build_header(doc, styles, generated_at, record_id))
    story.extend(build_executive_summary(doc, audit, styles))
    story.extend(build_audit_scope(audit, styles))
    story.extend(build_evaluation_matrix(doc, audit, styles))
    story.extend(build_audit_checks_section(doc, audit, styles))
    story.extend(build_selected_evidence_section(doc, audit, styles))
    story.extend(build_rationale_section(audit, styles))
    story.extend(build_citation_appendix(doc, audit, fingerprint, styles))

    footer = make_page_footer(record_id)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return str(destination.resolve())


def sample_state() -> dict:
    """Return a realistic state for local PDF generation and visual testing."""

    return {
        "query": (
            "Verify whether a $1,800,000 USD technology software licensing "
            "transaction initiated by Nexus India violates internal cross-border limits."
        ),
        "audit_verdict": (
            "## 1. OFFICIAL COMPLIANCE AUDIT VERDICT\n"
            "**NON_COMPLIANT**\n\n"
            "The transaction exceeds the approved corporate ceiling."
        ),
        "extracted_metrics": {
            "transaction_value": 1_800_000.00,
            "allowed_ceiling": 1_500_000.00,
            "lineage": (
                "Nexus Holdings owns Nexus India. The subsidiary is governed by "
                "Indian regulatory overlays and the parent company's cross-border policy."
            ),
            "source_doc": "nexus_holdings_global_inc.pdf",
        },
        "citations": [
            "nexus_holdings_global_inc.pdf (Page 3)",
            "foreign_Investement_rbi.pdf (Page 12)",
            "kyc_rbi.pdf (Page 8)",
        ],
        "citation_status": "complete",
    }


if __name__ == "__main__":
    sample_output = "output/pdf/sample_compliance_audit.pdf"
    generated_file = generate_compliance_pdf(sample_state(), sample_output)
    print(f"Sample compliance PDF generated: {generated_file}")
