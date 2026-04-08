from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.schemas.responses import DisputeCreateResponse

from app.models.transactions.disputes import Dispute, DisputeEvidence
from app.models.transactions.enums import DisputeStatus
from app.services.transactions.transaction_service import DisputeService
from app.schemas.transactions.transactions import (
    CreateDisputeRequest, DisputeCommandRequest, DisputeDetailSchema
)
from app.core.exceptions import (
    EvidenceDeadlinePassedError, ResolutionRequiredError,
)
from datetime import datetime, timezone

router = APIRouter(tags=["Disputes"])

@router.post("/transactions/{txn_id}/disputes", status_code=201, response_model=DisputeCreateResponse)
def create_dispute(
    txn_id: UUID,
    request: CreateDisputeRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("dispute:raise"))
):
    """
    Raise a dispute against a transaction.

    **What it does:**
    Opens a formal dispute case against an existing transaction. Creates a case number,
    sets an evidence submission deadline, and optionally issues provisional credit
    to the cardholder while the investigation is pending.

    **Request Body (`CreateDisputeRequest`):**
    - `dispute_type` enum: `UNAUTHORIZED` | `DUPLICATE_CHARGE` | `GOODS_NOT_RECEIVED` | `QUALITY_ISSUE` | `PROCESSING_ERROR` | `SUBSCRIPTION_CANCEL` | `FRAUD`
    - `description`: Detailed dispute explanation (min 20 characters)
    - `transaction_amount_disputed`: Decimal > 0
    - `supporting_documents`: Optional list of document reference strings
    - `request_provisional_credit`: Boolean (default: true)

    **Roles:** `dispute:raise` (User / Admin)

    **Response:** `{ dispute_id, case_number, status, provisional_credit_issued, deadline, next_steps }`
    """
    result = DisputeService.create_dispute(db, txn_id, request, actor_id=principal.user_id)
    return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)



@router.put("/disputes/{dispute_id}")
def transition_dispute(
    dispute_id: UUID,
    command: str = Query(..., description="submit_evidence | escalate | resolve | withdraw"),
    body: DisputeCommandRequest = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("dispute:manage"))
):
    """
    Unified dispute transition state machine.

    **What it does:**
    Processes dispute lifecycle actions. Validates evidence deadlines, manages
    status transitions, and triggers resolution logic (credit reversal or confirmation).

    **Query Parameter `command`:**
    - `submit_evidence` — Uploads documents and moves status to `UNDER_REVIEW`. Checks evidence deadline.
    - `escalate` — Escalates to card network (Visa/Mastercard). Moves status to `ESCALATED`.
    - `resolve` — Resolves the dispute. Requires `resolution` in body. Final status: `RESOLVED_WON` or `RESOLVED_LOST`.
    - `withdraw` — Cardholder withdraws the dispute. Status: `WITHDRAWN`.

    **Request Body (`DisputeCommandRequest`):**
    - `resolution`: String (required for `resolve` command)
    - `documents`: List of document references (for `submit_evidence`)
    - `statement`: Written statement (for `submit_evidence`)

    **Dispute Status enum:** `OPENED` | `UNDER_REVIEW` | `RESOLVED_WON` | `RESOLVED_LOST` | `ESCALATED` | `WITHDRAWN`

    **Roles:** `dispute:manage` (Admin / Super Admin only)

    **Response:** Updated `DisputeDetailSchema`.
    """
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    body = body or DisputeCommandRequest()

    # 1. Validation: Evidence Deadline check
    if command == "submit_evidence":
        if dispute.deadline and datetime.now(timezone.utc) > dispute.deadline:
            raise EvidenceDeadlinePassedError()

        if body.documents:
            for doc in body.documents:
                evidence = DisputeEvidence(
                    dispute_id=dispute.id, submitted_by=str(principal.user_id),
                    document_s3_key=doc, statement=body.statement,
                )
                db.add(evidence)
        # Update status to UNDER_REVIEW
        dispute.status = DisputeStatus.UNDER_REVIEW.value
        db.commit()
        db.refresh(dispute)
    elif command == "escalate":
        dispute.status = DisputeStatus.ESCALATED.value
        db.commit()
        db.refresh(dispute)
    elif command == "resolve":
        if not body.resolution:
            raise ResolutionRequiredError()
        dispute = DisputeService.resolve_dispute(db, dispute, body.resolution, actor_id=principal.user_id)
    elif command == "withdraw":
        # 'withdraw' corresponds to a user action, so anyone with dispute:raise or manage can theoretically hit this
        # Assuming the caller has appropriate access via principal
        dispute = DisputeService.withdraw_dispute(db, dispute, actor_id=principal.user_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'")

    data = DisputeDetailSchema.model_validate(dispute).model_dump(mode='json')
    return envelope_success(data)
