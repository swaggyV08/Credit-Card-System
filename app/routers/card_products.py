from fastapi import APIRouter, Depends, status, Query, Path
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, Literal, List
from datetime import datetime, timezone

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success, build_pagination
from app.models.enums import ProductStatus
from app.admin.schemas.card_product import (
    CardProductCreate, 
    CardProductApprovalRequest
)
from app.schemas.card_product import CardProductSummaryResponse
from app.admin.models.card_product import (
    CardProductCore, CardBillingConfiguration, CardTransactionControls,
    CardUsageLimits, CardRewardsConfiguration, CardAuthorizationRules,
    CardLifecycleRules, CardFraudRiskProfile, CardProductGovernance,
    CardFxConfiguration
)
from app.admin.models.credit_product import CreditProductInformation
from app.admin.services.card_product_svc import CardProductService
from app.core.app_error import AppError

router = APIRouter(prefix="/card-products", tags=["Card Products"])

@router.post("", status_code=status.HTTP_201_CREATED)
def create_card_product(
    data: CardProductCreate,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:create"))
):
    """Creates a new Card Product linked to an existing Credit Product."""
    credit_product = db.query(CreditProductInformation).filter(CreditProductInformation.product_code == data.credit_product_code).first()
    if not credit_product:
        raise AppError(code="NOT_FOUND", message="Credit Product not found", http_status=404)
        
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
        created_by=UUID(principal.user_id)
    )
    db.add(gov)
    
    db.commit()
    db.refresh(card)
    db.refresh(gov)
    
    return envelope_success({
        "card_product_id": str(card.id),
        "credit_product_id": str(card.credit_product_id),
        "effective_from": gov.effective_from.isoformat() if gov.effective_from else None,
        "effective_to": gov.effective_to.isoformat() if gov.effective_to else None,
        "created_at": gov.created_at.isoformat() if gov.created_at else None,
        "created_by": gov.created_by
    })

@router.get("")
def list_card_products(
    status_filter: Optional[Literal["DRAFT","ACTIVE","SUSPENDED","CLOSED","REJECTED"]] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:read"))
):
    """
    Retrieves all available Card Products with pagination.
    Supports filtering by lifecycle status.
    """
    results = CardProductService.get_all_cards(
        db, 
        status=status_filter, 
        skip=(page - 1) * limit, 
        limit=limit
    )
    total = CardProductService.count_all_cards(db, status=status_filter)
    
    # Map to schema
    items = [CardProductSummaryResponse.model_validate(r) for r in results]
    
    return envelope_success({
        "items": items,
        "pagination": build_pagination(total, page, limit)
    })

@router.post("/{card_product_id}")
def approve_card_product(
    card_product_id: UUID, 
    command: str = Query(..., description="Action: 'approve'"),
    data: Optional[CardProductApprovalRequest] = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:approve"))
):
    """Transitions a Card Product's lifecycle status via the `command` query parameter. Commands: `approve`."""
    if command != "approve":
        raise AppError(code="INVALID_COMMAND", message="Invalid command. Currently only 'approve' is supported.", http_status=400)
    
    effective_to = None
    if data and data.effective_to:
        effective_to = datetime(data.effective_to.year, data.effective_to.month, data.effective_to.day, tzinfo=timezone.utc)

    card = CardProductService.approve_card_product(db, card_product_id, UUID(principal.user_id), effective_to)
    gov = card.governance
    
    return envelope_success({
        "card_product_id": str(card.id),
        "credit_product_id": str(card.credit_product_id),
        "effective_from": gov.effective_from.isoformat() if gov.effective_from else None,
        "effective_to": gov.effective_to.isoformat() if gov.effective_to else None,
        "created_at": gov.created_at.isoformat() if gov.created_at else None,
        "created_by": gov.created_by,
        "approved_by": gov.approved_by
    })

@router.delete("/{card_product_id}")
def delete_card_product(
    card_product_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:delete"))
):
    """Permanently deletes a Card Product and all its associated configurations."""
    CardProductService.delete_card_product(db, card_product_id)
    return envelope_success({"message": "Card Product permanently deleted"})

