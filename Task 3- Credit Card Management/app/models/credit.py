import uuid
from sqlalchemy import Column, String, Boolean, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base
from sqlalchemy import Enum as SQLEnum
from app.models.enums import RiskBand, FraudFlagType, ApplicationStatus

class BureauReport(Base):
    __tablename__ = "bureau_report"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("credit_card_application.id"), nullable=False)
    bureau_score = Column(Integer, nullable=False)
    report_reference_id = Column(String, nullable=False)
    bureau_snapshot = Column(JSONB, nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    
    application = relationship("CreditCardApplication", back_populates="bureau_report")

class RiskAssessment(Base):
    __tablename__ = "risk_assessment"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("credit_card_application.id"), nullable=False)
    risk_band = Column(SQLEnum(RiskBand, native_enum=False), nullable=False) # LOW, MEDIUM, HIGH, VERY_HIGH
    confidence_score = Column(Numeric(5, 2), nullable=True)
    assessment_explanation = Column(String, nullable=True)
    assessed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    application = relationship("CreditCardApplication", back_populates="risk_assessment")

class FraudFlag(Base):
    __tablename__ = "fraud_flag"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("credit_card_application.id"), nullable=False)
    flag_code = Column(SQLEnum(FraudFlagType, native_enum=False), nullable=False) # e.g. RESIDENCY_MISMATCH
    flag_description = Column(String, nullable=True)
    severity = Column(String, default="MEDIUM") # LOW, MEDIUM, HIGH, CRITICAL
    flagged_at = Column(DateTime(timezone=True), server_default=func.now())
    
    application = relationship("CreditCardApplication", backref="fraud_flags")

class CreditDecision(Base):
    __tablename__ = "credit_decision"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("credit_card_application.id"), nullable=False)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=False)
    decision = Column(SQLEnum(ApplicationStatus, native_enum=False), nullable=False) # APPROVED, REJECTED
    override_flag = Column(Boolean, default=False)
    notes = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=True), server_default=func.now())
    
    application = relationship("CreditCardApplication", backref="decision_record", uselist=False)
    admin = relationship("Admin")
