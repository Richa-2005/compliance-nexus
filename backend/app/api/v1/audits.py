import datetime
import json
import pickle
from typing import  Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.audit_graph import audit_graph
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.models import AuditAssignment, AuditRecord, Roles, Users
from app.utils.pdf_generator import generate_compliance_pdf

audits_router = APIRouter(prefix="/audits")

OUTPUT_DIR = settings.DB_DIR / "certificates"
GRAPH_PATH = settings.DB_DIR / "knowledge_graph.pkl"


def compute_status(extracted: dict, verdict: str) -> str:
    """Calculates status based on ceiling and graph outputs."""
    val = float(extracted.get("transaction_value", 0.0))
    ceiling = float(extracted.get("allowed_ceiling", 0.0))
    source_doc = str(extracted.get("source_doc", ""))

    if source_doc.upper() == "N/A" or not source_doc:
        return "ACTION_REQUIRED"
    if ceiling > 0 and val > ceiling:
        return "NON_COMPLIANT"
    return "COMPLIANT"


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

    graph_output = audit_graph.invoke({"query": query_text})

    extracted = graph_output.get("extracted_metrics", {})
    status_verdict = compute_status(
        extracted, graph_output.get("audit_verdict", "")
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_filename = f"{transaction_id}.pdf"
    pdf_file_path = OUTPUT_DIR / pdf_filename

    generate_compliance_pdf(graph_output, str(pdf_file_path))

    citations_list = graph_output.get("citations", [])

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

    return {
        "id": new_audit.id,
        "transaction_id": new_audit.transaction_id,
        "query": new_audit.query,
        "transaction_value": new_audit.transaction_value,
        "allowed_ceiling": new_audit.allowed_ceiling,
        "status": new_audit.status,
        "source_doc": new_audit.source_doc,
        "audit_verdict_markdown": new_audit.audit_verdict_markdown,
        "citations": citations_list,
        "pdf_path": new_audit.pdf_path,
        "created_at": new_audit.timestamp.isoformat()
        if new_audit.timestamp
        else "",
    }


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
        try:
            parsed_citations = json.loads(rec.citations_json or "[]")
        except Exception:
            parsed_citations = []

        response_data.append(
            {
                "id": rec.id,
                "transaction_id": rec.transaction_id,
                "user_id": rec.user_id,
                "query": rec.query,
                "transaction_value": rec.transaction_value,
                "allowed_ceiling": rec.allowed_ceiling,
                "status": rec.status,
                "source_doc": rec.source_doc,
                "audit_verdict_markdown": rec.audit_verdict_markdown,
                "citations": parsed_citations,
                "pdf_path": rec.pdf_path,
                "created_at": rec.timestamp.isoformat()
                if rec.timestamp
                else "",
            }
        )

    return response_data


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
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    stmt = (
        select(AuditAssignment, AuditRecord)
        .join(AuditRecord, AuditRecord.id == AuditAssignment.audit_record_id)
        .where(AuditAssignment.assigned_to_user_id == current_user.id)
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
    if assignment.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Assignment is not assigned to this user.")

    next_status = str(payload.get("status") or "RESOLVED").upper()
    assignment.status = next_status
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
    """Parses NetworkX graph topology binary for interactive React D3 UI visualizer."""
    if not GRAPH_PATH.exists():
        return {
            "nodes": [
                {"id": "Nexus Holdings", "group": "PARENT_ENTITY"},
                {"id": "Nexus India", "group": "OPERATING_SUB"},
                {"id": "RBI Regulatory Ceiling", "group": "POLICY"},
            ],
            "edges": [
                {
                    "source": "Nexus Holdings",
                    "target": "Nexus India",
                    "label": "OWNERSHIP_100",
                },
                {
                    "source": "Nexus India",
                    "target": "RBI Regulatory Ceiling",
                    "label": "GOVERNED_BY",
                },
            ],
        }

    try:
        with open(GRAPH_PATH, "rb") as f:
            G = pickle.load(f)

        nodes = []
        for n in G.nodes():
            n_str = str(n)
            node_type = (
                "POLICY" if n_str.endswith(".pdf") else "CORPORATE_ENTITY"
            )
            nodes.append({"id": n_str, "group": node_type})

        edges = []
        for u, v, data in G.edges(data=True):
            relation_label = data.get("relation", "CONNECTED_TO")
            edges.append(
                {"source": str(u), "target": str(v), "label": relation_label}
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
        "action_type": assignment.action_type,
        "note": assignment.note,
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
            "created_at": audit.timestamp.isoformat() if audit.timestamp else "",
        }
        if audit
        else None,
    }
