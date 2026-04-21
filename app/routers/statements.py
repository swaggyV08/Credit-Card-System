from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_async_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.engine_schemas import (
    GenerateStatementResp,
    PaginatedStatementResp
)
from app.services.billing_engine import StatementEngine

router = APIRouter(tags=["Statements"])

@router.post(
    "/cards/{card_id}/statements/{billing_cycle}",
    response_model=GenerateStatementResp,
    status_code=201,
    summary="Generate Statement",
    description="""
FUNCTIONALITY:
Admins can manually kick off or regenerate the monthly transaction statement for a specific card cycle in YYYY-MM format.

ROLES THAT CAN ACCESS THE ENDPOINT:
- ADMIN
- SUPERADMIN

MATH FORMULA:
total_charges = SUM(transactions)
total_due = total_charges + interest + fees

LOGIC AND NECESSITY OF THE ENDPOINT:
Required for statement rendering interfaces securely isolating generation loops to admins.
"""
)
async def generate_statement(
    card_id: str,
    billing_cycle: str,
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("admin:all"))
):
    result = await StatementEngine.generate(
        db=db,
        credit_card_id=card_id,
        billing_cycle=billing_cycle
    )
    return result


@router.get(
    "/cards/{card_id}/statements",
    response_model=PaginatedStatementResp,
    status_code=200,
    summary="Fetch Statements",
    description="""
FUNCTIONALITY:
Lists historically generated statements for the assigned card.

ROLES THAT CAN ACCESS THE ENDPOINT:
- USER (own card only)

MATH FORMULA: N/A

LOGIC AND NECESSITY OF THE ENDPOINT:
Allows the consumer application to cleanly list statement summaries without pulling massive transaction payloads.
"""
)
async def fetch_statements(
    card_id: str,
    cycle: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("statement:read"))
):
    result = await StatementEngine.fetch(
        db=db,
        credit_card_id=card_id,
        user_id=principal.user_id,
        cycle=cycle,
        page=page,
        limit=limit
    )
    return result
