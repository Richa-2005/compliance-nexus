import datetime
import json
import pickle
from typing import  Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.audit_graph import audit_graph
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.models import AuditAssignment, AuditRecord, Roles, Users
from app.api.v1.websockets import manager
from app.utils.pdf_generator import generate_compliance_pdf

audits_router = APIRouter(prefix="/audits")

OUTPUT_DIR = settings.DB_DIR / "certificates"
GRAPH_PATH = settings.DB_DIR / "knowledge_graph.pkl"

DOC_TO_GRAPH_NODE = {
    "apple-SEC.pdf": "Apple SEC Filings",
    "credit_Risk_RBI.pdf": "RBI Credit Risk",
    "foreign_Investement_rbi.pdf": "Foreign Investment",
    "kyc_rbi.pdf": "RBI KYC",
    "microsoft-SEC.pdf": "Microsoft SEC Filings",
    "nexus_holdings_global_inc.pdf": "Internal Policy",
}

GRAPH_NODE_TO_DOC = {node: doc for doc, node in DOC_TO_GRAPH_NODE.items()}


def serialize_user(user: Users) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    }


def compute_status(extracted: dict, verdict: str, audit_checks: list[dict] | None = None) -> str:
    check_results = {check.get("result") for check in (audit_checks or [])}
    if "FAIL" in check_results:
        return "NON_COMPLIANT"
    if "REVIEW" in check_results:
        return "ACTION_REQUIRED"

    val = float(extracted.get("transaction_value", 0.0))
    ceiling = float(extracted.get("allowed_ceiling", 0.0))
    source_doc = str(extracted.get("source_doc", ""))

    if source_doc.upper() == "N/A" or not source_doc:
        return "ACTION_REQUIRED"
    if ceiling > 0 and val > ceiling:
        return "NON_COMPLIANT"
    return "COMPLIANT"


def node_group(node: str, audit: AuditRecord | None = None) -> str:
    if audit and node == audit.transaction_id:
        return "TRANSACTION"
    if node in DOC_TO_GRAPH_NODE.values():
        return "POLICY"
    if "breach" in node.lower() or "warning" in node.lower():
        return "WARNING"
    return "CORPORATE_ENTITY"


def parse_json_field(value: str | None, fallback):
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def serialize_audit_record(rec: AuditRecord, include_user: bool = False) -> dict:
    data = {
        "id": rec.id,
        "transaction_id": rec.transaction_id,
        "query": rec.query,
        "transaction_value": rec.transaction_value,
        "allowed_ceiling": rec.allowed_ceiling,
        "status": rec.status,
        "source_doc": rec.source_doc,
        "audit_verdict_markdown": rec.audit_verdict_markdown,
        "citations": parse_json_field(rec.citations_json, []),
        "evidence_items": parse_json_field(rec.evidence_json, []),
        "selected_evidence_items": parse_json_field(rec.selected_evidence_json, []),
        "audit_checks": parse_json_field(rec.audit_checks_json, []),
        "audit_rationale": parse_json_field(rec.audit_rationale_json, {}),
        "pdf_path": rec.pdf_path,
        "created_at": rec.timestamp.isoformat()
        if rec.timestamp
        else "",
    }
    if include_user:
        data["user_id"] = rec.user_id
    return data


def citation_nodes(citations_json: str | None) -> set[str]:
    try:
        citations = json.loads(citations_json or "[]")
    except Exception:
        citations = []

    nodes = set()
    for citation in citations:
        citation_text = citation if isinstance(citation, str) else json.dumps(citation)
        for doc, node in DOC_TO_GRAPH_NODE.items():
            if doc in citation_text:
                nodes.add(node)
    return nodes


def uploaded_evidence_nodes(audit: AuditRecord) -> set[str]:
    evidence_items = parse_json_field(audit.selected_evidence_json, [])
    evidence_items.extend(parse_json_field(audit.evidence_json, []))
    nodes = set()
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        source_document = item.get("source_document")
        if source_document and source_document not in DOC_TO_GRAPH_NODE:
            nodes.add(str(source_document))
    return nodes


