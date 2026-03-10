from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date
from uuid import UUID

from app.api.deps import get_db, get_current_authenticated_user
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.card_product import CardProductCore
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount
from app.models.enums import ApplicationStatus, ApplicationStage
from app.schemas.credit import ApplicationCreateRequest
from app.models.credit import BureauReport, RiskAssessment, FraudFlag
from app.services.engines.bureau_engine import simulate_bureau_score
from app.services.engines.fraud_engine import detect_fraud_anomalies
from app.services.engines.risk_engine import calculate_risk_assessment
from pydantic import BaseModel

class ApplicationSubmitResponse(BaseModel):
    application_id: UUID

router = APIRouter(prefix="/applications", tags=["Credit Card Applications"])

@router.post("/", response_model=ApplicationSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_application(
    data: ApplicationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Submits a new credit card application for the current user.
    """
    if not current_user.is_cif_completed or not current_user.is_kyc_completed:
        raise HTTPException(status_code=400, detail="CIF and KYC must be completed before applying for a credit card.")

    cif = db.query(CustomerProfile).filter(CustomerProfile.user_id == current_user.id).first()
    if not cif:
        raise HTTPException(status_code=400, detail="CIF not found for user. Complete KYC first.")
        
    card_product = db.query(CardProductCore).filter(CardProductCore.id == data.card_product_id).first()
    if not card_product:
        raise HTTPException(status_code=404, detail="Card product not found")

    # 1. Check for max limit (upto 3 credit cards of different types)
    account_count = db.query(CreditAccount).filter(CreditAccount.cif_id == cif.id).count()
    if account_count >= 3:
        raise HTTPException(
            status_code=400,
            detail="You can only have upto 3 credit cards of different types"
        )

    # 2. Check for duplicate product application (idempotency/uniqueness)
    existing_app = db.query(CreditCardApplication).filter(
        CreditCardApplication.cif_id == cif.id,
        CreditCardApplication.card_product_id == card_product.id,
        CreditCardApplication.application_status.in_([ApplicationStatus.SUBMITTED, ApplicationStatus.IN_REVIEW, ApplicationStatus.KYC_PENDING])
    ).first()
    
    if existing_app:
        # IDEMPOTENCY: Return the same application ID if already submitted
        return {"application_id": existing_app.id}

    # 3. Check if user already has an account for this specific product
    existing_account = db.query(CreditAccount).filter(
        CreditAccount.cif_id == cif.id,
        CreditAccount.card_product_id == card_product.id
    ).first()
    
    if existing_account:
        raise HTTPException(
            status_code=400,
            detail="You already have an active credit account for this card product"
        )

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
    db.flush() # Get application ID for relationships

    # --- ENGINE INTEGRATION (Deterministic Assessment) ---
    # 1. Age calculation
    today = date.today()
    age = today.year - cif.date_of_birth.year - (
        (today.month, today.day) < (cif.date_of_birth.month, cif.date_of_birth.day)
    )

    # 2. Bureau Score
    bureau_data = simulate_bureau_score(
        age=age,
        annual_income=float(cif.financial_information.net_annual_income) if cif.financial_information else float(data.declared_income),
        employment_type=cif.employment_detail.employment_type if cif.employment_detail else data.employment_status,
        country=cif.country_of_residence,
        is_kyc_completed=current_user.is_kyc_completed
    )
    bureau_report = BureauReport(
        application_id=application.id,
        bureau_score=bureau_data["bureau_score"],
        report_reference_id=bureau_data["report_reference_id"],
        bureau_snapshot=bureau_data["snapshot"]
    )
    db.add(bureau_report)

    # 3. Fraud Detection
    # Velocity count (apps in last 24h)
    from datetime import timedelta
    past_24h = datetime.now() - timedelta(days=1)
    velocity = db.query(CreditCardApplication).filter(
        CreditCardApplication.user_id == current_user.id,
        CreditCardApplication.submitted_at >= past_24h
    ).count()

    fraud_rules = detect_fraud_anomalies(
        declared_country=cif.country_of_residence.value if hasattr(cif.country_of_residence, 'value') else str(cif.country_of_residence),
        ip_country=None, # In real world, from Request
        declared_income=float(data.declared_income),
        verified_income=float(cif.financial_information.net_annual_income) if cif.financial_information else None,
        application_velocity_count=velocity
    )

    for rule in fraud_rules:
        f_flag = FraudFlag(
            application_id=application.id,
            flag_code=rule.code,
            flag_description=rule.description,
            severity=rule.severity
        )
        db.add(f_flag)

    # 4. Risk Assessment
    risk_band, confidence, explanation = calculate_risk_assessment(
        bureau_score=bureau_data["bureau_score"],
        fraud_flags=fraud_rules,
        declared_income=float(data.declared_income)
    )
    risk_assessment = RiskAssessment(
        application_id=application.id,
        risk_band=risk_band,
        confidence_score=confidence,
        assessment_explanation=explanation
    )
    db.add(risk_assessment)

    db.commit()
    db.refresh(application)
    
    return {"application_id": application.id}
