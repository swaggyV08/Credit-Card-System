from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date
from uuid import UUID
from typing import List, Literal, Optional

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success, build_pagination
from app.schemas.responses import ApplicationSubmitResponse, ApplicationListResponse, ProcessApplicationResponse
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
from app.admin.models.credit_product import CreditProductInformation
from app.admin.services.issuance_svc import CardIssuanceService
from app.schemas.responses import ApplicationSubmitResponse
from pydantic import BaseModel

router = APIRouter(prefix="/applications", tags=["Credit Card Applications"])

# --- CUSTOMER ENDPOINTS ---

@router.post(
    "/",
    summary="Submit New Application",
    status_code=201,
    response_model=ApplicationSubmitResponse,
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
        CreditCardApplication.application_status.in_([ApplicationStatus.SUBMITTED, ApplicationStatus.IN_REVIEW])
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
    response_model=ApplicationListResponse,
    dependencies=[Depends(require("application:read"))]
)
def get_applications(
    command: Literal["all", "by_user"] = Query(..., description="Action to perform: 'all' or 'by_user'"),
    user_id: Optional[str] = Query(None, description="Required for command=by_user"),
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
        results = []
        for app_record in apps:
            bureau_report = db.query(BureauReport).filter(BureauReport.application_id == app_record.id).first()
            if not bureau_report:
                cif = db.query(CustomerProfile).filter(CustomerProfile.user_id == app_record.user_id).first()
                if cif:
                    assessment = CardIssuanceService.run_engines_pre_assessment(db, cif, app_record, app_record.credit_product)
                    new_bureau = BureauReport(
                        application_id=app_record.id,
                        bureau_score=assessment["bureau_data"]["bureau_score"],
                        report_reference_id=assessment["bureau_data"]["report_reference_id"],
                        bureau_snapshot=assessment["bureau_data"]["snapshot"]
                    )
                    db.add(new_bureau)
                    for rule in assessment["fraud_rules"]:
                        db.add(FraudFlag(application_id=app_record.id, flag_code=rule.code, flag_description=rule.description, severity=rule.severity))
                    db.add(RiskAssessment(application_id=app_record.id, risk_band=assessment["risk_assessment"]["band"], confidence_score=assessment["risk_assessment"]["confidence"], assessment_explanation=assessment["risk_assessment"]["explanation"]))
                    db.commit()
            
            payload = CreditCardApplicationResponse.model_validate(app_record)
            results.append(payload.model_dump(mode='json'))
        
        return envelope_success({
            "items": results,
            "pagination": build_pagination(len(results), 1, len(results) or 20)
        })

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
            "pagination": build_pagination(total, page, page_size)
        })


@router.post(
    "/{user_id}",
    response_model=ProcessApplicationResponse,
    response_model_exclude_none=True,
    summary="Process Application (Evaluate/Configure)",
    description="""
**Unified endpoint to evaluate or configure a credit card application.**

### Commands

#### `command=evaluate`
- Runs the automated credit assessment engines (Bureau, Fraud, Risk) against the application.
- Returns the evaluation result: `APPROVED` or `REJECTED`.
- **Does NOT accept a request body.** Send an empty body or `{}`.

#### `command=configure`
- The admin provides a configuration body with `application_status` (`Approve` or `Reject`).
- **If `Approve`**: creates a credit account with product-default limits and billing cycle.
- **If `Reject`**: manually rejects the application.
- This is the mandatory admin decision step.

### Request Body (for `command=configure` only)
```json
{
  "application_status": "Approve"
}
```

**Enums for `application_status`:** `Approve` | `Reject`

### Example Success Response (command=configure, Approve)
```json
{
  "status": "success",
  "data": {
    "credit_account_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "readable_id": "ACC-000001",
    "user_id": "ZNBNQ000001",
    "credit_limit": "100000.000",
    "available_limit": "100000.000",
    "cash_advance_limit": "0.000",
    "outstanding_amount": "0.000",
    "account_status": "ACTIVE",
    "billing_cycle_id": "CYCLE_15",
    "opened_at": "2026-04-08T10:30:00+00:00"
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-08T10:30:00.000000+00:00",
    "api_version": "1.0.0"
  },
  "errors": []
}
```

### Example Success Response (command=configure, Reject)
```json
{
  "status": "success",
  "data": {
    "message": "Application manually rejected by admin",
    "application_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "application_status": "REJECTED"
  },
  "meta": { ... },
  "errors": []
}
```

**Roles:** `application:evaluate`, `application:configure` (Admin / Manager / SuperAdmin)
""",
    dependencies=[Depends(require("application:evaluate")), Depends(require("application:configure"))]
)
async def process_application(
    user_id: str,
    command: Literal["evaluate", "configure"] = Query(..., description="Action to perform on user's application"),
    application_id: Optional[UUID] = Query(None, description="Required for evaluate/configure commands"),
    config_body: Optional[CreditAccountManualConfig] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("application:evaluate"))
):
    """
    Unified endpoint to evaluate or configure an application.
    - evaluate: run engines against an application (no body)
    - configure: admin override decision (requires body with application_status only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(code="NOT_FOUND", message="User not found", http_status=404)
        
    CIFService.assert_cif_kyc_complete(user)
    
    if not application_id:
        raise AppError(code="MISSING_APP_ID", message="application_id is required", http_status=422)

    if command == "evaluate":
        if config_body is not None:
            raise AppError(
                code="NO_BODY_ACCEPTED",
                message="command=evaluate does not accept a request body. Remove the request body and try again.",
                http_status=422
            )
        if request is not None:
            body = await request.body()
            if body and body.strip() not in (b"", b"null", b"{}"):
                raise AppError(
                    code="NO_BODY_ACCEPTED",
                    message="command=evaluate does not accept a request body. Remove the request body and try again.",
                    http_status=422
                )
                
        result = CardIssuanceService.evaluate_application(db, application_id, UUID(principal.user_id))
        return envelope_success(result)

    elif command == "configure":
        if config_body is None:
            if request is not None:
                try:
                    body = await request.json()
                    config_body = CreditAccountManualConfig(**body)
                except Exception:
                    raise AppError(code="MISSING_BODY", message="Configuration body required with application_status field", http_status=422)
            else:
                raise AppError(code="MISSING_BODY", message="Configuration body required", http_status=422)
        
        account = CardIssuanceService.configure_and_create_account(db, application_id, config_body, UUID(principal.user_id))
        
        if account is None:
            return envelope_success({
                "message": "Application manually rejected by admin",
                "application_id": str(application_id),
                "application_status": "REJECTED"
            })
            
        return envelope_success({
            "message": "credit application approved , card will be issued soon",
            "application_id": str(application_id),
            "credit_account_id": str(account.id),
            "user_id": str(account.user_id),
            "credit_limit": f"{account.credit_limit:.2f}",
            "available_limit": f"{account.available_limit:.2f}",
            "account_status": account.account_status.value if hasattr(account.account_status, "value") else str(account.account_status)
        })




