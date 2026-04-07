from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.models.transactions.settlement import SettlementRun
from app.schemas.transactions.transactions import CreateSettlementRequest, SettlementRunDetailSchema
from app.services.transactions.transaction_service import SettlementService
from app.core.exceptions import (
    InvalidSettlementDateError, InvalidNetworkError, SettlementAlreadyRunError,
)
from datetime import datetime, timezone, date as py_date

router = APIRouter(tags=["Settlement"])

@router.post("/settlements", status_code=201)
def run_settlement(
    request: CreateSettlementRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("settlement:run"))
):
    """
    Triggers the 8-step settlement logic for all cleared transactions.
    
    1. Cutoff verification
    2. Network-specific batch grouping
    3. Merchant balance allocation
    4. Fee recovery (Waterfall)
    5. Interest calculation
    6. Tax computation
    7. Ledger posting
    8. Confirmation generation
    """
    # 1. Validation: Future Date check
    if request.settlement_date > py_date.today():
        raise InvalidSettlementDateError()

    # 2. Validation: Network Enum (Pydantic handles base enum, but we double-check or catch)
    valid_networks = ["VISA", "MASTERCARD", "AMEX", "RUPAY"]
    if request.network.value not in valid_networks:
        raise InvalidNetworkError()

    # 3. Validation: Duplicate run check
    existing = db.query(SettlementRun).filter(
        SettlementRun.network == request.network.value,
        SettlementRun.settlement_date == request.settlement_date
    ).first()
    if existing:
        raise SettlementAlreadyRunError()

    result = SettlementService.run_settlement(db, request, actor_id=principal.user_id)
    return envelope_success(result if isinstance(result, dict) else result.model_dump(mode='json'))

# DELETE: GET /settlements/{settlement_run_id} removed as per directive.
