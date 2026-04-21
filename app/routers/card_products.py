from fastapi import APIRouter, Depends, status, Query, Path, Header
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, Literal, List
from datetime import datetime, timezone

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success, build_pagination
from app.schemas.responses import CardProductCreateResponse, CardProductApproveResponse, CardProductDeleteResponse, CardProductGetResponse, CardProductCatalogResponse
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

@router.post("", status_code=status.HTTP_201_CREATED, response_model=CardProductCreateResponse)
def create_card_product(
    data: CardProductCreate,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:create"))
):
    """
    Creates a new Card Product linked to an existing Credit Product.

    **What it does:**
    Provisions a full card product blueprint (billing config, transaction controls,
    usage limits, rewards, authorization rules, lifecycle rules, fraud profile, FX config)
    and links it to an existing Credit Product via its `credit_product_code`.
    The product is created in DRAFT status and requires separate approval.

    **Roles:** `card_product:create` (Admin / Super Admin only)
    """
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
    
    rewards_dump = data.rewards_config.model_dump()
    if rewards_dump.get("merchant_category_bonus"):
        rewards_dump["merchant_category_bonus"] = {
            k: float(v) for k, v in rewards_dump["merchant_category_bonus"].items()
        }
    db.add(CardRewardsConfiguration(card_product_id=card.id, **rewards_dump))
    
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
        "effective_from": gov.effective_from.isoformat() if gov.effective_from else None,
        "effective_to": gov.effective_to.isoformat() if gov.effective_to else None,
        "created_at": gov.created_at.isoformat() if gov.created_at else None,
        "created_by": str(gov.created_by) if gov.created_by else None
    })