def transaction_focus_nodes(G, audit: AuditRecord) -> set[str]:
    focus = {"Nexus Holdings", "Nexus India"}
    if audit.source_doc in GRAPH_NODE_TO_DOC:
        focus.add(audit.source_doc)
    focus.update(citation_nodes(audit.citations_json))

    path_nodes = set(focus)
    for source in ("Nexus Holdings", "Nexus India"):
        for target in focus:
            if source == target or source not in G or target not in G:
                continue
            try:
                path_nodes.update(nx.shortest_path(G, source=source, target=target))
            except Exception:
                continue

    return path_nodes


@audits_router.post("/evaluate")
async def evaluate_transaction(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    query_text = payload.get("query")
    if not query_text:
        raise HTTPException(
            status_code=400, detail="Query string field is required."
        )

    
    tx_timestamp = int(datetime.datetime.utcnow().timestamp())
    transaction_id = f"TX_{tx_timestamp}"

    try:
        graph_output = audit_graph.invoke({
            "query": query_text,
            "use_seeded_sources": payload.get("use_seeded_sources", True) is not False,
            "include_ingested_sources": bool(payload.get("include_ingested_sources", False)),
            "selected_document_ids": payload.get("selected_document_ids") or [],
        })
    except Exception as e:
        await manager.broadcast(
            {
                "event": "AUDIT_EVALUATION_FAILED",
                "query": query_text,
            }
        )
        raise HTTPException(
            status_code=502,
            detail=f"Audit evaluation failed: {str(e)}",
        )

    extracted = graph_output.get("extracted_metrics", {})
    status_verdict = compute_status(
        extracted,
        graph_output.get("audit_verdict", ""),
        graph_output.get("audit_checks", []),
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_filename = f"{transaction_id}.pdf"
    pdf_file_path = OUTPUT_DIR / pdf_filename

    generate_compliance_pdf(graph_output, str(pdf_file_path))

    citations_list = graph_output.get("citations", [])
    evidence_items = graph_output.get("evidence_items", [])
    selected_evidence_items = graph_output.get("selected_evidence_items", [])
    audit_checks = graph_output.get("audit_checks", [])
    audit_rationale = graph_output.get("audit_rationale", {})

    new_audit = AuditRecord(
        transaction_id=transaction_id,
        user_id=current_user.id,
        query=query_text,
        transaction_value=float(extracted.get("transaction_value", 0.0)),
        allowed_ceiling=float(extracted.get("allowed_ceiling", 0.0)),
        source_doc=str(extracted.get("source_doc", "N/A")),
        status=status_verdict,
        audit_verdict_markdown=graph_output.get("audit_verdict", ""),
        citations_json=json.dumps(citations_list),
        evidence_json=json.dumps(evidence_items),
        selected_evidence_json=json.dumps(selected_evidence_items),
        audit_checks_json=json.dumps(audit_checks),
        audit_rationale_json=json.dumps(audit_rationale),
        pdf_path=f"certificates/{pdf_filename}",
    )

    try:
        db.add(new_audit)
        db.commit()
        db.refresh(new_audit)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Database record save failure: {str(e)}"
        )

    await manager.broadcast(
        {
            "event": "AUDIT_EVALUATION_COMPLETE",
            "transaction_id": new_audit.transaction_id,
            "status": new_audit.status,
            "source_doc": new_audit.source_doc,
        }
    )

    return serialize_audit_record(new_audit)


@audits_router.get("/history")
def get_history(
    limit: Optional[int] = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    stmt = (
        select(AuditRecord)
        .where(AuditRecord.user_id == current_user.id)
        .order_by(AuditRecord.timestamp.desc())
        .limit(limit)
    )
    records = db.scalars(stmt).all()

    response_data = []
    for rec in records:
        response_data.append(serialize_audit_record(rec, include_user=True))

    return response_data


@audits_router.get("/analysts")
def get_analysts(
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if current_user.role != Roles.L2_RISK_OFFICER:
        raise HTTPException(status_code=403, detail="Only L2 risk officers can list analysts.")

    analysts = db.scalars(
        select(Users)
        .where(Users.role == Roles.L1_ANALYST)
        .where(Users.is_active == True)
        .order_by(Users.full_name.asc())
    ).all()
    return [serialize_user(user) for user in analysts]


@audits_router.post("/{transaction_id}/assignments")
def create_assignment(
    transaction_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if current_user.role != Roles.L2_RISK_OFFICER:
        raise HTTPException(status_code=403, detail="Only L2 risk officers can assign audit actions.")

    audit = db.scalar(select(AuditRecord).where(AuditRecord.transaction_id == transaction_id))
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit record '{transaction_id}' not found.")

    assignee_email = payload.get("assignee_email", "analyst@compliancenexus.com")
    assignee = db.scalar(select(Users).where(Users.email == assignee_email))
    if not assignee:
        raise HTTPException(status_code=404, detail=f"Assignee '{assignee_email}' not found.")

    action_type = str(payload.get("action_type") or "REQUEST_EVIDENCE").upper()
    note = str(payload.get("note") or "L2 review requested additional analyst action.")

    assignment = AuditAssignment(
        audit_record_id=audit.id,
        transaction_id=audit.transaction_id,
        assigned_by_user_id=current_user.id,
        assigned_to_user_id=assignee.id,
        action_type=action_type,
        note=note,
        status="OPEN",
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return serialize_assignment(assignment, audit)


@audits_router.get("/assignments/inbox")
def get_assignment_inbox(
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    stmt = (
        select(AuditAssignment, AuditRecord)
        .join(AuditRecord, AuditRecord.id == AuditAssignment.audit_record_id)
        .where(AuditAssignment.assigned_to_user_id == current_user.id)
    )
    if not include_resolved:
        stmt = stmt.where(AuditAssignment.status == "OPEN")
    stmt = stmt.order_by(AuditAssignment.created_at.desc())
    rows = db.execute(stmt).all()
    return [serialize_assignment(assignment, audit) for assignment, audit in rows]


@audits_router.get("/assignments/outbox")
def get_assignment_outbox(
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    if current_user.role != Roles.L2_RISK_OFFICER:
        raise HTTPException(status_code=403, detail="Only L2 risk officers can view follow-up history.")

    stmt = (
        select(AuditAssignment, AuditRecord)
        .join(AuditRecord, AuditRecord.id == AuditAssignment.audit_record_id)
        .where(AuditAssignment.assigned_by_user_id == current_user.id)
        .order_by(AuditAssignment.created_at.desc())
    )
    rows = db.execute(stmt).all()
    return [serialize_assignment(assignment, audit) for assignment, audit in rows]


@audits_router.patch("/assignments/{assignment_id}")
def update_assignment(
    assignment_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    assignment = db.scalar(select(AuditAssignment).where(AuditAssignment.id == assignment_id))
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    next_status = str(payload.get("status") or "RESOLVED").upper()
    is_assignee = assignment.assigned_to_user_id == current_user.id
    is_assigning_officer = (
        assignment.assigned_by_user_id == current_user.id
        and current_user.role == Roles.L2_RISK_OFFICER
    )
    if is_assignee and next_status != "RESOLVED":
        raise HTTPException(status_code=403, detail="Analysts can only resolve assigned follow-ups.")
    if is_assigning_officer and next_status != "CLOSED":
        raise HTTPException(status_code=403, detail="L2 officers can only close returned follow-ups.")
    if not is_assignee and not is_assigning_officer:
        raise HTTPException(status_code=403, detail="Assignment is not assigned to or created by this user.")

    assignment.status = next_status
    if "resolution_note" in payload:
        assignment.resolution_note = str(payload.get("resolution_note") or "")
    if next_status in {"RESOLVED", "CLOSED"}:
        assignment.resolved_at = datetime.datetime.utcnow()

    audit = db.scalar(select(AuditRecord).where(AuditRecord.id == assignment.audit_record_id))
    db.commit()
    db.refresh(assignment)
    return serialize_assignment(assignment, audit)


@audits_router.get("/topology/{transaction_id}")
def get_topology(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """Return the evidence topology used by one audit transaction."""
    audit = db.scalar(select(AuditRecord).where(AuditRecord.transaction_id == transaction_id))
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit record '{transaction_id}' not found.")

    if not GRAPH_PATH.exists():
        return {
            "nodes": [
                {"id": audit.transaction_id, "group": "TRANSACTION"},
                {"id": "Nexus India", "group": "CORPORATE_ENTITY"},
                {"id": audit.source_doc or "Unresolved Policy", "group": "POLICY"},
            ],
            "edges": [
                {
                    "source": audit.transaction_id,
                    "target": "Nexus India",
                    "label": "INITIATED_BY",
                },
                {
                    "source": "Nexus India",
                    "target": audit.source_doc or "Unresolved Policy",
                    "label": "GOVERNED_BY",
                },
            ],
        }

    try:
        with open(GRAPH_PATH, "rb") as f:
            G = pickle.load(f)

        focus_nodes = transaction_focus_nodes(G, audit)
        uploaded_nodes = uploaded_evidence_nodes(audit)
        if audit.source_doc and audit.source_doc not in G:
            focus_nodes.add(audit.source_doc)

        nodes = [{"id": audit.transaction_id, "group": "TRANSACTION"}]
        nodes.extend(
            {"id": str(n), "group": node_group(str(n), audit)}
            for n in G.nodes()
            if n in focus_nodes
        )
        nodes.extend(
            {"id": node, "group": "UPLOADED_SOURCE"}
            for node in sorted(uploaded_nodes)
        )

        edges = []
        for u, v, data in G.edges(data=True):
            if u not in focus_nodes or v not in focus_nodes:
                continue
            relation_label = data.get("relation", "CONNECTED_TO")
            edges.append(
                {"source": str(u), "target": str(v), "label": relation_label}
            )

        if "Nexus India" in focus_nodes:
            edges.append(
                {
                    "source": audit.transaction_id,
                    "target": "Nexus India",
                    "label": "INITIATED_BY",
                }
            )
        if audit.source_doc and audit.source_doc in focus_nodes:
            edges.append(
                {
                    "source": audit.transaction_id,
                    "target": audit.source_doc,
                    "label": audit.status or "EVALUATED_AGAINST",
                }
            )
        for uploaded_node in uploaded_nodes:
            edges.append(
                {
                    "source": "Nexus India" if "Nexus India" in focus_nodes else audit.transaction_id,
                    "target": uploaded_node,
                    "label": "USES_UPLOADED_EVIDENCE",
                }
            )

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse NetworkX graph: {str(e)}"
        )


@audits_router.get("/{transaction_id}/pdf")
def download_pdf(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """Streams ReportLab generated PDF compliance certificate."""
    stmt = select(AuditRecord).where(
        AuditRecord.transaction_id == transaction_id
    )
    rec = db.scalar(stmt)

    if not rec or not rec.pdf_path:
        raise HTTPException(
            status_code=404,
            detail=f"Audit record '{transaction_id}' not found.",
        )

    file_path = settings.DB_DIR / rec.pdf_path
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF certificate file missing from disk: {rec.pdf_path}",
        )

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=f"Compliance_Certificate_{transaction_id}.pdf",
    )


def serialize_assignment(assignment: AuditAssignment, audit: AuditRecord | None) -> dict:
    return {
        "id": assignment.id,
        "transaction_id": assignment.transaction_id,
        "audit_record_id": assignment.audit_record_id,
        "assigned_by_user_id": assignment.assigned_by_user_id,
        "assigned_to_user_id": assignment.assigned_to_user_id,
        "action_type": assignment.action_type,
        "note": assignment.note,
        "resolution_note": assignment.resolution_note or "",
        "status": assignment.status,
        "created_at": assignment.created_at.isoformat() if assignment.created_at else "",
        "resolved_at": assignment.resolved_at.isoformat() if assignment.resolved_at else "",
        "audit": {
            "id": audit.id,
            "transaction_id": audit.transaction_id,
            "transaction_value": audit.transaction_value,
            "allowed_ceiling": audit.allowed_ceiling,
            "status": audit.status,
            "source_doc": audit.source_doc,
            "audit_verdict_markdown": audit.audit_verdict_markdown,
            "citations": audit.citations,
            "evidence_items": audit.evidence,
            "selected_evidence_items": audit.selected_evidence,
            "audit_checks": audit.audit_checks,
            "audit_rationale": audit.audit_rationale,
            "created_at": audit.timestamp.isoformat() if audit.timestamp else "",
        }
        if audit
        else None,
    }
