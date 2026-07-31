import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.models import AuditRecord, Roles, Users

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ComplianceNexus.Seed")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Utility to securely hash plain text passwords."""
    return pwd_context.hash(password)


def resolve_status(record: Dict[str, Any]) -> str:
    """Helper to dynamically resolve status across JSON schema variations."""
    if "state" in record and record["state"]:
        return str(record["state"])
    if "status" in record and record["status"]:
        return str(record["status"])
    if "COMPLIANT" in record:
        return "COMPLIANT"
    return "COMPLIANT"


def resolve_citations_json(citations_raw: Any) -> str:
    if isinstance(citations_raw, str):
        
        return citations_raw
    if isinstance(citations_raw, list):
        return json.dumps(citations_raw)
    return "[]"


def resolve_json(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return fallback
    return json.dumps(value)


def ensure_audit_record_columns(db: Session) -> None:
    existing = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(audit_records)")).fetchall()
    }
    columns = {
        "evidence_json": "'[]'",
        "selected_evidence_json": "'[]'",
        "audit_checks_json": "'[]'",
        "audit_rationale_json": "'{}'",
    }
    for name, default in columns.items():
        if name not in existing:
            db.execute(text(f"ALTER TABLE audit_records ADD COLUMN {name} TEXT DEFAULT {default}"))
    db.commit()


def ensure_assignment_columns(db: Session) -> None:
    existing = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(audit_assignments)")).fetchall()
    }
    if "resolution_note" not in existing:
        db.execute(text("ALTER TABLE audit_assignments ADD COLUMN resolution_note TEXT DEFAULT ''"))
    db.commit()


def seed_database_if_empty() -> None:
    """Executes atomic database initialization and seeding on container cold-boot."""
  
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
        ensure_audit_record_columns(db)
        ensure_assignment_columns(db)
    
        analyst_user = db.query(Users).filter(Users.email == "analyst@compliancenexus.com").first()
        
        if not analyst_user:
            logger.info("[DB SEEDING]: Creating demo persona user accounts...")
            
            analyst_user = Users(
                email="analyst@compliancenexus.com",
                full_name="Sarah Jenkins",
                hashed_password=get_password_hash("analyst123"),
                role=Roles.L1_ANALYST,
                is_active=True
            )
            
            officer_user = Users(
                email="officer@compliancenexus.com",
                full_name="Marcus Vance",
                hashed_password=get_password_hash("officer123"),
                role=Roles.L2_RISK_OFFICER,
                is_active=True
            )
            
            db.add_all([analyst_user, officer_user])
            db.commit()
            db.refresh(analyst_user)
            logger.info("[USERS SEEDED]: Sarah Jenkins (L1) and Marcus Vance (L2) created.")
        else:
            logger.info("[USERS WARM]: Demo persona users already exist.")

       
        seed_json_path = settings.DB_DIR / "seed_data.json"
        
        if not seed_json_path.exists():
            logger.warning(f"[SEED WARNING]: File not found at {seed_json_path}. Skipping audit record seeding.")
            return

        logger.info(f"[DB SEEDING]: Loading authentic graph outputs from {seed_json_path.name}...")
        
        with open(seed_json_path, "r", encoding="utf-8") as file:
            records_data: List[Dict[str, Any]] = json.load(file)

        upserted = 0
        for item in records_data:
            status_value = resolve_status(item)
            citations_str = resolve_citations_json(item.get("citations_json", []))
            record_obj = db.query(AuditRecord).filter(
                AuditRecord.transaction_id == item["transaction_id"]
            ).first()
            if not record_obj:
                record_obj = AuditRecord(
                    transaction_id=item["transaction_id"],
                    user_id=analyst_user.id,
                    query=item["query"],
                )
                db.add(record_obj)

            record_obj.user_id = analyst_user.id
            record_obj.query = item["query"]
            record_obj.initiating_entity = item.get("initiating_entity", "Nexus India")
            record_obj.beneficiary = item.get("beneficiary", "Overseas Entity")
            record_obj.transaction_value = float(item.get("transaction_value", 0.0))
            record_obj.allowed_ceiling = float(item.get("allowed_ceiling", 0.0))
            record_obj.status = status_value
            record_obj.source_doc = item.get("source_doc", "N/A")
            record_obj.audit_verdict_markdown = item.get("audit_verdict_markdown", "")
            record_obj.citations_json = citations_str
            record_obj.evidence_json = resolve_json(item.get("evidence_items"), "[]")
            record_obj.selected_evidence_json = resolve_json(item.get("selected_evidence_items"), "[]")
            record_obj.audit_checks_json = resolve_json(item.get("audit_checks"), "[]")
            record_obj.audit_rationale_json = resolve_json(item.get("audit_rationale"), "{}")
            record_obj.pdf_path = str(item.get("pdf_path", ""))
            upserted += 1

        db.commit()
        logger.info(f"[AUDIT RECORDS SEEDED]: Upserted {upserted} records into SQLite.")

    except Exception as e:
        db.rollback()
        logger.error(f"[DB SEED ERROR]: Failed during seeding pipeline execution: {str(e)}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    print("Executing manual database seeding run...")
    seed_database_if_empty()
