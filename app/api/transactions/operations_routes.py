"""
Operations Routers — API endpoints for Groups 6–11.
Group 6: Statements
Group 7: Fees & Interest
Group 8: Payments
Group 9: Limits & Controls
Group 10: Fraud & Risk
Group 11: Reconciliation & Audit
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_authenticated_user
from app.models.transactions.transactions import TransactionAuditLog as AuditLog
from app.models.transactions.fees import Fee
from app.models.transactions.payments import Payment
from app.models.transactions.risk import RiskAlert
from app.models.transactions.statements import Statement
from app.schemas.transactions.envelope import success_response, paginated_response
from app.schemas.transactions.operations import (
    StatementSummarySchema, StatementDetailSchema, StatementLineItemSchema,
    CreateExportRequest, ExportJobResponse,
    FeeSchema, CreateFeeRequest, FeeWaiveRequest, InterestPostRequest,
    CreatePaymentRequest, PaymentSchema, PaymentCommandRequest,
    CardControlSchema, UpdateCardControlRequest,
    RiskAlertSchema, RiskAlertCommandRequest,
    AuditLogSchema,
)
from app.services.transactions.operations_service import (
    StatementService, FeeService, PaymentService,
    ControlsService, RiskService, ReconciliationService,
)


# =====================================================
# GROUP 6 — STATEMENTS
# =====================================================
stmt_router = APIRouter(prefix="/api/v1", tags=["Statements"])


@stmt_router.get(
    "/cards/{card_id}/statements",
    summary="List Statements",
    description="Lists all billing cycle statements for the card with optional year/month filter.",
)
def list_statements(
    card_id: uuid.UUID,
    year: int | None = None,
    month: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    stmts = StatementService.list_statements(db, card_id, year, month)
    total = len(stmts)
    paginated = stmts[(page - 1) * page_size : page * page_size]
    data = [StatementSummarySchema.model_validate(s).model_dump() for s in paginated]
    return paginated_response(data, total, page, page_size)


@stmt_router.get(
    "/cards/{card_id}/statements/{statement_id}",
    summary="Get Statement Detail",
    description="Full statement detail with all line-item transactions within the billing cycle.",
)
def get_statement(
    card_id: uuid.UUID,
    statement_id: uuid.UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    stmt = StatementService.get_statement_detail(db, statement_id)
    data = StatementDetailSchema.model_validate(stmt).model_dump()
    return success_response(data)


@stmt_router.post(
    "/cards/{card_id}/statements/{statement_id}/exports",
    status_code=202,
    summary="Export Statement",
    description="Triggers async PDF/CSV export of a statement. Poll via the returned `poll_url`.",
)
def export_statement(
    card_id: uuid.UUID,
    statement_id: uuid.UUID,
    request: CreateExportRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    export_job_id = uuid.uuid4()
    return success_response({
        "export_job_id": str(export_job_id),
        "status": "QUEUED",
        "poll_url": f"/api/v1/exports/{export_job_id}",
    })


# =====================================================
# GROUP 7 — FEES & INTEREST
# =====================================================
fee_router = APIRouter(prefix="/api/v1", tags=["Fees & Interest"])


@fee_router.get(
    "/cards/{card_id}/fees",
    summary="List Card Fees",
    description="Returns all fee events applied to the card account with optional filters.",
)
def list_fees(
    card_id: uuid.UUID,
    fee_type: str | None = None,
    waived: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    fees = FeeService.list_fees(db, card_id, fee_type, waived)
    total = len(fees)
    paginated = fees[(page - 1) * page_size : page * page_size]
    data = [FeeSchema.model_validate(f).model_dump() for f in paginated]
    return paginated_response(data, total, page, page_size)


@fee_router.post(
    "/cards/{card_id}/fees",
    status_code=201,
    summary="Apply Fee",
    description="Manually apply a fee to a card account. Admin/System only. Set `waived=true` for fee waiver records.",
)
def apply_fee(
    card_id: uuid.UUID,
    request: CreateFeeRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    fee = FeeService.apply_fee(db, card_id, request, actor_id=user.id)
    data = FeeSchema.model_validate(fee).model_dump()
    return success_response(data)


@fee_router.patch(
    "/fees/{fee_id}",
    summary="Waive Fee",
    description="Waives a previously applied fee and credits the amount back to the card balance.",
)
def waive_fee(
    fee_id: uuid.UUID,
    command: str = Query(..., description="waive"),
    body: FeeWaiveRequest = None,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    if command != "waive":
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'. Only 'waive' is supported.")
    if not body:
        raise HTTPException(status_code=422, detail="Request body with waiver_reason is required")
    fee = FeeService.waive_fee(db, fee_id, body.waiver_reason, actor_id=user.id)
    data = FeeSchema.model_validate(fee).model_dump()
    return success_response(data)


@fee_router.post(
    "/cards/{card_id}/interest",
    status_code=201,
    summary="Post Interest Charge",
    description="System-only: calculates and posts monthly interest using DPR formula.",
)
def post_interest(
    card_id: uuid.UUID,
    request: InterestPostRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    fee = FeeService.post_interest(db, card_id, request, actor_id=user.id)
    data = FeeSchema.model_validate(fee).model_dump()
    return success_response(data)


# =====================================================
# GROUP 8 — PAYMENTS
# =====================================================
payment_router = APIRouter(prefix="/api/v1", tags=["Payments"])


@payment_router.post(
    "/cards/{card_id}/payments",
    status_code=201,
    summary="Make a Payment",
    description="""