@router.get(
    "",
    summary="Get Card Products",
    description="""
**Unified endpoint to retrieve card products.**

### Commands
- `command=all` — Returns a paginated list of card products with optional status filtering.
- `command=by_id` — Returns full details of a single card product (requires `card_product_id` header).

### Query Parameters
- `status_filter`: `DRAFT` | `ACTIVE` | `SUSPENDED` | `CLOSED` | `REJECTED`
- `page`, `page_size`: Pagination controls
- `sort_by`, `sort_order`: Sorting controls

### Example Success Response (command=all)
```json
{
  "status": "success",
  "data": {
    "items": [
      {
        "card_product_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "credit_product_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "card_network": "VISA",
        "card_variant": "PLATINUM",
        "status": "ACTIVE"
      }
    ],
    "pagination": {
      "total": 1,
      "page": 1,
      "page_size": 20,
      "total_pages": 1
    }
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-08T10:30:00.000000+00:00",
    "api_version": "1.0.0"
  },
  "errors": []
}
```

**Roles:** `card_product:read` (Admin / Manager / SuperAdmin)
""",
    dependencies=[Depends(require("card_product:read"))],
    response_model=CardProductGetResponse
)
def get_card_products(
    command: Literal["all", "by_id"] = Query(..., description="Action to perform"),
    card_product_id: Optional[UUID] = Header(None, alias="card-product-id", description="Required for command=by_id"),
    status_filter: Optional[Literal["DRAFT","ACTIVE","SUSPENDED","CLOSED","REJECTED"]] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Optional[str] = Query("id"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:read"))
):
    if command == "by_id":
        if not card_product_id:
            raise AppError(code="MISSING_CARD_PRODUCT_ID", message="card-product-id header is required for command=by_id", http_status=422)
        
        card = CardProductService.get_card(db, card_product_id)
        from app.admin.schemas.card_product import CardProductResponse
        payload = CardProductResponse.model_validate(card)
        return envelope_success(payload.model_dump(mode='json'))

    elif command == "all":
        results = CardProductService.get_all_cards(
            db, 
            status=status_filter, 
            skip=(page - 1) * page_size, 
            limit=page_size
        )
        total = CardProductService.count_all_cards(db, status=status_filter)
        
        items = [CardProductSummaryResponse.model_validate(r).model_dump(mode='json') for r in results]
        
        return envelope_success({
            "items": items,
            "pagination": build_pagination(total, page, page_size)
        })

@router.post(
    "/{card_product_id}",
    summary="Manage Card Product",
    description="""
**Transitions a Card Product's lifecycle status via the `command` query parameter.**

### Commands
- `approve`: DRAFT → ACTIVE (sets effective dates and approver)
- `reject`: DRAFT → REJECTED (requires `rejection_reason` in body)
- `suspend`: ACTIVE → SUSPENDED (body fields can be null)

### Request Body
```json
{
  "effective_to": "2027-04-08",
  "rejection_reason": "string"
}
```

### Example Success Response
```json
{
  "status": "success",
  "data": {
    "card_product_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "effective_from": "2026-04-08T10:30:00+00:00",
    "effective_to": "2027-04-08T10:30:00+00:00",
    "created_at": "2026-04-08T10:30:00+00:00",
    "created_by": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "approved_by": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-08T10:30:00.000000+00:00",
    "api_version": "1.0.0"
  },
  "errors": []
}
```

**Roles:** `card_product:approve` (Manager only)
""",
    response_model=CardProductApproveResponse
)
def manage_card_product(
    card_product_id: UUID, 
    command: Literal["approve", "reject", "suspend"] = Query(..., description="Action to perform"),
    data: Optional[CardProductApprovalRequest] = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:approve"))
):
    admin_id = UUID(principal.user_id)
    
    if command == "approve":
        effective_to = None
        if data and data.effective_to:
            effective_to = datetime(data.effective_to.year, data.effective_to.month, data.effective_to.day, tzinfo=timezone.utc)
        card = CardProductService.approve_card_product(db, card_product_id, admin_id, effective_to)
    
    elif command == "reject":
        if not data or not data.reject_reason:
            raise AppError(code="MISSING_REJECTION_REASON", message="rejection_reason is mandatory for command=reject", http_status=422)
        card = CardProductService.reject_card_product(db, card_product_id, data.reject_reason, admin_id)
        
    elif command == "suspend":
        card = CardProductService.suspend_card_product(db, card_product_id, admin_id)

    gov = card.governance
    
    return envelope_success({
        "card_product_id": str(card.id),
        "effective_from": gov.effective_from.isoformat() if gov.effective_from else None,
        "effective_to": gov.effective_to.isoformat() if gov.effective_to else None,
        "created_at": gov.created_at.isoformat() if gov.created_at else None,
        "created_by": str(gov.created_by) if gov.created_by else None,
        "approved_by": str(gov.approved_by) if gov.approved_by else None
    })

@router.delete("/{card_product_id}", response_model=CardProductDeleteResponse)
def delete_card_product(
    card_product_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:delete"))
):
    """Permanently deletes a Card Product and all its associated configurations."""
    CardProductService.delete_card_product(db, card_product_id)
    return envelope_success({"message": "Card Product permanently deleted"})


# ===================================================================
# USER-FACING UNIFIED CATALOG ENDPOINT
# ===================================================================

@router.get(
    "/catalog",
    summary="Browse Active Card Products (User)",
    description="""
**Unified endpoint for users to browse ACTIVE card products.**

### Commands
- `command=all` — Returns a paginated list of all ACTIVE card products.
- `command=by_id` — Returns details for a single ACTIVE card product (requires `card_product_id` header).

### Example Success Response (command=all)
```json
{
  "status": "success",
  "data": {
    "items": [
      {
        "card_product_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "credit_product_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "card_network": "VISA",
        "card_variant": "PLATINUM",
        "status": "ACTIVE"
      }
    ],
    "pagination": {
      "total": 1,
      "page": 1,
      "page_size": 10,
      "total_pages": 1
    }
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-08T10:30:00.000000+00:00",
    "api_version": "1.0.0"
  },
  "errors": []
}
```

**Roles:** `card_product:user_read` (User)
""",
    dependencies=[Depends(require("card_product:user_read"))],
    response_model=CardProductCatalogResponse,
    response_model_exclude_none=True
)
def browse_active_card_products(
    command: Literal["all", "by_id"] = Query(..., description="Action to perform"),
    card_product_id: Optional[UUID] = Header(None, convert_underscores=False, description="Required for command=by_id"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card_product:user_read")),
):
    from app.admin.models.card_product import CardProductGovernance as CPG

    if command == "by_id":
        if not card_product_id:
            raise AppError(code="MISSING_CARD_PRODUCT_ID", message="card_product_id header is required for command=by_id", http_status=422)
        
        card = (
            db.query(CardProductCore)
            .join(CPG)
            .filter(
                CardProductCore.id == card_product_id,
                CPG.status == ProductStatus.ACTIVE,
            )
            .first()
        )
        if not card:
            raise AppError(code="NOT_FOUND", message="Card product not found or not currently available", http_status=404)
        
        from app.admin.schemas.card_product import CardProductResponse
        admin_payload = CardProductResponse.model_validate(card)
        
        payload_dict = {
            "card_product_id": str(card.id),
            "credit_product_id": str(card.credit_product_id),
            "card_network": card.card_network.value if hasattr(card.card_network, 'value') else str(card.card_network),
            "card_variant": card.card_variant.value if hasattr(card.card_variant, 'value') else str(card.card_variant),
            "status": "ACTIVE",
            "details": {
                "card_bin_range": card.card_bin_range,
                "card_branding_code": card.card_branding_code,
                "card_form_factor": card.card_form_factor.value if hasattr(card.card_form_factor, 'value') else str(card.card_form_factor),
            },
            "config": {
                "billing": admin_payload.billing_config.model_dump(mode="json") if admin_payload.billing_config else None,
                "transaction": admin_payload.transaction_controls.model_dump(mode="json") if admin_payload.transaction_controls else None,
                "limits": admin_payload.usage_limits.model_dump(mode="json") if admin_payload.usage_limits else None,
                "rewards": admin_payload.rewards_config.model_dump(mode="json") if admin_payload.rewards_config else None,
                "auth_rules": admin_payload.authorization_rules.model_dump(mode="json") if admin_payload.authorization_rules else None,
                "lifecycle": admin_payload.lifecycle_rules.model_dump(mode="json") if admin_payload.lifecycle_rules else None,
                "fraud_profile": admin_payload.fraud_profile.model_dump(mode="json") if admin_payload.fraud_profile else None,
                "fx": admin_payload.fx_configuration.model_dump(mode="json") if admin_payload.fx_configuration else None,
            }
        }
        return envelope_success(payload_dict)

    elif command == "all":
        query = (
            db.query(CardProductCore)
            .join(CPG)
            .filter(CPG.status == ProductStatus.ACTIVE)
        )

        total = query.count()
        results = query.offset((page - 1) * limit).limit(limit).all()

        items = [CardProductSummaryResponse.model_validate(r).model_dump(mode="json") for r in results]

        return envelope_success({
            "items": items,
            "pagination": build_pagination(total, page, limit),
        })
