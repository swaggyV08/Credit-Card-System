import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.schemas.transactions.operations import FeeSchema, CreateFeeRequest, FeeWaiveRequest, InterestPostRequest
from app.services.transactions.operations_service import FeeService

router = APIRouter(tags=["Fees & Interest"])

@router.get("/cards/{card_id}/fees")
def list_fees(
    card_id: uuid.UUID,
    fee_type: str | None = None,
    waived: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:read"))
):
    """Returns all fee events applied to the card account with optional filters."""
    fees = FeeService.list_fees(db, card_id, fee_type, waived)
    total = len(fees)
    paginated = fees[(page - 1) * page_size : page * page_size]
    data = [FeeSchema.model_validate(f).model_dump(mode='json') for f in paginated]
    return envelope_success({
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size}
    })

@router.post("/cards/{card_id}/fees", status_code=201)
def manage_fee(
    card_id: uuid.UUID,
    command: str = Query(..., description="apply | waive"),
    apply_request: CreateFeeRequest = None,
    waive_request: FeeWaiveRequest = None,
    fee_id: uuid.UUID = Query(None, description="Required only when command=waive"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("fee:apply"))
):
    """
    Apply or waive a fee unified endpoint.
    - command=apply: Uses `apply_request` body.
    - command=waive: Uses `waive_request` body and requires `fee_id` query param.
    """
    if command == "apply":
        if not apply_request:
            raise HTTPException(status_code=422, detail="apply_request body is required for 'apply' command")
        fee = FeeService.apply_fee(db, card_id, apply_request, actor_id=principal.user_id)
        data = FeeSchema.model_validate(fee).model_dump(mode='json')
        return envelope_success(data)
        
    elif command == "waive":
        if not fee_id:
            raise HTTPException(status_code=422, detail="fee_id query param is required for 'waive' command")
        if not waive_request:
            raise HTTPException(status_code=422, detail="waive_request body is required for 'waive' command")
        
        fee = FeeService.waive_fee(db, fee_id, waive_request.waiver_reason, actor_id=principal.user_id)
        data = FeeSchema.model_validate(fee).model_dump(mode='json')
        return envelope_success(data)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'")

@router.post("/cards/{card_id}/interest", status_code=201)
def post_interest(
    card_id: uuid.UUID,
    request: InterestPostRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("fee:apply"))
):
    """System-only: calculates and posts monthly interest using DPR formula."""
    fee = FeeService.post_interest(db, card_id, request, actor_id=principal.user_id)
    data = FeeSchema.model_validate(fee).model_dump(mode='json')
    return envelope_success(data)
