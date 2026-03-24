from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from typing import List, Optional
from app.api.deps import get_db, get_current_admin_user
from app.models.auth import User
from app.models.enums import ProductStatus
from app.admin.schemas.card_product import (
    CardProductCreate, CardProductResponse, CardProductUpdate, 
    CardProductCreateResponse, CardProductApprovalResponse,
    CardProductApprovalRequest, CardProductSummaryResponse
)
from app.admin.models.card_product import (
    CardProductCore, CardBillingConfiguration, CardTransactionControls,
    CardUsageLimits, CardRewardsConfiguration, CardAuthorizationRules,
    CardLifecycleRules, CardFraudRiskProfile, CardProductGovernance,
    CardFxConfiguration
)
from app.admin.models.credit_product import CreditProductInformation
from app.admin.services.card_product_svc import CardProductService

router = APIRouter(prefix="/card-products", tags=["Admin: Card Products"])

@router.post("/", response_model=CardProductCreateResponse, status_code=status.HTTP_201_CREATED)
def create_card_product(
    data: CardProductCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Creates a new Card Product linked to an existing Credit Product via `credit_product_code`, with full configuration (billing, transaction controls, FX, usage limits, rewards, authorization rules, lifecycle rules, fraud profile)."""
    credit_product = db.query(CreditProductInformation).filter(CreditProductInformation.product_code == data.credit_product_code).first()
    if not credit_product:
        raise HTTPException(status_code=404, detail="Credit Product not found")
        
    card = CardProductCore(
        credit_product_id=credit_product.id,
        card_network=data.card_network,
        card_bin_range=data.card_bin_range,
        card_branding_code=data.card_branding_code,
        card_form_factor=data.card_form_factor,
        card_variant=data.card_variant,
        default_card_currency=data.default_card_currency
    )
    db.add(card)
    db.flush() 

    db.add(CardBillingConfiguration(card_product_id=card.id, **data.billing_config.model_dump()))
    db.add(CardTransactionControls(card_product_id=card.id, **data.transaction_controls.model_dump()))
    db.add(CardFxConfiguration(card_product_id=card.id, **data.fx_configuration.model_dump()))
    db.add(CardUsageLimits(card_product_id=card.id, **data.usage_limits.model_dump()))
    db.add(CardRewardsConfiguration(card_product_id=card.id, **data.rewards_config.model_dump()))
    db.add(CardAuthorizationRules(card_product_id=card.id, **data.authorization_rules.model_dump()))
    db.add(CardLifecycleRules(card_product_id=card.id, **data.lifecycle_rules.model_dump()))
    db.add(CardFraudRiskProfile(card_product_id=card.id, **data.fraud_profile.model_dump()))
    
    gov = CardProductGovernance(
        card_product_id=card.id,
        created_by=admin.id
    )
    db.add(gov)
    
    db.commit()
    db.refresh(card)
    db.refresh(gov)
    
    return {
        "card_product_id": card.id,
        "credit_product_id": card.credit_product_id,
        "effective_from": gov.effective_from,
        "effective_to": gov.effective_to,
        "created_at": gov.created_at,
        "created_by": gov.created_by
    }

@router.get("/", response_model=List[CardProductSummaryResponse])
def get_all_card_products(
    status_filter: Optional[ProductStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Retrieves all Card Products with optional filtering by status. Status filter values: DRAFT, ACTIVE, SUSPENDED, CLOSED, REJECTED."""
    return CardProductService.get_all_cards(db, status=status_filter, skip=skip, limit=limit)

@router.get("/{card_product_id}", response_model=CardProductResponse)
def get_card_product(
    card_product_id: UUID, 
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Retrieves a single Card Product by its UUID, including all nested configurations (billing, transaction controls, FX, usage limits, rewards, authorization, lifecycle, fraud profile, governance)."""
    return CardProductService.get_card(db, card_product_id)

@router.post("/{card_product_id}", response_model=CardProductApprovalResponse)
def approve_card_product(
    card_product_id: UUID, 
    command: str,
    data: CardProductApprovalRequest = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Transitions a Card Product's lifecycle status via the `command` query parameter. Commands: `approve` (DRAFT → ACTIVE, makes the product eligible for card issuance, optional effective_to date)."""
    if command != "approve":
        raise HTTPException(status_code=400, detail="Invalid command")
    
    effective_to = None
    if data and data.effective_to:
        from datetime import datetime
        effective_to = datetime(data.effective_to.year, data.effective_to.month, data.effective_to.day)

    card = CardProductService.approve_card_product(db, card_product_id, admin.id, effective_to)
    gov = card.governance
    
    return {
        "card_product_id": card.id,
        "credit_product_id": card.credit_product_id,
        "effective_from": gov.effective_from,
        "effective_to": gov.effective_to,
        "created_at": gov.created_at,
        "created_by": gov.created_by,
        "approved_by": gov.approved_by
    }

@router.delete("/{card_product_id}")
def delete_card_product(
    card_product_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Permanently deletes a Card Product and all its associated configurations (billing, transaction controls, FX, usage limits, rewards, authorization, lifecycle, fraud profile, governance)."""
    return CardProductService.delete_card_product(db, card_product_id)
