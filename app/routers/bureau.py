import uuid
from datetime import datetime, timezone, date as py_date
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require, AuthenticatedPrincipal
from app.core.roles import Role
from app.core.app_error import AppError
from app.core.redis import redis_service
from app.db.session import get_async_db
from app.models.auth import User
from app.models.bureau import BureauScore
from app.models.enums import BureauRiskBand, ScoreTrigger
from app.schemas.base import envelope_success, ResponseEnvelope, ErrorDetail
from app.schemas.bureau import (
    BureauScoreResponse, 
    BureauHistoryResponse, 
    BureauSnapshotResponse,
    FactorDetail
)
from app.services.bureau_service import compute_bureau_score, classify_band

router = APIRouter(prefix="/bureau")

INTERPRETATIONS = {
    BureauRiskBand.POOR: "A POOR score indicates significant credit risk. Credit applications are likely to be declined or offered at very high interest rates.",
    BureauRiskBand.FAIR: "A FAIR score indicates below-average creditworthiness. Some lenders may approve credit with higher rates or lower limits.",
    BureauRiskBand.GOOD: "A GOOD score indicates responsible credit usage. Most lenders will approve credit applications at standard rates.",
    BureauRiskBand.VERY_GOOD: "A VERY GOOD score indicates strong credit management. Lenders will typically offer competitive rates and higher limits.",
    BureauRiskBand.EXCELLENT: "An EXCELLENT score indicates exceptional credit management. Lenders will offer the best available rates and highest credit limits."
}

