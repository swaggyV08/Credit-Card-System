from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Header
from sqlalchemy.orm import Session
from uuid import UUID
import uuid
import random
from typing import List, Optional, Literal
from datetime import datetime, timezone
from app.models.enums import ProductStatus

from app.api.deps import get_db
from app.models.auth import User
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success, build_pagination
from app.core.app_error import AppError
from app.schemas.responses import CreditProductCreateResponse as CreditProductCreateEnvelope, CreditProductStatusResponse, CreditProductDeleteResponse, CreditProductGetResponse
from app.admin.schemas.credit_product import (
    CreditProductCreate, 
    CreditProductResponse, 
    CreditProductUpdate,
    CreditProductStatusUpdateResponse,
    CreditProductSummaryResponse,
    CreditProductCreateResponse,
    CreditProductApprovalRequest
)
from app.admin.models.credit_product import (
    CreditProductInformation, CreditProductLimits, CreditProductInterestFramework,
    CreditProductFees, CreditProductEligibilityRules,
    CreditProductComplianceMetadata, CreditProductAccountingMapping, CreditProductGovernance
)
from app.admin.services.credit_product_svc import CreditProductService

router = APIRouter(prefix="/credit-products", tags=["Admin: Credit Products"])


@router.post(
    "/",
    summary="Create Credit Product",
    response_model=CreditProductCreateEnvelope,
    dependencies=[Depends(require("credit_product:create"))]
)
def create_credit_product(
    data: CreditProductCreate,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_product:create"))
):
    """
    Creates a new Credit Product in DRAFT status with its full configuration.
    
    **Exactly why we are implementing this**:
    Administrative users need a workbench to define financial guardrails (limits, APR, fees) before a product 
    is made live for customers. DRAFT status allows for multi-stage setup and compliance review.
    """
    while True:
        product_code = f"cp-{random.randint(10000, 99999)}"
        existing = db.query(CreditProductInformation).filter(CreditProductInformation.product_code == product_code).first()
        if not existing:
            break

    product = CreditProductInformation(
        product_code=product_code,
        product_name=data.product_name,
        product_category=data.product_category
    )
    db.add(product)
    db.flush() # To obtain ID

    # Create associated children records
    db.add(CreditProductLimits(credit_product_id=product.id, **data.limits.model_dump()))
    db.add(CreditProductInterestFramework(credit_product_id=product.id, **data.interest_framework.model_dump()))
    db.add(CreditProductFees(credit_product_id=product.id, **data.fees.model_dump()))
    db.add(CreditProductEligibilityRules(credit_product_id=product.id, **data.eligibility_rules.model_dump()))
    db.add(CreditProductComplianceMetadata(credit_product_id=product.id, **data.compliance_metadata.model_dump()))
    db.add(CreditProductAccountingMapping(
        credit_product_id=product.id, 
        principal_gl_code="gl-1001",
        interest_income_gl_code="gl-4001",
        fee_income_gl_code="gl-4002",
        penalty_gl_code="gl-4003",
        writeoff_gl_code="gl-9001"
    ))
    
    db.add(CreditProductGovernance(
        credit_product_id=product.id,
        auto_renewal_allowed=data.auto_renewal_allowed,
        cooling_period_days=data.cooling_period_days,
        created_by=UUID(principal.user_id)
    ))
    
    db.commit()
    db.refresh(product)
    
    payload = CreditProductCreateResponse.model_validate(product)
    return envelope_success(payload.model_dump(mode='json'))

