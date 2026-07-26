import datetime
import json
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, 
    Boolean, ForeignKey,Enum
)
from app.core.database import Base
import enum

class Roles(str,enum.Enum):
    L1_ANALYST = "l1_analyst"
    L2_RISK_OFFICER = "l2_analyst"
    COMPLIANCE_ADMIN = "compliance_admin"

class AuditRecord(Base):
    __tablename__ = "audit_records"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(50), unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.id'))
    query = Column(Text, nullable=False)
    initiating_entity = Column(String(100), default="Nexus India")
    beneficiary = Column(String(100), default="Overseas Vendor")
    transaction_value = Column(Float, nullable=False)
    allowed_ceiling = Column(Float, nullable=False)
    
    status = Column(String(30), index=True, nullable=False)  # COMPLIANT | NON_COMPLIANT | ACTION_REQUIRED
    source_doc = Column(String(150), nullable=False)
    audit_verdict_markdown = Column(Text, nullable=False)
    
    citations_json = Column(Text, default="[]")
    pdf_path = Column(String(255))

    @property
    def citations(self):
        """Helper to parse citations_json back to Python list."""
        try:
            return json.loads(self.citations_json)
        except Exception:
            return []

    @citations.setter
    def citations(self, value: list):
        """Helper to serialize Python list to JSON string."""
        self.citations_json = json.dumps(value)


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String,unique=True,index=True)
    hashed_password = Column(String)
    full_name = Column(String(150))
    role = Column(Enum(Roles, native_enum=False))
    is_active = Column(Boolean,default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