async def _verify_user_and_cif(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Common guard for user existence and CIF status (Phases 3 & 4 of guard sequence)."""
    user_res = await db.execute(select(User).where(User.id == str(user_id)))
    user = user_res.scalar()
    if not user:
        raise AppError(code="USER_NOT_FOUND", message="No user account found for the given user_id.", http_status=404)
    
    if not user.is_cif_completed:
        raise AppError(code="CIF_INCOMPLETE", message="Bureau score is only available after the Customer Information Form has been submitted.", http_status=400)
    
    return user

@router.get(
    "/score",
    response_model=ResponseEnvelope[BureauScoreResponse],
    summary="Get bureau score",
    tags=["Bureau Score"]
)
async def get_score(
    user_id: Optional[uuid.UUID] = Query(None, description="The user whose bureau score to retrieve. Required for admin roles. Ignored for USER role — the score returned is always for the authenticated user."),
    include_history: bool = Query(False, description="When true, includes the last 12 score snapshots in the response. Defaults to false."),
    principal: AuthenticatedPrincipal = Depends(require("bureau:read_own")),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves the most recently computed bureau score for a user.

    USER role: always retrieves the authenticated user's own score.
      The user_id query parameter is ignored for this role.

    SALES, MANAGER, ADMIN, SUPERADMIN: user_id query parameter is
      required. Returns the score for the specified user.

    The score ranges from 300 (lowest) to 900 (highest).
    Bands: POOR (300–549) | FAIR (550–649) | GOOD (650–749) |
           VERY_GOOD (750–849) | EXCELLENT (850–900)

    The response includes a full factor breakdown showing the exact
    contribution of each of the five scoring factors, along with the
    raw input values used in the calculation.

    Set include_history=true to receive the last 12 score snapshots,
    enabling trend analysis.

    The score is automatically recomputed after every settled
    transaction and every payment. Use the manual trigger endpoint
    (POST /bureau/score/trigger) to compute on demand.

    Error codes:
      MISSING_USER_ID       — admin role called without user_id
      USER_NOT_FOUND        — user_id does not exist
      CIF_INCOMPLETE        — user has not completed CIF submission
      SCORE_NOT_YET_COMPUTED — no score exists; trigger one first

    Accessible by: USER (own score), SALES, MANAGER, ADMIN, SUPERADMIN
    """
    # 1. principal already extracted by Depends(require)
    
    # 2. Role handling
    is_user_role = principal.role == Role.USER
    target_user_id = principal.user_id if is_user_role else user_id
    
    if not target_user_id:
        raise AppError(code="MISSING_USER_ID", message="user_id is required for admin roles.", http_status=400)

    # 3. UUID validity is handled by FastAPI type hint
    try:
        u_id = uuid.UUID(str(target_user_id))
    except (ValueError, AttributeError):
        raise AppError(code="INVALID_UUID", message="Malformed UUID in path or query parameter.", http_status=422)

    # 4 & 5. Verify user and CIF
    await _verify_user_and_cif(db, u_id)

    # 6. Fetch latest score
    stmt = select(BureauScore).where(BureauScore.user_id == u_id).order_by(desc(BureauScore.computed_at))
    result = await db.execute(stmt)
    latest = result.scalar()
    
    if not latest:
        raise AppError(code="SCORE_NOT_YET_COMPUTED", message="A bureau score has not yet been computed for this user. Complete a payment or transaction to trigger score generation, or use the manual trigger endpoint.", http_status=404)

    # Factor breakdown formatting
    factor_breakdown = {
        "payment_history": FactorDetail(
            score=latest.payment_history_score, max=350, weight_pct=35,
            inputs={"on_time_payments": latest.on_time_payment_count, "late_payments": latest.late_payment_count, "missed_payments": latest.missed_payment_count}
        ),
        "credit_utilisation": FactorDetail(
            score=latest.utilisation_score, max=300, weight_pct=30,
            inputs={"current_utilisation_pct": str(latest.current_utilisation_pct)}
        ),
        "credit_history": FactorDetail(
            score=latest.credit_history_score, max=150, weight_pct=15,
            inputs={"account_age_days": latest.account_age_days}
        ),
        "transaction_behaviour": FactorDetail(
            score=latest.transaction_behaviour_score, max=120, weight_pct=12,
            inputs={"transactions_last_90_days": latest.total_transactions_90d, "disputes_last_90_days": latest.disputes_90d}
        ),
        "derogatory_marks": FactorDetail(
            score=latest.derogatory_score, max=80, weight_pct=8,
            inputs={"chargebacks_all_time": latest.chargebacks_total, "over_limit_events": 1 if latest.utilisation_score == 0 and latest.current_utilisation_pct > 100 else 0}
        )
    }

    history = None
    if include_history:
        hist_stmt = select(BureauScore).where(BureauScore.user_id == u_id).order_by(desc(BureauScore.computed_at)).limit(12)
        hist_res = await db.execute(hist_stmt)
        rows = hist_res.scalars().all()
        # Delta calculation logic for snapshots
        history = []
        for i in range(len(rows)):
            delta = None
            if i < len(rows) - 1:
                delta = rows[i].score - rows[i+1].score
            history.append(BureauSnapshotResponse(
                score=rows[i].score, risk_band=rows[i].risk_band, trigger_event=rows[i].trigger_event,
                computed_at=rows[i].computed_at, delta=delta
            ))

    data = BureauScoreResponse(
        user_id=u_id, score=latest.score, risk_band=latest.risk_band,
        score_interpretation=INTERPRETATIONS.get(latest.risk_band, ""),
        computed_at=latest.computed_at, trigger_event=latest.trigger_event,
        factor_breakdown=factor_breakdown, history=history
    )
    return envelope_success(data.model_dump(mode='json'))

@router.post(
    "/score/trigger",
    status_code=201,
    summary="Manually trigger bureau score computation",
    tags=["Bureau Score"]
)
async def trigger_score(
    request: Request,
    user_id: uuid.UUID = Query(..., description="The user whose score to recompute."),
    principal: AuthenticatedPrincipal = Depends(require("bureau:trigger")),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Forces an immediate recomputation of the bureau score for the
    specified user. The result is persisted and returned in the response.

    The score is computed synchronously — the response contains the
    freshly computed score.

    Rate limit: 3 manual triggers per user per hour.
    Automatic triggers (from transactions and payments) do not count
    toward this limit.

    Input: user_id query parameter only. No request body accepted.

    Error codes:
      MISSING_USER_ID   — user_id not provided
      USER_NOT_FOUND    — user does not exist
      CIF_INCOMPLETE    — user has not submitted CIF
      TRIGGER_RATE_LIMIT — rate limit of 3/hour exceeded
      NO_BODY_ACCEPTED   — trigger endpoint received a body

    Accessible by: MANAGER, ADMIN, SUPERADMIN
    """
    # 0. NO_BODY_ACCEPTED enforcement
    body = await request.body()
    if body:
        raise AppError(code="NO_BODY_ACCEPTED", message="This endpoint does not accept a request body. Remove the body and try again.", http_status=422)

    # 4 & 5. Verify user and CIF
    await _verify_user_and_cif(db, user_id)

    # 6. Rate Limit
    redis = redis_service.get_client()
    if redis:
        key = f"bureau:trigger:{user_id}"
        count = redis.get(key)
        if count and int(count) >= 3:
            ttl = redis.ttl(key)
            raise HTTPException(
                status_code=429,
                detail={"code": "TRIGGER_RATE_LIMIT", "message": "Bureau score can only be manually triggered 3 times per hour per user. Please wait before triggering again.", "field": "user_id"},
                headers={"Retry-After": str(ttl)}
            )
        
        # Incremental logic
        if not count:
            redis.setex(key, 3600, 1)
        else:
            redis.incr(key)

    # 7. Call compute_bureau_score synchronously (awaited)
    new_score = await compute_bureau_score(
        user_id=user_id,
        trigger_event=ScoreTrigger.MANUAL_REQUEST,
        trigger_ref_id=None,
        computed_by=uuid.UUID(principal.user_id),
        db=db
    )

    return envelope_success({
        "user_id": user_id,
        "score": new_score.score,
        "risk_band": new_score.risk_band,
        "computed_at": new_score.computed_at.isoformat(),
        "trigger_event": new_score.trigger_event,
        "message": "Bureau score computed successfully."
    })

@router.get(
    "/score/history",
    response_model=ResponseEnvelope[BureauHistoryResponse],
    summary="Get bureau score history",
    tags=["Bureau Score"]
)
async def get_history(
    user_id: Optional[uuid.UUID] = Query(None, description="The user whose bureau history to retrieve. Required for admin roles."),
    limit: int = Query(default=12, ge=1, le=50),
    from_date: Optional[py_date] = Query(None),
    to_date: Optional[py_date] = Query(None),
    principal: AuthenticatedPrincipal = Depends(require("bureau:read_own")),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves score history for a user with trend analysis and date filters."""
    # 1. principal handles JWT
    
    # 2. Role handling
    is_user_role = principal.role == Role.USER
    u_id = uuid.UUID(principal.user_id) if is_user_role else user_id
    
    if not u_id:
        raise AppError(code="MISSING_USER_ID", message="user_id is required for admin roles.", http_status=400)

    # Date range validation
    if from_date and to_date and from_date > to_date:
        raise AppError(code="INVALID_DATE_RANGE", message="from_date must be earlier than or equal to to_date.", http_status=400)

    # 4 & 5. Verify user and CIF
    await _verify_user_and_cif(db, u_id)

    # Query snapshots
    filters = [BureauScore.user_id == u_id]
    if from_date:
        filters.append(BureauScore.computed_at >= datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc))
    if to_date:
        filters.append(BureauScore.computed_at <= datetime.combine(to_date, datetime.max.time(), tzinfo=timezone.utc))

    stmt = select(BureauScore).where(and_(*filters)).order_by(desc(BureauScore.computed_at)).limit(limit)
    res = await db.execute(stmt)
    rows = res.scalars().all()

    # snapshots list with delta
    snapshots = []
    # Note: to calc delta for oldest in result set, we'd need snapshot[i-1] which might not be in the result.
    # The spec says delta[i] = score[i] - score[i-1] (chronological i).
    # Since we have desc order: delta = current.score - next.score
    for i in range(len(rows)):
        delta = None
        if i < len(rows) - 1:
            delta = rows[i].score - rows[i+1].score
        snapshots.append(BureauSnapshotResponse(
            score=rows[i].score, risk_band=rows[i].risk_band, 
            trigger_event=rows[i].trigger_event, computed_at=rows[i].computed_at,
            delta=delta
        ))

    # Trend logic (last 3 snapshots)
    trend = "STABLE"
    if len(rows) >= 3:
        # Latest - 2nd oldest in this set
        diff = rows[0].score - rows[2].score
        if diff >= 20: trend = "IMPROVING"
        elif diff <= -20: trend = "DECLINING"

    history_data = BureauHistoryResponse(
        user_id=u_id,
        snapshots=snapshots,
        count=len(snapshots),
        oldest_snapshot_at=rows[-1].computed_at if rows else None,
        latest_score=rows[0].score if rows else None,
        latest_band=rows[0].risk_band if rows else None,
        score_trend=trend
    )
    return envelope_success(history_data.model_dump(mode='json'))
