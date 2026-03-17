from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date
from uuid import UUID
from typing import List

from app.api.deps import get_db, get_current_authenticated_user, get_current_admin_user
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.card_product import CardProductCore
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card
from app.models.enums import ApplicationStatus, ApplicationStage
from app.schemas.credit import ApplicationCreateRequest
from app.models.credit import BureauReport, RiskAssessment, FraudFlag
from app.services.engines.bureau_engine import simulate_bureau_score
from app.services.engines.fraud_engine import detect_fraud_anomalies
from app.services.engines.risk_engine import calculate_risk_assessment
from app.admin.schemas.card_issuance import (
    CreditCardApplicationResponse,
    CreditCardApplicationSummary, CreditAccountResponse, CardResponse,
    ApplicationReviewResponse, ApplicationReviewRequest, AdminKYCReviewRequest,
    CreditAccountManualConfig, IssueCardRequest
)
from pydantic import BaseModel

class ApplicationSubmitResponse(BaseModel):
    application_id: UUID

router = APIRouter(prefix="/applications", tags=["Credit Card Applications"])

# --- CUSTOMER ENDPOINTS ---

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def submit_application(
    data: ApplicationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Submits a new credit card application for the current user.
    
    **Exactly why we are implementing this**:
    To ensure banking-grade integrity, we assess the applicant's eligibility (Bureau, Fraud, Risk) 
    *before* storing the application in our core ledger. This prevents 'dead' or 'rejected' 
    records from bloating our database and ensures only qualified applications proceed to the KYC/Review stage.
    
    **Business Logic**:
    1. **Normalization**: Fields like product code and employment status are converted to lower case.
    2. **Preliminary Checks**: Validates CIF completeness and maximum card limits (max 3).
    3. **Pre-Assessment**: Runs automated engines using dynamic product rules from the database.
    4. **Zero-Storage Rejection**: If the applicant fails eligibility (e.g., low score), we return a 
       clear human-readable rejection message and do *not* create a database record.
    5. **Back-dating Protection**: Rejects any application with a date in the past.
    """
    if not current_user.is_cif_completed or not current_user.is_kyc_completed:
        raise HTTPException(status_code=400, detail="Incomplete Profile: You must complete CIF and KYC registration before applying for a credit card.")

    cif = db.query(CustomerProfile).filter(CustomerProfile.user_id == current_user.id).first()
    if not cif:
        raise HTTPException(status_code=400, detail="Customer Profile not found. Please ensure your account setup is complete.")
        
    from app.admin.models.credit_product import CreditProductInformation
    
    # Case conversion is handled in the schema (.lower())
    credit_product = db.query(CreditProductInformation).filter(
        CreditProductInformation.product_code == data.credit_product_code
    ).first()
    
    if not credit_product:
        raise HTTPException(status_code=404, detail=f"Invalid Product: Credit product with code '{data.credit_product_code}' was not found in our catalog.")

    # Pick the first associated card product
    card_product = db.query(CardProductCore).filter(
        CardProductCore.credit_product_id == credit_product.id
    ).first()
    
    if not card_product:
        raise HTTPException(status_code=404, detail="Configuration Error: This credit product is currently unavailable for new card issuance.")

    # 1. Limit Check (upto 3 credit cards)
    account_count = db.query(CreditAccount).filter(CreditAccount.cif_id == cif.id).count()
    if account_count >= 3:
        raise HTTPException(
            status_code=400,
            detail="Limit Reached: You are only eligible for up to 3 active credit cards across different products."
        )

    # 2. Duplicate Check
    existing_app = db.query(CreditCardApplication).filter(
        CreditCardApplication.cif_id == cif.id,
        CreditCardApplication.card_product_id == card_product.id,
        CreditCardApplication.application_status.in_([ApplicationStatus.SUBMITTED, ApplicationStatus.IN_REVIEW, ApplicationStatus.KYC_PENDING])
    ).first()
    
    if existing_app:
        return {"message": "You have an existing application in progress for this product.", "application_id": existing_app.id}

    # 3. EXISTING ACCOUNT CHECK
    existing_account = db.query(CreditAccount).filter(
        CreditAccount.cif_id == cif.id,
        CreditAccount.card_product_id == card_product.id
    ).first()
    
    if existing_account:
        raise HTTPException(
            status_code=400,
            detail="Ownership Conflict: Our records show you already hold an active credit account for this specific card product."
        )

    # --- PRE-PERSISTENCE ASSESSMENT ---
    from app.admin.services.issuance_svc import CardIssuanceService
    assessment = CardIssuanceService.run_engines_pre_assessment(db, cif, data, credit_product)

    if assessment["status"] == "REJECTED":
        # DO NOT STORE IN DB AS PER REQUIREMENT
        return {
            "message": f"Application Rejected: {assessment['reason']}",
            "status": "REJECTED"
        }

    # --- PERSISTENCE (ONLY FOR APPROVED) ---
    application = CreditCardApplication(
        user_id=current_user.id,
        cif_id=cif.id,
        credit_product_id=card_product.credit_product_id, 
        card_product_id=card_product.id,
        application_status=ApplicationStatus.SUBMITTED,
        current_stage=ApplicationStage.KYC,
        
        declared_income=data.declared_income,
        income_frequency=data.income_frequency,
        employment_status=data.employment_status,
        occupation=data.occupation,
        employer_name=data.employer_name,
        work_experience_years=data.work_experience_years,
        
        existing_emis_monthly=data.existing_emis_monthly,
        has_existing_credit_card=data.has_existing_credit_card,
        existing_cards_count=data.existing_cards_count,
        approx_credit_limit_total=data.approx_credit_limit_total,
        
        residential_status=data.residential_status,
        years_at_current_address=data.years_at_current_address,
        preferred_billing_cycle=data.preferred_billing_cycle,
        statement_delivery_mode=data.statement_delivery_mode,
        card_delivery_address_type=data.card_delivery_address_type,
        preferred_branch_code=data.preferred_branch_code,
        
        nominee_name=data.nominee_name,
        nominee_relationship=data.nominee_relationship,
        
        consent_terms_accepted=data.consent_terms_accepted,
        consent_credit_bureau_check=data.consent_credit_bureau_check,
        consent_marketing_communication=data.consent_marketing_communication,
        application_declaration_accepted=data.application_declaration_accepted
    )
    
    db.add(application)
    db.flush()

    # Save Assessment Results
    bureau_report = BureauReport(
        application_id=application.id,
        bureau_score=assessment["bureau_data"]["bureau_score"],
        report_reference_id=assessment["bureau_data"]["report_reference_id"],
        bureau_snapshot=assessment["bureau_data"]["snapshot"]
    )
    db.add(bureau_report)

    for rule in assessment["fraud_rules"]:
        f_flag = FraudFlag(
            application_id=application.id,
            flag_code=rule.code,
            flag_description=rule.description,
            severity=rule.severity
        )
        db.add(f_flag)

    risk_assessment = RiskAssessment(
        application_id=application.id,
        risk_band=assessment["risk_assessment"]["band"],
        confidence_score=assessment["risk_assessment"]["confidence"],
        assessment_explanation=assessment["risk_assessment"]["explanation"]
    )
    db.add(risk_assessment)

    db.commit()
    db.refresh(application)
    
    return {
        "message": "Application submitted successfully and passed initial eligibility checks.",
        "application_id": application.id,
        "status": "SUBMITTED"
    }


# --- ADMIN ENDPOINTS (Consolidated) ---

@router.get("/all", response_model=List[CreditCardApplicationSummary])
def get_all_applications(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Fetch all credit applications setup for Admin Listing.
    """
    return db.query(CreditCardApplication).all()

@router.get("/{application_id}", response_model=CreditCardApplicationResponse)
def get_application_details(
    application_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Fetch full details of an application.
    """
    from app.admin.services.issuance_svc import CardIssuanceService
    
    app = db.query(CreditCardApplication).filter(CreditCardApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Auto-generate assessments if missing
    CardIssuanceService.run_engines(db, app)
    
    return app

@router.post("/{application_id}/evaluate")
def evaluate_application(
    application_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Automatically evaluate a Credit Card Application (after KYC review).
    Transitions status from KYC_REVIEW to PENDING (for manual config) or REJECTED.
    """
    from app.admin.services.issuance_svc import CardIssuanceService
    return CardIssuanceService.evaluate_application(db, application_id, admin.id)

@router.post("/{application_id}/account", response_model=CreditAccountResponse)
def configure_account(
    application_id: UUID,
    config: CreditAccountManualConfig,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Manually configure and provision a credit account for an APPROVED application.
    
    **Billing Cycle IDs**:
    - CYCLE_01: Statement on 1st of month
    - CYCLE_05: Statement on 5th
    - CYCLE_10: Statement on 10th
    - CYCLE_15: Statement on 15th
    - CYCLE_20: Statement on 20th
    - CYCLE_25: Statement on 25th
    - CYCLE_28: Statement on 28th
    """
    from app.admin.services.issuance_svc import CardIssuanceService
    return CardIssuanceService.configure_and_create_account(db, application_id, config, admin.id)


@router.post("/{credit_account_id}/card", response_model=CardResponse)
def issue_card_for_account(
    credit_account_id: UUID,
    data: IssueCardRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Manually issue a card against an existing credit account.
    """
    from app.admin.services.issuance_svc import CardIssuanceService
    return CardIssuanceService.issue_card_manual(db, credit_account_id, data, admin.id)
