from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.api.deps import get_async_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.engine_schemas import (
    GenerateBillReq,
    GenerateBillResp,
    PaginatedBillResp,
    BillDetailResp
)
from app.services.billing_engine import BillingEngine

router = APIRouter(tags=["Billing"])

from fastapi import APIRouter, Depends, Query, Path

@router.post(
    "/credit-account/{credit_account_id}/bill/{cycle_end}",
    response_model=GenerateBillResp,
    status_code=201,
    summary="Generate Bill",
    description="""
FUNCTIONALITY:
Generates monthly Bill records for a specific credit account. Applies interest computationally if the previous billing statement was not successfully resolved in full. Resolves minimum due calculations simultaneously.

ROLES THAT CAN ACCESS THE ENDPOINT:
- ADMIN
- SUPERADMIN

MATH FORMULA:
foreign_fee = amount × 0.03 (if applicable cross-border)
new_charges = Σ CLEARED tx.amount + Σ CLEARED tx.foreign_fee
daily_rate = APR / 365
interest = prev_balance × daily_rate × days_in_cycle
total_due = new_charges + interest + other_fees - credits
min_due = max(25.00, 0.02 × total_due) + past_due_amount

LOGIC AND NECESSITY OF THE ENDPOINT:
Fundamental for the monthly financial accounting workflows ensuring correct statement compilation for user visibility. Enforces single generation per cycle ensuring no duplicate balance compounding occurs.
"""
)
async def generate_bill(
    credit_account_id: str,
    cycle_end: str = Path(..., openapi_examples={"default": {"value": "2026-04-30"}}, description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("admin:all"))
):
    result = await BillingEngine.generate_bill(db, credit_account_id, cycle_end)
    return result


@router.get(
    "/cards/{card_id}/bills",
    response_model=PaginatedBillResp,
    status_code=200,
    summary="List Bills",
    description="""
FUNCTIONALITY:
Fetches historically generated bills strictly mapped to an associated card.

ROLES THAT CAN ACCESS THE ENDPOINT:
- USER (own card)
- ADMIN

MATH FORMULA: N/A

LOGIC AND NECESSITY OF THE ENDPOINT:
Provides standard bill fetching endpoints natively supporting pagination logic and limiting queries securely on indexed relationships.
"""
)
async def list_bills(
    card_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("billing:read"))
):
    result = await BillingEngine.list_bills(db, card_id, principal.user_id, page, limit, status)
    return result


@router.get(
    "/bills/{bill_id}",
    response_model=BillDetailResp,
    status_code=200,
    summary="Get Bill Detail",
    description="""
FUNCTIONALITY:
Fully unpacks a generated Bill surfacing raw transaction line items and corresponding payments matched during the previous resolution block. 

ROLES THAT CAN ACCESS THE ENDPOINT:
- USER
- ADMIN

MATH FORMULA: N/A

LOGIC AND NECESSITY OF THE ENDPOINT:
Gives full detailed line-by-line granular verification so users have deep insights on their historical spending without requiring arbitrary table scans globally.
"""
)
async def get_bill_detail(
    bill_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("billing:read"))
):
    result = await BillingEngine.get_bill_detail(db, str(bill_id), principal.user_id)
    return result
