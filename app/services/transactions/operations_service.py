"""
Operations Service — Business logic for Groups 6-11.
Handles: Statements, Fees, Payments, Card Controls, Risk Alerts, Audit/Reconciliation
"""
import uuid
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from fastapi import HTTPException

from app.admin.models.card_issuance import Card, CreditAccount
from app.models.transactions.transactions import Transaction, CreditHold, TransactionAuditLog as AuditLog
from app.models.transactions.fees import Fee
from app.models.transactions.payments import Payment
from app.models.transactions.controls import CardControl, CardControlHistory
from app.models.transactions.risk import RiskAlert
from app.models.transactions.statements import Statement, StatementLineItem
from app.models.transactions.enums import (
    TransactionType, TransactionStatus, HoldStatus,
    FeeType, PaymentStatus, StatementStatus,
    RiskAlertStatus, ReviewOutcome, AuditAction,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _write_audit(db: Session, entity_type: str, entity_id: str, action: str,
                 actor_id: str | None = None, actor_role: str | None = None,
                 before_state: dict | None = None, after_state: dict | None = None):
    entry = AuditLog(
        entity_type=entity_type, entity_id=str(entity_id), action=action,
        actor_id=str(actor_id) if actor_id else None, actor_role=actor_role,
        before_state=before_state, after_state=after_state,
    )
    db.add(entry)


# =====================================================
# GROUP 6 — STATEMENT SERVICE
# =====================================================
class StatementService:

    @staticmethod
    def list_statements(db: Session, card_id: uuid.UUID, year: int | None = None, month: int | None = None):
        query = db.query(Statement).filter(Statement.card_id == card_id)
        if year:
            query = query.filter(func.extract("year", Statement.cycle_start) == year)
        if month:
            query = query.filter(func.extract("month", Statement.cycle_start) == month)
        return query.order_by(Statement.cycle_start.desc()).all()

    @staticmethod
    def get_statement_detail(db: Session, statement_id: uuid.UUID):
        stmt = db.query(Statement).filter(Statement.id == statement_id).first()
        if not stmt:
            raise HTTPException(status_code=404, detail="Statement not found")
        return stmt


# =====================================================
# GROUP 7 — FEE SERVICE
# =====================================================
class FeeService:

    @staticmethod
    def list_fees(db: Session, card_id: uuid.UUID, fee_type: str | None = None,
                  waived: bool | None = None):
        query = db.query(Fee).filter(Fee.card_id == card_id)
        if fee_type:
            query = query.filter(Fee.fee_type == fee_type)
        if waived is not None:
            query = query.filter(Fee.waived == waived)
        return query.order_by(Fee.created_at.desc()).all()

    @staticmethod
    def apply_fee(db: Session, card_id: uuid.UUID, request, actor_id: str | None = None) -> Fee:
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")

        account = db.query(CreditAccount).filter(CreditAccount.id == card.credit_account_id).first()

        fee = Fee(
            card_id=card_id,
            fee_type=request.fee_type.value,
            amount=request.amount,
            waived=request.waived,
            waiver_reason=request.waiver_reason if request.waived else None,
        )
        db.add(fee)

        if not request.waived and account:
            account.outstanding_amount = account.outstanding_amount + request.amount
            account.available_limit = account.available_limit - request.amount

        _write_audit(db, "FEE", str(fee.id) if hasattr(fee, 'id') else "new",
                     AuditAction.FEE_APPLIED.value, actor_id=actor_id)
        db.commit()
        db.refresh(fee)
        return fee

    @staticmethod
    def waive_fee(db: Session, fee_id: uuid.UUID, waiver_reason: str, actor_id: str | None = None) -> Fee:
        fee = db.query(Fee).filter(Fee.id == fee_id).first()
        if not fee:
            raise HTTPException(status_code=404, detail="Fee not found")
        if fee.waived:
            raise HTTPException(status_code=400, detail="This fee has already been waived")

        fee.waived = True
        fee.waiver_reason = waiver_reason
        fee.waived_by = str(actor_id) if actor_id else None

        # Credit back to card
        card = db.query(Card).filter(Card.id == fee.card_id).first()
        if card:
            account = db.query(CreditAccount).filter(CreditAccount.id == card.credit_account_id).first()
            if account:
                account.outstanding_amount = account.outstanding_amount - fee.amount
                account.available_limit = account.available_limit + fee.amount

        _write_audit(db, "FEE", str(fee.id), AuditAction.FEE_WAIVED.value, actor_id=actor_id)
        db.commit()
        db.refresh(fee)
        return fee

    @staticmethod
    def post_interest(db: Session, card_id: uuid.UUID, request, actor_id: str | None = None) -> Fee:
        """Calculate and post monthly interest charge."""
        if request.previous_cycle_fully_paid:
            # Grace period applies — no purchase interest
            interest_amount = Decimal("0")
        else:
            dpr = request.purchase_apr / 365
            interest_amount = request.average_daily_balance * dpr * request.billing_cycle_days
            interest_amount = round(interest_amount, 2)

        if interest_amount <= 0:
            raise HTTPException(status_code=400, detail="No interest to charge (grace period applies or zero balance)")

        fee = Fee(
            card_id=card_id,
            fee_type=FeeType.INTEREST_CHARGE.value,
            amount=interest_amount,
        )
        db.add(fee)

        card = db.query(Card).filter(Card.id == card_id).first()
        if card:
            account = db.query(CreditAccount).filter(CreditAccount.id == card.credit_account_id).first()
            if account:
                account.outstanding_amount = account.outstanding_amount + interest_amount
                account.available_limit = account.available_limit - interest_amount

        db.commit()
        db.refresh(fee)
        return fee


# =====================================================
# GROUP 8 — PAYMENT SERVICE
# =====================================================
class PaymentService:

    @staticmethod
    def create_payment(db: Session, card_id: uuid.UUID, request, actor_id: str | None = None) -> dict:
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        account = db.query(CreditAccount).filter(CreditAccount.id == card.credit_account_id).first()
        if not account:
            raise HTTPException(status_code=400, detail="No credit account linked to this card")

        payment_date = request.payment_date or date.today()

        # Allocation waterfall
        allocation = {
            "fees_and_charges": str(min(request.amount, Decimal("0"))),
            "interest": "0",
            "cash_advance_principal": "0",
            "purchase_principal": str(request.amount),
        }

        payment = Payment(
            card_id=card_id,
            amount=request.amount,
            status=PaymentStatus.PENDING.value,
            payment_source=request.payment_source.value,
            source_reference=request.source_reference,
            payment_date=payment_date,
            allocation_breakdown=allocation,
            remarks=request.remarks,
        )
        db.add(payment)

        _write_audit(db, "PAYMENT", "new", AuditAction.PAYMENT_POSTED.value, actor_id=actor_id)
        db.commit()
        db.refresh(payment)

        return {
            "payment_id": payment.id,
            "status": payment.status,
            "amount": payment.amount,
            "new_balance": account.outstanding_amount,
            "new_available_credit": account.available_limit,
            "allocation_breakdown": allocation,
        }

    @staticmethod
    def confirm_payment(db: Session, payment_id: uuid.UUID, actor_id: str | None = None) -> Payment:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.status != PaymentStatus.PENDING.value:
            raise HTTPException(status_code=400, detail=f"Payment is '{payment.status}', not PENDING")

        payment.status = PaymentStatus.POSTED.value
        payment.posted_at = _utcnow()

        # Credit to card account
        card = db.query(Card).filter(Card.id == payment.card_id).first()
        if card:
            account = db.query(CreditAccount).filter(CreditAccount.id == card.credit_account_id).first()
            if account:
                account.outstanding_amount = account.outstanding_amount - payment.amount
                account.available_limit = account.available_limit + payment.amount

        _write_audit(db, "PAYMENT", str(payment.id), AuditAction.PAYMENT_POSTED.value, actor_id=actor_id)
        db.commit()
        db.refresh(payment)
        return payment

    @staticmethod
    def reverse_payment(db: Session, payment_id: uuid.UUID, reason: str, actor_id: str | None = None) -> Payment:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.status != PaymentStatus.POSTED.value:
            raise HTTPException(status_code=400, detail="Only POSTED payments can be reversed")

        payment.status = PaymentStatus.REVERSED.value

        # Re-debit card account
        card = db.query(Card).filter(Card.id == payment.card_id).first()
        if card:
            account = db.query(CreditAccount).filter(CreditAccount.id == card.credit_account_id).first()
            if account:
                account.outstanding_amount = account.outstanding_amount + payment.amount
                account.available_limit = account.available_limit - payment.amount

        _write_audit(db, "PAYMENT", str(payment.id), AuditAction.PAYMENT_REVERSED.value, actor_id=actor_id)
        db.commit()
        db.refresh(payment)
        return payment


# =====================================================
# GROUP 9 — CONTROLS SERVICE
# =====================================================
class ControlsService:

    @staticmethod
    def get_controls(db: Session, card_id: uuid.UUID) -> CardControl:
        ctrl = db.query(CardControl).filter(CardControl.card_id == card_id).first()
        if not ctrl:
            ctrl = CardControl(card_id=card_id)
            db.add(ctrl)
            db.commit()
            db.refresh(ctrl)
        return ctrl

    @staticmethod
    def update_controls(db: Session, card_id: uuid.UUID, request, actor_id: str | None = None,
                        is_admin: bool = False) -> CardControl:
        ctrl = db.query(CardControl).filter(CardControl.card_id == card_id).first()
        if not ctrl:
            ctrl = CardControl(card_id=card_id)
            db.add(ctrl)
            db.flush()

        previous = {
            "international_transactions_enabled": ctrl.international_transactions_enabled,
            "online_transactions_enabled": ctrl.online_transactions_enabled,
            "contactless_enabled": ctrl.contactless_enabled,
            "atm_withdrawals_enabled": ctrl.atm_withdrawals_enabled,
        }
        new_values = {}

        # User-accessible toggles
        if request.international_transactions_enabled is not None:
            ctrl.international_transactions_enabled = request.international_transactions_enabled
            new_values["international_transactions_enabled"] = request.international_transactions_enabled
        if request.online_transactions_enabled is not None:
            ctrl.online_transactions_enabled = request.online_transactions_enabled
            new_values["online_transactions_enabled"] = request.online_transactions_enabled
        if request.contactless_enabled is not None:
            ctrl.contactless_enabled = request.contactless_enabled
            new_values["contactless_enabled"] = request.contactless_enabled
        if request.atm_withdrawals_enabled is not None:
            ctrl.atm_withdrawals_enabled = request.atm_withdrawals_enabled
            new_values["atm_withdrawals_enabled"] = request.atm_withdrawals_enabled

        # Admin-only fields
        if is_admin:
            if request.daily_limit is not None:
                ctrl.daily_limit = request.daily_limit
                new_values["daily_limit"] = str(request.daily_limit)
            if request.single_transaction_limit is not None:
                ctrl.single_transaction_limit = request.single_transaction_limit
                new_values["single_transaction_limit"] = str(request.single_transaction_limit)
            if request.monthly_limit is not None:
                ctrl.monthly_limit = request.monthly_limit
                new_values["monthly_limit"] = str(request.monthly_limit)
            if request.mcc_blocks is not None:
                ctrl.mcc_blocks = request.mcc_blocks
                new_values["mcc_blocks"] = request.mcc_blocks
            if request.allowed_countries is not None:
                ctrl.allowed_countries = request.allowed_countries
                new_values["allowed_countries"] = request.allowed_countries

        # Store history
        if new_values:
            history = CardControlHistory(
                card_id=card_id,
                changed_by=str(actor_id) if actor_id else "system",
                previous_values=previous,
                new_values=new_values,
                diff=new_values,
            )
            db.add(history)
            _write_audit(db, "CARD_CONTROLS", str(card_id), AuditAction.CONTROLS_UPDATED.value,
                         actor_id=actor_id, before_state=previous, after_state=new_values)

        db.commit()
        db.refresh(ctrl)
        return ctrl


# =====================================================
# GROUP 10 — RISK SERVICE
# =====================================================
class RiskService:

    @staticmethod
    def get_transaction_risk(db: Session, txn_id: uuid.UUID):
        alert = db.query(RiskAlert).filter(RiskAlert.transaction_id == txn_id).first()
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return {
            "fraud_score": txn.fraud_score or 0.0,
            "risk_tier": txn.risk_tier or "LOW",
            "rules_triggered": alert.rules_triggered if alert else [],
            "reviewed_by": alert.assigned_to if alert else None,
            "review_outcome": alert.review_outcome if alert else None,
        }

    @staticmethod
    def list_alerts(db: Session, status: str | None = None, risk_tier: str | None = None):
        query = db.query(RiskAlert)
        if status:
            query = query.filter(RiskAlert.status == status)
        if risk_tier:
            query = query.filter(RiskAlert.risk_tier == risk_tier)
        return query.order_by(RiskAlert.created_at.desc()).all()

    @staticmethod
    def review_alert(db: Session, alert_id: uuid.UUID, outcome: str, actor_id: str | None = None) -> RiskAlert:
        alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Risk alert not found")
        alert.status = RiskAlertStatus.REVIEWED.value
        alert.review_outcome = outcome
        alert.reviewed_at = _utcnow()
        _write_audit(db, "RISK_ALERT", str(alert.id), AuditAction.RISK_ALERT_REVIEWED.value, actor_id=actor_id)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def dismiss_alert(db: Session, alert_id: uuid.UUID, actor_id: str | None = None) -> RiskAlert:
        alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Risk alert not found")
        alert.status = RiskAlertStatus.DISMISSED.value
        alert.review_outcome = ReviewOutcome.FALSE_POSITIVE.value
        alert.reviewed_at = _utcnow()
        _write_audit(db, "RISK_ALERT", str(alert.id), AuditAction.RISK_ALERT_DISMISSED.value, actor_id=actor_id)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def escalate_alert(db: Session, alert_id: uuid.UUID, assigned_to: str, actor_id: str | None = None) -> RiskAlert:
        alert = db.query(RiskAlert).filter(RiskAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Risk alert not found")
        alert.status = RiskAlertStatus.ESCALATED.value
        alert.assigned_to = assigned_to
        _write_audit(db, "RISK_ALERT", str(alert.id), AuditAction.RISK_ALERT_ESCALATED.value, actor_id=actor_id)
        db.commit()
        db.refresh(alert)
        return alert


# =====================================================
# GROUP 11 — RECONCILIATION & AUDIT SERVICE
# =====================================================
class ReconciliationService:

    @staticmethod
    def get_summary(db: Session, for_date: date):
        from app.models.transactions.clearing import ClearingRecord
        from app.models.transactions.settlement import SettlementRecord
        from app.models.transactions.disputes import Dispute

        total_authorized = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            and_(Transaction.status == TransactionStatus.AUTHORIZED.value,
                 func.date(Transaction.created_at) == for_date)).scalar()
        total_cleared = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            and_(Transaction.status == TransactionStatus.CLEARED.value,
                 func.date(Transaction.created_at) == for_date)).scalar()
        total_settled = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            and_(Transaction.status == TransactionStatus.SETTLED.value,
                 func.date(Transaction.created_at) == for_date)).scalar()
        total_reversed = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            and_(Transaction.status == TransactionStatus.REVERSED.value,
                 func.date(Transaction.created_at) == for_date)).scalar()
        total_disputed = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            and_(Transaction.status == TransactionStatus.DISPUTED.value,
                 func.date(Transaction.created_at) == for_date)).scalar()
        total_fees = db.query(func.coalesce(func.sum(Fee.amount), 0)).filter(
            and_(Fee.waived == False, func.date(Fee.created_at) == for_date)).scalar()

        holds_active = db.query(CreditHold).filter(CreditHold.status == HoldStatus.ACTIVE.value).all()
        open_holds_count = len(holds_active)
        open_holds_amount = sum(h.amount for h in holds_active)

        return {
            "date": for_date,
            "total_authorized": total_authorized,
            "total_cleared": total_cleared,
            "total_settled": total_settled,
            "total_reversed": total_reversed,
            "total_disputed": total_disputed,
            "total_fees_collected": total_fees,
            "interchange_earned": Decimal("0"),
            "open_holds_count": open_holds_count,
            "open_holds_amount": open_holds_amount,
            "exceptions_count": 0,
        }

    @staticmethod
    def get_audit_trail(db: Session, entity_type: str | None = None, entity_id: str | None = None):
        query = db.query(AuditLog)
        if entity_type:
            query = query.filter(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.filter(AuditLog.entity_id == entity_id)
        return query.order_by(AuditLog.timestamp.desc()).all()
