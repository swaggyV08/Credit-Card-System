from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.models.enums import ProductStatus
from app.admin.schemas.card_product import (
    CardProductCreate, 
    CardProductApprovalRequest
)
from app.admin.models.card_product import (
    CardProductCore, CardBillingConfiguration, CardTransactionControls,
    CardUsageLimits, CardRewardsConfiguration, CardAuthorizationRules,
    CardLifecycleRules, CardFraudRiskProfile, CardProductGovernance,
    CardFxConfiguration
)
from app.admin.models.credit_product import CreditProductInformation
from app.admin.services.card_product_svc import CardProductService

router = APIRouter(prefix="/card-products", tags=["Card Products"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_card_product(
    data: CardProductCreate,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:create"))
):
    """Creates a new Card Product linked to an existing Credit Product."""
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
        created_by=principal.user_id
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

@router.get("/")
def get_card_products(
    command: str = Query("all", description="Command: 'all' to list, 'by_id' requiring card_product_id"),
    card_product_id: Optional[UUID] = None,
    status_filter: Optional[ProductStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:read"))
):
    """Retrieves Card Products using a unified command interface (all | by_id)."""
    if command == "by_id":
        if not card_product_id:
            raise HTTPException(status_code=400, detail="card_product_id is required when command is by_id")
        result = CardProductService.get_card(db, card_product_id)
        if not result:
            raise HTTPException(status_code=404, detail="Card Product not found")
        # Ensure conversion to dict using Pydantic's model_dump if it's a Pydantic model
        result_dict = result.model_dump(mode='json') if hasattr(result, 'model_dump') else result
        return envelope_success(result_dict)
    
    elif command == "all":
        results = CardProductService.get_all_cards(db, status=status_filter, skip=skip, limit=limit)
        results_list = [r.model_dump(mode='json') if hasattr(r, 'model_dump') else r for r in results]
        return envelope_success(results_list)
    else:
        raise HTTPException(status_code=400, detail="Invalid command. Use 'all' or 'by_id'.")

@router.post("/{card_product_id}")
def approve_card_product(
    card_product_id: UUID, 
    command: str,
    data: Optional[CardProductApprovalRequest] = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:approve"))
):
    """Transitions a Card Product's lifecycle status via the `command` query parameter. Commands: `approve`."""
    if command != "approve":
        raise HTTPException(status_code=400, detail="Invalid command. Currently only 'approve' is supported.")
    
    effective_to = None
    if data and data.effective_to:
        from datetime import datetime
        effective_to = datetime(data.effective_to.year, data.effective_to.month, data.effective_to.day)

    card = CardProductService.approve_card_product(db, card_product_id, principal.user_id, effective_to)
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