@router.get(
    "/",
    summary="Get Credit Products",
    description="""
**Unified endpoint to retrieve credit products.**

### Commands
- `command=all` — Returns a paginated list of all credit products.
- `command=by_id` — Returns full details for a single product (requires `product_id`).

### Query Parameters
- `status_filter`: `DRAFT` | `ACTIVE` | `SUSPENDED` | `REJECTED`
- `page`, `page_size`: Pagination controls
- `sort_by`, `sort_order`: Sorting controls

### Example Success Response (command=all)
```json
{
  "status": "success",
  "data": {
    "items": [
      {
        "product_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "product_code": "cp-12345",
        "product_name": "ZBanque Gold Card",
        "status": "ACTIVE"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1,
    "has_next": false,
    "has_previous": false
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-08T10:30:00.000000+00:00",
    "api_version": "1.0.0"
  },
  "errors": []
}
```

### Example Success Response (command=by_id)
```json
{
  "status": "success",
  "data": {
    "product_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "product_code": "cp-12345",
    "product_name": "ZBanque Gold Card",
    "product_category": "CARD",
    "product_version": 1,
    "status": "ACTIVE",
    "limits": {
      "min_credit_limit": "100000.000",
      "max_credit_limit": "500000.000",
      "max_total_exposure_per_cif": "1000000.000",
      "revolving_credit_allowed": true,
      "overlimit_allowed": false,
      "overlimit_percentage": "0.000"
    },
    "interest_framework": {
      "interest_type": "FIXED",
      "base_interest_rate": "36.000",
      "interest_calculation_method": "AVERAGE_DAILY_BALANCE",
      "interest_basis": "ACTUAL_360",
      "penal_interest_rate": "42.000",
      "interest_free_allowed": true,
      "max_interest_free_days": 30
    },
    "fees": {
      "joining_fee": "500.000",
      "annual_fee": "1000.000",
      "renewal_fee": "500.000",
      "late_payment_fee": "500.000",
      "overlimit_fee": "0.000",
      "cash_advance_fee": "500.000"
    },
    "eligibility_rules": {
      "min_age": 18,
      "max_age": 70,
      "min_income_required": "300000.000",
      "employment_types_allowed": ["FULL_TIME", "SELF_EMPLOYED"],
      "min_credit_score": 750,
      "secured_flag": false
    },
    "compliance_metadata": {
      "regulatory_product_code": "rpc-001",
      "kyc_level_required": "FULL_KYC",
      "aml_risk_category": "MEDIUM",
      "jurisdiction": "India",
      "tax_applicability": "GST_APPLICABLE",
      "statement_disclosure_version": "v1.0",
      "regulatory_reporting_category": "retail-unsecured"
    },
    "governance": {
      "card_product_version": 1,
      "effective_from": "2026-04-08T10:30:00+00:00",
      "effective_to": null,
      "created_at": "2026-04-08T10:30:00+00:00",
      "created_by": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "approved_by": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    }
  },
  "meta": { ... },
  "errors": []
}
```

**Roles:** `credit_product:read` (Admin / Manager / SuperAdmin)
""",
    dependencies=[Depends(require("credit_product:read"))],
    response_model=CreditProductGetResponse
)
def get_credit_products(
    command: Literal["all", "by_id"] = Query(..., description="Action to perform"),
    product_id: Optional[UUID] = Header(None, alias="product-id", description="Required for by_id"),
    status_filter: Optional[Literal["DRAFT", "ACTIVE", "SUSPENDED", "REJECTED"]] = Query(None, description="Filter products by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Optional[str] = Query("id"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_product:read"))
):
    if command == "by_id":
        if not product_id:
            raise AppError(code="MISSING_PRODUCT_ID", message="product-id header is required for by_id", http_status=422)
            
        product = CreditProductService.get_product(db, product_id)
        payload = CreditProductResponse.model_validate(product)
        return envelope_success(payload.model_dump(mode='json'))

    elif command == "all":
        query = db.query(CreditProductInformation)
        if status_filter:
            query = query.filter(CreditProductInformation.status == status_filter)
            
        total = query.count()
        skip = (page - 1) * page_size
        
        sort_attr = getattr(CreditProductInformation, sort_by, CreditProductInformation.id)
        if sort_order == "desc":
            query = query.order_by(sort_attr.desc())
        else:
            query = query.order_by(sort_attr.asc())
            
        products = query.offset(skip).limit(page_size).all()
        items = [CreditProductSummaryResponse.model_validate(p).model_dump(mode='json') for p in products]
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        
        return envelope_success({
            "items": items,
            "pagination": build_pagination(total, page, page_size)
        })

@router.post(
    "/{product_id}",
    summary="Update Product Status",
    response_model=CreditProductStatusResponse,
    dependencies=[Depends(require("credit_product:status"))]
)
def update_credit_product_status(
    product_id: UUID,
    command: Literal["approve", "reject", "suspend"] = Query(..., description="Action to perform"),
    data: Optional[CreditProductApprovalRequest] = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_product:status"))
):
    """
    Transitions a Credit Product's lifecycle status via the `command` query parameter.
    
    **Exactly why we are implementing this**:
    Implements the Governance workflow. Products move from DRAFT to ACTIVE only after approval. 
    Suspension and Rejection controls allow the bank to respond to market or regulatory changes quickly.
    
    **Commands**: `approve`, `reject`, `suspend`.
    """
    command = command.lower().strip()
    if command == "approve":
        effective_to_dt = None
        if data and data.effective_to:
            effective_to_dt = datetime(data.effective_to.year, data.effective_to.month, data.effective_to.day, tzinfo=timezone.utc)
        
        product = CreditProductService.approve_product(db, product_id, UUID(principal.user_id), effective_to_dt)
        return envelope_success({
            "message": "Credit Product approved",
            "product_id": str(product.id),
            "product_code": product.product_code,
            "product_name": product.product_name
        })
    elif command == "reject":
        reason = data.reject_reason if data else None
        product = CreditProductService.reject_product(db, product_id, UUID(principal.user_id), reason)
        return envelope_success({
            "message": "Credit Product rejected",
            "product_id": str(product.id),
            "product_code": product.product_code,
            "product_name": product.product_name,
            "reject_reason": reason
        })
    elif command == "suspend":
        product = CreditProductService.suspend_product(db, product_id, UUID(principal.user_id))
        return envelope_success({
            "message": "Credit Product suspended",
            "product_id": str(product.id),
            "product_code": product.product_code,
            "product_name": product.product_name
        })
    else:
        raise HTTPException(status_code=400, detail="Invalid command")

@router.delete(
    "/{product_id}",
    summary="Delete Credit Product",
    response_model=CreditProductDeleteResponse,
    dependencies=[Depends(require("credit_product:delete"))]
)
def delete_credit_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_product:delete"))
):
    """Permanently deletes a Credit Product and all its associated configurations."""
    result = CreditProductService.delete_product(db, product_id)
    result["product_id"] = str(result["product_id"])
    return envelope_success(result)
