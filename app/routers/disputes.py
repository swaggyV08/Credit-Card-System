from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.models.transactions.disputes import Dispute, DisputeEvidence
from app.models.transactions.enums import DisputeStatus
from app.services.transactions.transaction_service import DisputeService
from app.core.exceptions import (
    EvidenceDeadlinePassedError, ResolutionRequiredError,
)
from datetime import datetime, timezone

router = APIRouter(tags=["Disputes"])

@router.post("/transactions/{txn_id}/disputes", status_code=201)
def create_dispute(
    txn_id: UUID,
    request: CreateDisputeRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("dispute:raise"))
):
    """Raise a dispute against a transaction."""
    result = DisputeService.create_dispute(db, txn_id, request, actor_id=principal.user_id)
    return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)



@router.patch("/disputes/{dispute_id}")
def transition_dispute(
    dispute_id: UUID,
    command: str = Query(..., description="submit_evidence | escalate | resolve | withdraw"),
    body: DisputeCommandRequest = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("dispute:manage"))
):
    """Unified dispute transition state machine."""
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
