"""
User-facing Credit Product endpoints.

Allows authenticated USERs to browse only ACTIVE credit products.
Admin endpoints remain in app/admin/api/credit_product.py.
"""
from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, Literal

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success, build_pagination
from app.core.app_error import AppError
from app.models.enums import ProductStatus
from app.admin.models.credit_product import CreditProductInformation
from app.admin.schemas.credit_product import (
    CreditProductSummaryResponse,
    CreditProductResponse,
)
from app.schemas.responses import CreditProductCatalogResponse

router = APIRouter(prefix="/credit-products", tags=["Credit Products: User"])


@router.get(
    "/catalog",
    summary="Browse Active Credit Products",
    description="""
**Unified endpoint for users to browse ACTIVE credit products.**

### Commands
- `command=all` — Returns a paginated list of all ACTIVE credit products.
- `command=by_id` — Returns full details for a single ACTIVE product (requires `product_id` header).

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
      "base_interest_rate": "36.000"
    },
    "fees": {
      "joining_fee": "500.000",
      "annual_fee": "1000.000"
    },
    "eligibility_rules": {
      "min_age": 18,
      "max_age": 70,
      "min_income_required": "300000.000",
      "min_credit_score": 750
    },
    "governance": {
      "effective_from": "2026-04-08T10:30:00+00:00",
      "created_at": "2026-04-08T10:30:00+00:00"
    }
  },
  "meta": { ... },
  "errors": []
}
```

**Roles:** `credit_product:user_read` (User)
""",
    dependencies=[Depends(require("credit_product:user_read"))],
    response_model=CreditProductCatalogResponse
)
def browse_active_credit_products(
    command: Literal["all", "by_id"] = Query(..., description="Action to perform"),
    product_id: Optional[UUID] = Header(None, alias="product-id", description="Required for command=by_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_product:user_read")),
):
    if command == "by_id":
        if not product_id:
            raise AppError(code="MISSING_PRODUCT_ID", message="product-id header is required for command=by_id", http_status=422)
        
        product = db.query(CreditProductInformation).filter(
            CreditProductInformation.id == product_id,
            CreditProductInformation.status == ProductStatus.ACTIVE,
        ).first()

        if not product:
            raise AppError(
                code="NOT_FOUND",
                message="Credit product not found or not currently available",
                http_status=404,
            )

        payload = CreditProductSummaryResponse.model_validate(product)
        return envelope_success(payload.model_dump(mode="json"))

    elif command == "all":
        query = db.query(CreditProductInformation).filter(
            CreditProductInformation.status == ProductStatus.ACTIVE
        )

        total = query.count()
        products = (
            query.order_by(CreditProductInformation.product_name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = [
            CreditProductSummaryResponse.model_validate(p).model_dump(mode="json")
            for p in products
        ]

        return envelope_success({
            "items": items,
            "pagination": build_pagination(total, page, page_size),
        })
