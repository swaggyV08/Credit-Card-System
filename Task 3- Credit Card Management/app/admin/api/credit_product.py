from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
import uuid
import random
from typing import List, Optional
from datetime import datetime, timezone
from app.models.enums import ProductStatus

from app.api.deps import get_db, get_current_admin_user
from app.models.auth import User
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


@router.post("/", response_model=CreditProductCreateResponse, status_code=status.HTTP_201_CREATED)
def create_credit_product(
    data: CreditProductCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Creates a new Credit Product in DRAFT status with its full configuration.
    
    **Exactly why we are implementing this**:
    Administrative users need a workbench to define financial guardrails (limits, APR, fees) before a product 
    is made live for customers. DRAFT status allows for multi-stage setup and compliance review.
    """
    while True:
        product_code = f"CP-{random.randint(10000, 99999)}"
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
    db.add(CreditProductAccountingMapping(credit_product_id=product.id, **data.accounting_mapping.model_dump()))
    
    db.add(CreditProductGovernance(
        credit_product_id=product.id,
        auto_renewal_allowed=data.auto_renewal_allowed,
        cooling_period_days=data.cooling_period_days,
        created_by=admin.id
    ))
    
    db.commit()
    db.refresh(product)
    return product

@router.get("/", response_model=List[CreditProductSummaryResponse])
def get_all_credit_products(
    status_filter: Optional[ProductStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Retrieves all Credit Products with optional filtering by status.
    
    **Exactly why we are implementing this**:
    Provides an overview of the product catalog. Status filtering is critical for monitoring 
    active vs suspended products and managing the lifecycle of financial offerings.
    """
    return CreditProductService.get_all_products(db, status=status_filter, skip=skip, limit=limit)

@router.get("/{product_id}", response_model=CreditProductResponse)
def get_credit_product(
    product_id: UUID, 
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Retrieves a single Credit Product by its UUID, including all nested configurations (limits, interest, fees, eligibility, compliance, accounting, governance)."""
    return CreditProductService.get_product(db, product_id)

@router.post("/{product_id}", response_model=CreditProductStatusUpdateResponse)
def update_credit_product_status(
    product_id: UUID,
    command: str,
    data: Optional[CreditProductApprovalRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
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
            effective_to_dt = datetime(
                year=data.effective_to.year,
                month=data.effective_to.month,
                day=data.effective_to.day,
                tzinfo=timezone.utc
            )
        
        product = CreditProductService.approve_product(db, product_id, admin.id, effective_to_dt)
        return {
            "message": "Credit Product approved",
            "product_id": product.id,
            "product_code": product.product_code,
            "product_name": product.product_name
        }
    elif command == "reject":
        reason = data.reject_reason if data else None
        product = CreditProductService.reject_product(db, product_id, admin.id, reason)
        return {
            "message": "Credit Product rejected",
            "product_id": product.id,
            "product_code": product.product_code,
            "product_name": product.product_name,
            "reject_reason": reason
        }
    elif command == "suspend":
        product = CreditProductService.suspend_product(db, product_id, admin.id)
        return {
            "message": "Credit Product suspended",
            "product_id": product.id,
            "product_code": product.product_code,
            "product_name": product.product_name
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid command")

@router.delete("/{product_id}")
def delete_credit_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Permanently deletes a Credit Product and all its associated configurations (limits, interest, fees, eligibility, compliance, accounting, governance)."""
    return CreditProductService.delete_product(db, product_id)