Cardholder payment towards credit card outstanding balance.

**Sources:** BANK_ACCOUNT, NEFT, RTGS, UPI, CHEQUE

**Allocation Waterfall:**
1. Fees and charges
2. Interest charges
3. Cash advance principal
4. Purchase principal
""",
)
def create_payment(
    card_id: uuid.UUID,
    request: CreatePaymentRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    result = PaymentService.create_payment(db, card_id, request, actor_id=user.id)
    return success_response(result)


@payment_router.get(
    "/cards/{card_id}/payments",
    summary="List Payments",
    description="Lists all payments on the card account with status and date filters.",
)
def list_payments(
    card_id: uuid.UUID,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    query = db.query(Payment).filter(Payment.card_id == card_id)
    if status:
        query = query.filter(Payment.status == status)
    total = query.count()
    results = query.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [PaymentSchema.model_validate(p).model_dump() for p in results]
    return paginated_response(data, total, page, page_size)


@payment_router.patch(
    "/payments/{payment_id}",
    summary="Payment State Machine",
    description="""
Payment state transitions:
- `confirm` — Mark PENDING → POSTED (triggers balance update)
- `reverse` — Mark POSTED → REVERSED (re-debits balance, creates returned payment fee)
""",
)
def transition_payment(
    payment_id: uuid.UUID,
    command: str = Query(..., description="confirm | reverse"),
    body: PaymentCommandRequest = None,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    body = body or PaymentCommandRequest()
    if command == "confirm":
        payment = PaymentService.confirm_payment(db, payment_id, actor_id=user.id)
    elif command == "reverse":
        reason = body.reason or "Payment reversal"
        payment = PaymentService.reverse_payment(db, payment_id, reason, actor_id=user.id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'. Supported: confirm, reverse")
    data = PaymentSchema.model_validate(payment).model_dump()
    return success_response(data)


# =====================================================
# GROUP 9 — LIMITS & CONTROLS
# =====================================================
controls_router = APIRouter(prefix="/api/v1", tags=["Card Controls"])


@controls_router.get(
    "/cards/{card_id}/controls",
    summary="Get Card Controls",
    description="Returns current transaction controls and spending limits on the card.",
)
def get_controls(
    card_id: uuid.UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    ctrl = ControlsService.get_controls(db, card_id)
    data = CardControlSchema.model_validate(ctrl).model_dump()
    return success_response(data)


@controls_router.patch(
    "/cards/{card_id}/controls",
    summary="Update Card Controls",
    description="Update transaction controls. Cardholders can toggle international/online/contactless/ATM. Admin can set limits.",
)
def update_controls(
    card_id: uuid.UUID,
    request: UpdateCardControlRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    ctrl = ControlsService.update_controls(db, card_id, request, actor_id=user.id)
    data = CardControlSchema.model_validate(ctrl).model_dump()
    return success_response(data)


# =====================================================
# GROUP 10 — FRAUD & RISK
# =====================================================
risk_router = APIRouter(prefix="/api/v1", tags=["Fraud & Risk"])


@risk_router.get(
    "/transactions/{txn_id}/risk",
    summary="Get Transaction Risk Signals",
    description="Returns full fraud/risk signals for a transaction including fraud score, risk tier, and rules triggered.",
)
def get_transaction_risk(
    txn_id: uuid.UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    data = RiskService.get_transaction_risk(db, txn_id)
    return success_response(data)


@risk_router.get(
    "/risk/alerts",
    summary="List Risk Alerts",
    description="Lists open fraud/risk alerts requiring review with status and risk tier filters.",
)
def list_risk_alerts(
    status: str | None = None,
    risk_tier: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    alerts = RiskService.list_alerts(db, status, risk_tier)
    total = len(alerts)
    paginated = alerts[(page - 1) * page_size : page * page_size]
    data = [RiskAlertSchema.model_validate(a).model_dump() for a in paginated]
    return paginated_response(data, total, page, page_size)


@risk_router.patch(
    "/risk/alerts/{alert_id}",
    summary="Risk Alert Workflow",
    description="""
