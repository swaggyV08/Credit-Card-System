"""
User-facing Credit Product endpoints.

Allows authenticated USERs to browse only ACTIVE credit products.
Admin endpoints remain in app/admin/api/credit_product.py.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

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

router = APIRouter(prefix="/credit-products", tags=["Credit Products: User"])


@router.get(
    "/catalog",
    summary="Browse Active Credit Products",
    description="""
Returns a paginated list of **ACTIVE** credit products available for application.

Only products that have been approved and are currently active are shown.
Non-active products (DRAFT, SUSPENDED, CLOSED, REJECTED) are explicitly excluded.
""",
    dependencies=[Depends(require("credit_product:user_read"))],
)
def list_active_credit_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_product:user_read")),
):
    """List active credit products for user browsing."""
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


@router.get(
    "/catalog/{product_id}",
    summary="Get Active Credit Product Details",
    description="""
Returns full details for a single **ACTIVE** credit product.

If the product is not ACTIVE, a 404 error is returned.
""",
    dependencies=[Depends(require("credit_product:user_read"))],
)
def get_active_credit_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("credit_product:user_read")),
):
    """Get details of a single active credit product."""
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

    payload = CreditProductResponse.model_validate(product)
    return envelope_success(payload.model_dump(mode="json"))
