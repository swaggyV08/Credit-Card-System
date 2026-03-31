from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date
from uuid import UUID
from typing import List, Literal, Optional

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.core.app_error import AppError
from app.services.cif_service import CIFService
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

@router.post(
    "/",
    summary="Submit New Application",
    dependencies=[Depends(require("application:submit"))]
)
def submit_application(
    data: ApplicationCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("application:submit"))
):
    """
    Submits a new credit card application for the current user.
    """
    user = db.query(User).filter(User.id == principal.user_id).first()
    if not user:
        raise AppError(code="NOT_FOUND", message="User not found", http_status=404)
        
    # CIF/KYC Gate Integration
    CIFService.assert_cif_kyc_complete(user)

    cif = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not cif:
        raise AppError(code="PROFILE_MISSING", message="Customer Profile not found. Please ensure your account setup is complete.", http_status=400)
        
    from app.admin.models.credit_product import CreditProductInformation
    
    # Case conversion is handled in the schema (.lower())
    credit_product = db.query(CreditProductInformation).filter(
        CreditProductInformation.product_code == data.credit_product_code
    ).first()
    
    if not credit_product:
        raise AppError(code="INVALID_PRODUCT", message=f"Invalid Product: Credit product with code '{data.credit_product_code}' was not found in our catalog.", http_status=404)

    card_product = db.query(CardProductCore).filter(
        CardProductCore.credit_product_id == credit_product.id
    ).first()
    
    if not card_product:
        raise AppError(code="UNAVAILABLE", message="Configuration Error: This credit product is currently unavailable for new card issuance.", http_status=404)

    # 1. Limit Check (upto 3 credit cards)
    account_count = db.query(CreditAccount).filter(CreditAccount.user_id == user.id).count()
    if account_count >= 3:
        raise AppError(
            code="LIMIT_REACHED",
            message="Limit Reached: You are only eligible for up to 3 active credit cards across different products.",
            http_status=400
        )

    # 2. Duplicate Check
    existing_app = db.query(CreditCardApplication).filter(
        CreditCardApplication.user_id == user.id,
        CreditCardApplication.card_product_id == card_product.id,
        CreditCardApplication.application_status.in_([ApplicationStatus.SUBMITTED, ApplicationStatus.IN_REVIEW, ApplicationStatus.KYC_PENDING])
    ).first()
    
    if existing_app:
        return envelope_success({"message": "You have an existing application in progress for this product.", "application_id": str(existing_app.id)})

    # 3. EXISTING ACCOUNT CHECK
    existing_account = db.query(CreditAccount).filter(
        CreditAccount.user_id == user.id,
        CreditAccount.card_product_id == card_product.id
    ).first()
    
    if existing_account:
        raise AppError(
            code="OWNERSHIP_CONFLICT",
            message="Ownership Conflict: Our records show you already hold an active credit account for this specific card product.",
            http_status=400
        )

    # --- PRE-PERSISTENCE ASSESSMENT ---
    from app.admin.services.issuance_svc import CardIssuanceService
    assessment = CardIssuanceService.run_engines_pre_assessment(db, cif, data, credit_product)

    if assessment["status"] == "REJECTED":
        # DO NOT STORE IN DB AS PER REQUIREMENT
        return envelope_success({
            "message": f"Application Rejected: {assessment['reason']}",
            "status": "REJECTED"
        })

    # --- PERSISTENCE (ONLY FOR APPROVED) ---
    application = CreditCardApplication(
        user_id=user.id,
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
    
    return envelope_success({
        "message": "Application submitted successfully and passed initial eligibility checks.",
        "application_id": str(application.id),
        "status": "SUBMITTED"
    })


# --- ADMIN ENDPOINTS (Consolidated) ---

@router.get(
    "/",
    summary="Get Applications",
    dependencies=[Depends(require("application:read"))]
)
def get_applications(
    command: Literal["all", "by_user"] = Query(..., description="Action to perform: 'all' or 'by_user'"),
    user_id: Optional[UUID] = Query(None, description="Required for command=by_user"),
    status_filter: Optional[ApplicationStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("application:read"))
):
    if command == "by_user":
        if status_filter is not None or page != 1 or page_size != 20 or sort_order != "desc":
            raise AppError(
                code="INVALID_SIGNATURE",
                message="Only user_id is accepted as input for command=by_user",
                http_status=422
            )
        if not user_id:
            raise AppError(code="MISSING_USER_ID", message="user_id is required for command=by_user", http_status=422)

        apps = db.query(CreditCardApplication).filter(CreditCardApplication.user_id == user_id).all()
        
        # Hydrate application details with assessments if needed
        from app.admin.services.issuance_svc import CardIssuanceService
        results = []
        for app in apps:
            bureau_report = db.query(BureauReport).filter(BureauReport.application_id == app.id).first()
            if not bureau_report:
                cif = db.query(CustomerProfile).filter(CustomerProfile.user_id == app.user_id).first()
                if cif:
                    assessment = CardIssuanceService.run_engines_pre_assessment(db, cif, app, app.credit_product)
                    new_bureau = BureauReport(
                        application_id=app.id,
                        bureau_score=assessment["bureau_data"]["bureau_score"],
                        report_reference_id=assessment["bureau_data"]["report_reference_id"],
                        bureau_snapshot=assessment["bureau_data"]["snapshot"]
                    )
                    db.add(new_bureau)
                    for rule in assessment["fraud_rules"]:
                        db.add(FraudFlag(application_id=app.id, flag_code=rule.code, flag_description=rule.description, severity=rule.severity))
                    db.add(RiskAssessment(application_id=app.id, risk_band=assessment["risk_assessment"]["band"], confidence_score=assessment["risk_assessment"]["confidence"], assessment_explanation=assessment["risk_assessment"]["explanation"]))
                    db.commit()
            
            payload = CreditCardApplicationResponse.model_validate(app)
            results.append(payload.model_dump(mode='json'))
        
        return envelope_success(results)

    elif command == "all":
        query = db.query(CreditCardApplication)
        if status_filter:
            query = query.filter(CreditCardApplication.application_status == status_filter)
        if sort_order == "desc":
            query = query.order_by(CreditCardApplication.submitted_at.desc())
        else:
            query = query.order_by(CreditCardApplication.submitted_at.asc())
            
        total = query.count()
        apps = query.offset((page - 1) * page_size).limit(page_size).all()
        
        items = [CreditCardApplicationSummary.model_validate(app).model_dump(mode='json') for app in apps]
        return envelope_success({
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        })


@router.post(
    "/{user_id}",
    summary="Process Application (Evaluate/Configure)",
    dependencies=[Depends(require("application:evaluate")), Depends(require("application:configure"))]
)
async def process_application(
    user_id: UUID,
    command: Literal["evaluate", "configure"] = Query(..., description="Action to perform on user's application"),
    application_id: Optional[UUID] = Query(None, description="Required for evaluate/configure commands"),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Unified endpoint to evaluate or configure an application.
    - evaluate: run engines against an application
    - configure: configure account and limits
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(code="NOT_FOUND", message="User not found", http_status=404)
        
    CIFService.assert_cif_kyc_complete(user)
    
    if not application_id:
        raise AppError(code="MISSING_APP_ID", message="application_id is required", http_status=422)

    if command == "evaluate":
        if request is not None:
            body = await request.body()
            if body and body.strip() not in (b"", b"null", b"{}"):
                raise HTTPException(status_code=422, detail={
                    "code": "NO_BODY_ACCEPTED",
                    "message": "command=evaluate does not accept a request body. Remove the request body and try again."
                })
                
        from app.admin.services.issuance_svc import CardIssuanceService
        result = CardIssuanceService.evaluate_application(db, application_id, user_id)
        return envelope_success(result)

    elif command == "configure":
        if request is None:
            raise AppError(code="MISSING_BODY", message="Configuration body required", http_status=422)
            
        body = await request.json()
        config = CreditAccountManualConfig(**body)
        
        from app.admin.services.issuance_svc import CardIssuanceService
        account = CardIssuanceService.configure_and_create_account(db, application_id, config, user_id)
        payload = CreditAccountResponse.model_validate(account)
        return envelope_success(payload.model_dump(mode='json'))


@router.post(
    "/{credit_account_id}/card",
    summary="Issue Card",
    dependencies=[Depends(require("application:issue_card"))]
)
def issue_card_for_account(
    credit_account_id: UUID,
    data: IssueCardRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("application:issue_card"))
):
    from app.admin.services.issuance_svc import CardIssuanceService
    card = CardIssuanceService.issue_card_manual(db, credit_account_id, data, principal.user_id)
    payload = CardResponse.model_validate(card)
    return envelope_success(payload.model_dump(mode='json'))