Risk alert review workflow:
- `review` — Mark as reviewed with outcome (TRUE_POSITIVE, FALSE_POSITIVE, INCONCLUSIVE)
- `dismiss` — False positive dismissal
- `escalate` — Escalate to senior risk officer
""",
)
def transition_risk_alert(
    alert_id: uuid.UUID,
    command: str = Query(..., description="review | dismiss | escalate"),
    body: RiskAlertCommandRequest = None,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    body = body or RiskAlertCommandRequest()
    if command == "review":
        if not body.review_outcome:
            raise HTTPException(status_code=422, detail="review_outcome is required")
        alert = RiskService.review_alert(db, alert_id, body.review_outcome.value, actor_id=user.id)
    elif command == "dismiss":
        alert = RiskService.dismiss_alert(db, alert_id, actor_id=user.id)
    elif command == "escalate":
        if not body.assigned_to:
            raise HTTPException(status_code=422, detail="assigned_to is required for escalation")
        alert = RiskService.escalate_alert(db, alert_id, body.assigned_to, actor_id=user.id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'")
    data = RiskAlertSchema.model_validate(alert).model_dump()
    return success_response(data)


# =====================================================
# GROUP 11 — RECONCILIATION & AUDIT
# =====================================================
recon_router = APIRouter(prefix="/api/v1", tags=["Reconciliation & Audit"])


@recon_router.get(
    "/reconciliation/summary",
    summary="Daily Reconciliation Summary",
    description="Returns daily reconciliation summary across all cards including authorized, cleared, settled, and disputed totals.",
)
def get_reconciliation_summary(
    for_date: date = Query(..., alias="date", description="Date to reconcile (YYYY-MM-DD)"),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    data = ReconciliationService.get_summary(db, for_date)
    data["date"] = str(data["date"])
    # Convert Decimal to str for JSON serialization
    for key in data:
        if hasattr(data[key], 'quantize'):
            data[key] = str(data[key])
    return success_response(data)


@recon_router.get(
    "/audit/transactions/{txn_id}",
    summary="Transaction Audit Trail",
    description="Complete immutable audit trail for a transaction — every status change, actor, timestamp, and payload.",
)
def get_transaction_audit(
    txn_id: uuid.UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    logs = ReconciliationService.get_audit_trail(db, entity_type="TRANSACTION", entity_id=str(txn_id))
    data = [AuditLogSchema.model_validate(log).model_dump() for log in logs]
    return success_response(data)
