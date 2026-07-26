import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from passlib.context import CryptContext
from sqlalchemy.orm import Session

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
    """Ensures citations are safely serialized to a JSON string for SQLite storage."""
    if isinstance(citations_raw, str):
        
        return citations_raw
    if isinstance(citations_raw, list):
        return json.dumps(citations_raw)
    return "[]"


def seed_database_if_empty() -> None:
    """Executes atomic database initialization and seeding on container cold-boot."""
  
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
    
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

       
        if db.query(AuditRecord).count() == 0:
            seed_json_path = settings.DB_DIR / "seed_data.json"
            
            if not seed_json_path.exists():
                logger.warning(f"[SEED WARNING]: File not found at {seed_json_path}. Skipping audit record seeding.")
                return

            logger.info(f"[DB SEEDING]: Loading authentic graph outputs from {seed_json_path.name}...")
            
            with open(seed_json_path, "r", encoding="utf-8") as file:
                records_data: List[Dict[str, Any]] = json.load(file)

            audit_records_to_insert: List[AuditRecord] = []
            
            for item in records_data:
                status_value = resolve_status(item)
                citations_str = resolve_citations_json(item.get("citations_json", []))
                
                record_obj = AuditRecord(
                    transaction_id=item["transaction_id"],
                    user_id=analyst_user.id,
                    query=item["query"],
                    initiating_entity=item.get("initiating_entity", "Nexus India"),
                    beneficiary=item.get("beneficiary", "Overseas Entity"),
                    transaction_value=float(item.get("transaction_value", 0.0)),
                    allowed_ceiling=float(item.get("allowed_ceiling", 0.0)),
                    status=status_value,
                    source_doc=item.get("source_doc", "N/A"),
                    audit_verdict_markdown=item.get("audit_verdict_markdown", ""),
                    citations_json=citations_str,
                    pdf_path=str(item.get("pdf_path", ""))
                )
                audit_records_to_insert.append(record_obj)

            db.add_all(audit_records_to_insert)
            db.commit()
            logger.info(f"[AUDIT RECORDS SEEDED]: Successfully loaded {len(audit_records_to_insert)} records into SQLite.")
        else:
            logger.info("[AUDIT RECORDS WARM]: Transaction history table already populated.")

    except Exception as e:
        db.rollback()
        logger.error(f"[DB SEED ERROR]: Failed during seeding pipeline execution: {str(e)}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    print("Executing manual database seeding run...")
    seed_database_if_empty()