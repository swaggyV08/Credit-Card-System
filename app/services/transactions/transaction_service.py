"""
Transaction Service — Core business logic for Groups 1-5.
Handles authorization, velocity checks, hold management, clearing,
settlement, disputes, and refunds.
"""
import uuid
import string
import random
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from fastapi import HTTPException

from app.admin.models.card_issuance import Card, CreditAccount
from app.models.transactions.transactions import Transaction, CreditHold, TransactionAuditLog as AuditLog
from app.models.transactions.clearing import ClearingBatch, ClearingRecord
from app.models.transactions.settlement import SettlementRun, SettlementRecord
from app.models.transactions.disputes import Dispute, DisputeEvidence, ProvisionalCredit
from app.models.transactions.payments import Refund
from app.models.transactions.enums import (
    TransactionType, TransactionStatus, HoldStatus,
    ClearingBatchStatus, SettlementRunStatus,
    DisputeType, DisputeStatus, ProvisionalCreditStatus,
    RiskTier, AuditAction,
)
from app.models.enums import CardStatus, ScoreTrigger
from app.services.bureau_service import compute_bureau_score
from app.core.redis import redis_service
from app.core.app_error import AppError
from app.core.exceptions import (
    VelocityExceededError, InsufficientFundsError, CardNotActiveError,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_auth_code() -> str:
    """Generate a unique 8-character alphanumeric auth code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=8))


def _generate_case_number() -> str:
    """Generate a formatted dispute case number: DISP-YYYY-XXXXXX."""
    year = datetime.now(timezone.utc).year
    seq = "".join(random.choices(string.digits, k=6))
    return f"DISP-{year}-{seq}"


def _write_audit(db: Session, entity_type: str, entity_id: str, action: str,
                 actor_id: str | None = None, actor_role: str | None = None,
                 before_state: dict | None = None, after_state: dict | None = None):
    """Append an immutable audit log entry."""
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        actor_id=str(actor_id) if actor_id else None,
        actor_role=actor_role,
        before_state=before_state,
        after_state=after_state,
    )
    db.add(entry)


# =====================================================
# GROUP 1 — TRANSACTION SERVICE
# =====================================================
class TransactionService:

    @staticmethod
    def get_transaction(db: Session, txn_id: uuid.UUID) -> Transaction:
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        # Ensure dispute is loaded (it's a relationship)
        # SQLAlchemy will handle this if the relationship is defined
        return txn
        return txn

    @staticmethod
    def check_velocity(db: Session, card_id: uuid.UUID, amount: Decimal):
        """
        Step 3: Redis Velocity Gate (Directive Mandated).
        Four sliding windows: 1m (3), 10m (10), 1h (20), 24h (50).
        """
        client = redis_service.get_client()
        if not client:
            return  # Fail open if Redis is down, or implement fallback

        now_ts = int(_utcnow().timestamp())
        windows = [
            ("1m", 60, 3),
            ("10m", 600, 10),
            ("1h", 3600, 20),
            ("24h", 86400, 50),
        ]

        for suffix, ttl, threshold in windows:
            key = f"velocity:{card_id}:{suffix}"
            try:
                # Use a sliding window pipe
                p = client.pipeline()
                p.zremrangebyscore(key, 0, now_ts - ttl)
                p.zadd(key, {str(now_ts): now_ts})
                p.zcard(key)
                p.expire(key, ttl)
                results = p.execute()
                
                count = results[2]
                if count > threshold:
                    # Retry-After value
                    raise VelocityExceededError(retry_after=ttl // 10)
            except VelocityExceededError:
                raise
            except Exception as e:
                import logging
                logging.getLogger("zbanque.velocity").error(f"Redis velocity error: {e}")

    @staticmethod
    def check_geo_velocity(db: Session, card_id: uuid.UUID, current_country: str) -> None:
        """
        Geographic velocity check: if country change < 2h, flag but do not block.
        """
        last_txn = db.query(Transaction).filter(
            Transaction.card_id == card_id,
            Transaction.status.in_([TransactionStatus.AUTHORIZED.value, TransactionStatus.SETTLED.value])
        ).order_by(Transaction.created_at.desc()).first()

        if not last_txn or not last_txn.merchant_country:
            return

        if last_txn.merchant_country != current_country:
            time_delta = (_utcnow() - last_txn.created_at).total_seconds()
            if time_delta < 7200:
                # Add risk signal / flag
                import logging
                logging.getLogger("zbanque.geo").warning(
                    f"Geographic velocity flag for card {card_id}: "
                    f"Country jumped from {last_txn.merchant_country} to {current_country} in {time_delta}s"
                )

    @staticmethod
    def check_duplicate(db: Session, card_id: uuid.UUID, merchant_id: uuid.UUID,
                        amount: Decimal, idempotency_key: str | None = None) -> Transaction | None:
        """Check for duplicate transactions (idempotency)."""
        if idempotency_key:
            existing = db.query(Transaction).filter(Transaction.idempotency_key == idempotency_key).first()
            if existing:
                return existing

        # 60-second window duplicate check
        cutoff = _utcnow() - timedelta(seconds=60)
        duplicate = db.query(Transaction).filter(
            and_(
                Transaction.card_id == card_id,
                Transaction.merchant_id == merchant_id,
                Transaction.amount == amount,
                Transaction.created_at >= cutoff,
            )
        ).first()
        return duplicate

    @staticmethod
    def authorize_transaction(db: Session, card: Card, request, idempotency_key: str | None = None,
                               actor_id: str | None = None) -> dict:
        """Full authorization flow: Steps 1-6."""
        account = db.query(CreditAccount).filter(CreditAccount.id == card.credit_account_id).first()
        if not account:
            raise HTTPException(status_code=400, detail="No credit account linked to this card")

        # Step 4: Credit Limit Authorization
        available_credit = account.available_limit
        if request.amount <= 0:
            raise AppError(code="INVALID_AMOUNT", message="Transaction amount must be greater than zero.", http_status=400)

        if request.amount > available_credit:
            raise InsufficientFundsError(available=available_credit, requested=request.amount)

        if request.transaction_type == TransactionType.CASH_ADVANCE:
            if request.amount > account.cash_advance_limit:
                raise AppError(code="CASH_ADVANCE_LIMIT_EXCEEDED", message=f"Cash advance limit exceeded. Limit: {account.cash_advance_limit}", http_status=402)

        # Step 4.2: Controls & Restrictions
        from app.models.transactions.controls import CardControl
        controls = db.query(CardControl).filter(CardControl.card_id == card.id).first()
        if controls:
            if controls.mcc_blocks and str(request.merchant_category_code) in controls.mcc_blocks:
                raise AppError(code="MCC_RESTRICTED", message="Merchant Category Code is restricted for this card.", http_status=403)
            
            if controls.allowed_countries and request.merchant_country not in controls.allowed_countries:
                raise AppError(code="COUNTRY_RESTRICTED", message="Merchant country is restricted for this card.", http_status=403)
            
            if not controls.online_transactions_enabled and request.card_not_present:
                raise AppError(code="ONLINE_RESTRICTED", message="Online transactions are disabled for this card.", http_status=403)

        # Step 4.3: Geographic Velocity Flagging
        TransactionService.check_geo_velocity(db, card.id, request.merchant_country)

        # Step 5: Hold Creation
        hold_days = 30 if request.transaction_type == TransactionType.PRE_AUTH else 7
        auth_code = _generate_auth_code()

        txn = Transaction(
            card_id=card.id,
            account_id=account.id,
            amount=request.amount,
            currency=request.currency,
            transaction_type=request.transaction_type.value,
            status=TransactionStatus.AUTHORIZED.value,
            merchant_id=request.merchant_id,
            merchant_name=request.merchant_name,
            merchant_category_code=request.merchant_category_code,
            merchant_country=request.merchant_country,
            auth_code=auth_code,
            terminal_id=request.terminal_id,
            pos_entry_mode=request.pos_entry_mode.value if request.pos_entry_mode else None,
            card_not_present=request.card_not_present,
            installments=request.installments,
            idempotency_key=idempotency_key,
            metadata_json=request.metadata,
        )
        db.add(txn)
        db.flush()

        hold = CreditHold(
            transaction_id=txn.id,
            card_id=card.id,
            amount=request.amount,
            currency=request.currency,
            status=HoldStatus.ACTIVE.value,
            hold_expiry=_utcnow() + timedelta(days=hold_days),
        )
        db.add(hold)

        # Decrement available credit atomically
        account.available_limit = account.available_limit - request.amount
        account.outstanding_amount = account.outstanding_amount + request.amount

        _write_audit(db, "TRANSACTION", str(txn.id), AuditAction.TRANSACTION_CREATED.value,
                     actor_id=actor_id, after_state={"status": txn.status, "amount": str(txn.amount)})

        db.commit()
        db.refresh(txn)
        db.refresh(hold)
        db.refresh(account)

        return {
            "transaction_id": txn.id,
            "auth_code": txn.auth_code,
            "status": txn.status,
            "amount": txn.amount,
            "currency": txn.currency,
            "available_credit": account.available_limit,
            "hold_id": hold.id,
            "hold_expiry": hold.hold_expiry,
        }

    @staticmethod
    def reverse_transaction(db: Session, txn: Transaction, reason: str, actor_id: str | None = None) -> Transaction:
        """Reverse an authorized transaction."""
        if txn.status != TransactionStatus.AUTHORIZED.value:
            raise HTTPException(status_code=400, detail=f"Cannot reverse a transaction with status '{txn.status}'. Only AUTHORIZED transactions can be reversed.")

        old_status = txn.status
        txn.status = TransactionStatus.REVERSED.value

        # Release holds
        holds = db.query(CreditHold).filter(
            and_(CreditHold.transaction_id == txn.id, CreditHold.status == HoldStatus.ACTIVE.value)
        ).all()
        account = db.query(CreditAccount).filter(CreditAccount.id == txn.account_id).first()
        for hold in holds:
            hold.status = HoldStatus.RELEASED.value
            hold.release_reason = reason
            hold.released_at = _utcnow()
            if account:
                account.available_limit = account.available_limit + hold.amount
                account.outstanding_amount = account.outstanding_amount - hold.amount

        _write_audit(db, "TRANSACTION", str(txn.id), AuditAction.TRANSACTION_REVERSED.value,
                     actor_id=actor_id, before_state={"status": old_status}, after_state={"status": txn.status})
        db.commit()
        db.refresh(txn)
        return txn

    @staticmethod
    def void_transaction(db: Session, txn: Transaction, reason: str, actor_id: str | None = None) -> Transaction:
        """Void a pending transaction."""
        if txn.status != TransactionStatus.PENDING_AUTHORIZATION.value:
            raise AppError(code="INVALID_STATUS", message="Only PENDING_AUTHORIZATION transactions can be voided", http_status=400)
        old_status = txn.status
        txn.status = TransactionStatus.VOIDED.value
        _write_audit(db, "TRANSACTION", str(txn.id), AuditAction.TRANSACTION_VOIDED.value,
                     actor_id=actor_id, before_state={"status": old_status}, after_state={"status": txn.status})
        db.commit()
        db.refresh(txn)
        return txn

    @staticmethod
    def flag_transaction(db: Session, txn: Transaction, reason: str, actor_id: str | None = None) -> Transaction:
        txn.internal_flag = True
        txn.internal_flag_reason = reason
        _write_audit(db, "TRANSACTION", str(txn.id), AuditAction.TRANSACTION_FLAGGED.value,
                     actor_id=actor_id, after_state={"flag_reason": reason})
        db.commit()
        db.refresh(txn)
        return txn

    @staticmethod
    def unflag_transaction(db: Session, txn: Transaction, reason: str, actor_id: str | None = None) -> Transaction:
        txn.internal_flag = False
        txn.internal_flag_reason = None
        _write_audit(db, "TRANSACTION", str(txn.id), AuditAction.TRANSACTION_UNFLAGGED.value,
                     actor_id=actor_id, after_state={"unflag_reason": reason})
        db.commit()
        db.refresh(txn)
        return txn

    @staticmethod
    def capture_preauth(db: Session, txn: Transaction, capture_amount: Decimal | None, actor_id: str | None = None) -> Transaction:
        """Capture a PRE_AUTH transaction."""
        if txn.transaction_type != TransactionType.PRE_AUTH.value:
            raise AppError(code="INVALID_TYPE", message="Only PRE_AUTH transactions can be captured", http_status=400)
        if txn.status != TransactionStatus.AUTHORIZED.value:
            raise AppError(code="INVALID_STATUS", message="Transaction must be AUTHORIZED to capture", http_status=400)

        original_amount = txn.amount
        final_amount = capture_amount if capture_amount and capture_amount <= original_amount else original_amount

        # Release excess hold if partial capture
        if final_amount < original_amount:
            excess = original_amount - final_amount
            account = db.query(CreditAccount).filter(CreditAccount.id == txn.account_id).first()
            if account:
                account.available_limit = account.available_limit + excess
                account.outstanding_amount = account.outstanding_amount - excess

        txn.amount = final_amount
        txn.status = TransactionStatus.CLEARED.value

        # Release original hold
        holds = db.query(CreditHold).filter(
            and_(CreditHold.transaction_id == txn.id, CreditHold.status == HoldStatus.ACTIVE.value)
        ).all()
        for hold in holds:
            hold.status = HoldStatus.RELEASED.value
            hold.release_reason = "Captured"
            hold.released_at = _utcnow()

        _write_audit(db, "TRANSACTION", str(txn.id), AuditAction.TRANSACTION_CAPTURED.value,
                     actor_id=actor_id, after_state={"captured_amount": str(final_amount)})
        db.commit()
        db.refresh(txn)
        return txn


# =====================================================
# GROUP 2 — HOLD SERVICE
# =====================================================
class HoldService:

    @staticmethod
    def get_holds(db: Session, card_id: uuid.UUID, status_filter: str | None = "ACTIVE"):
        query = db.query(CreditHold).filter(CreditHold.card_id == card_id)
        if status_filter and status_filter != "ALL":
            query = query.filter(CreditHold.status == status_filter)

        # Lazy cleanup: expire any active holds past their expiry
        now = _utcnow()
        expired = db.query(CreditHold).filter(
            and_(CreditHold.card_id == card_id, CreditHold.status == HoldStatus.ACTIVE.value,
                 CreditHold.hold_expiry < now)
        ).all()
        for h in expired:
            h.status = HoldStatus.EXPIRED.value
            account = db.query(CreditAccount).join(Card, Card.credit_account_id == CreditAccount.id).filter(Card.id == card_id).first()
            if account:
                account.available_limit = account.available_limit + h.amount
                account.outstanding_amount = account.outstanding_amount - h.amount
        if expired:
            db.commit()

        holds = query.all()
        total_hold = sum(h.amount for h in holds if h.status == HoldStatus.ACTIVE.value)

        account = db.query(CreditAccount).join(Card, Card.credit_account_id == CreditAccount.id).filter(Card.id == card_id).first()
        available_credit = account.available_limit if account else Decimal("0")

        return holds, total_hold, available_credit

    @staticmethod
    def release_hold(db: Session, hold_id: uuid.UUID, reason: str, actor_id: str | None = None):
        hold = db.query(CreditHold).filter(CreditHold.id == hold_id).first()
        if not hold:
            raise HTTPException(status_code=404, detail="Hold not found")
        if hold.status != HoldStatus.ACTIVE.value:
            raise HTTPException(status_code=400, detail=f"Cannot release a hold with status '{hold.status}'. Only ACTIVE holds can be released.")

        hold.status = HoldStatus.RELEASED.value
        hold.release_reason = reason
        hold.released_at = _utcnow()
        hold.released_by = str(actor_id) if actor_id else None

        account = db.query(CreditAccount).join(Card, Card.credit_account_id == CreditAccount.id).filter(Card.id == hold.card_id).first()
        if account:
            account.available_limit = account.available_limit + hold.amount
            account.outstanding_amount = account.outstanding_amount - hold.amount

        _write_audit(db, "HOLD", str(hold.id), AuditAction.HOLD_RELEASED.value,
                     actor_id=actor_id, after_state={"reason": reason})
        db.commit()
        db.refresh(hold)
        return hold


# =====================================================
# GROUP 3 — CLEARING SERVICE
# =====================================================
class ClearingService:

    @staticmethod
    def process_batch(db: Session, request, actor_id: str | None = None) -> dict:
        batch = ClearingBatch(
            network=request.network.value,
            file_reference=request.file_reference,
            status=ClearingBatchStatus.PROCESSING.value,
        )
        db.add(batch)
        db.flush()

        matched, exceptions, force_posts = 0, 0, 0

        for record in request.clearing_records:
            txn = db.query(Transaction).filter(Transaction.auth_code == record.auth_code).first()

            if not txn:
                # Force post
                force_posts += 1
                cr = ClearingRecord(
                    batch_id=batch.id, clearing_amount=record.clearing_amount,
                    clearing_date=record.txn_date, force_post=True,
                )
                db.add(cr)
                continue

            # Check for duplicate clearing
            existing_cr = db.query(ClearingRecord).filter(ClearingRecord.transaction_id == txn.id).first()
            if existing_cr:
                exceptions += 1
                continue

            # Amount mismatch check
            diff_pct = abs(record.clearing_amount - txn.amount) / txn.amount * 100 if txn.amount else 0
            if diff_pct > 20:
                exceptions += 1

            cr = ClearingRecord(
                transaction_id=txn.id, batch_id=batch.id,
                clearing_amount=record.clearing_amount,
                clearing_date=record.txn_date,
            )
            db.add(cr)

            txn.status = TransactionStatus.CLEARED.value

            # Release original hold
            holds = db.query(CreditHold).filter(
                and_(CreditHold.transaction_id == txn.id, CreditHold.status == HoldStatus.ACTIVE.value)
            ).all()
            for h in holds:
                h.status = HoldStatus.RELEASED.value
                h.released_at = _utcnow()
                h.release_reason = "Cleared"
            matched += 1

        batch.status = ClearingBatchStatus.COMPLETED.value
        batch.processed_count = len(request.clearing_records)
        batch.matched_count = matched
        batch.exception_count = exceptions
        batch.force_post_count = force_posts

        _write_audit(db, "CLEARING_BATCH", str(batch.id), AuditAction.CLEARING_BATCH_PROCESSED.value,
                     actor_id=actor_id)
        db.commit()

        return {
            "batch_id": batch.id,
            "processed": batch.processed_count,
            "matched": matched,
            "exceptions": exceptions,
            "force_posts": force_posts,
        }


# =====================================================
# GROUP 3 — SETTLEMENT SERVICE
# =====================================================
class SettlementService:

    @staticmethod
    def run_settlement(db: Session, request, actor_id: str | None = None) -> dict:
        run = SettlementRun(
            network=request.network.value,
            settlement_date=request.settlement_date,
            status=SettlementRunStatus.IN_PROGRESS.value,
        )
        db.add(run)
        db.flush()

        cleared_txns = db.query(Transaction).filter(
            and_(Transaction.status == TransactionStatus.CLEARED.value,
                 Transaction.created_at <= request.cutoff_datetime)
        ).all()

        cards_settled, total_amount, failed = 0, Decimal("0"), 0

        for txn in cleared_txns:
            try:
                record = SettlementRecord(
                    settlement_run_id=run.id,
                    transaction_id=txn.id,
                    net_amount=txn.amount,
                    settlement_date=request.settlement_date,
                )
                db.add(record)
                txn.status = TransactionStatus.SETTLED.value
                total_amount += txn.amount
                cards_settled += 1
            except Exception:
                failed += 1

        run.status = SettlementRunStatus.COMPLETED.value
        run.total_amount = total_amount
        run.cards_settled = cards_settled
        run.failed_count = failed

        _write_audit(db, "SETTLEMENT_RUN", str(run.id), AuditAction.SETTLEMENT_COMPLETED.value,
                     actor_id=actor_id)
        db.commit()

        # ── Trigger Bureau Score (Async/Non-blocking) ──
        try:
            import asyncio
            from uuid import UUID
            user_ids = set()
            for txn in cleared_txns:
                acc = db.query(CreditAccount).filter(CreditAccount.id == txn.account_id).first()
                if acc and acc.user_id:
                    user_ids.add(UUID(str(acc.user_id)))
            
            for u_id in user_ids:
                asyncio.create_task(compute_bureau_score(u_id, ScoreTrigger.SETTLEMENT_RUN))
        except Exception as e:
            import logging
            logging.getLogger("zbanque.bureau").error(f"Failed to trigger bureau scores after settlement: {e}")

        return {
            "settlement_run_id": run.id,
            "cards_settled": cards_settled,
            "total_amount": total_amount,
            "failed_count": failed,
        }


# =====================================================
# GROUP 4 — DISPUTE SERVICE
# =====================================================
class DisputeService:

    @staticmethod
    def create_dispute(db: Session, txn_id: uuid.UUID, request, actor_id: str | None = None) -> dict:
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")

        if txn.status not in (TransactionStatus.CLEARED.value, TransactionStatus.SETTLED.value):
            raise HTTPException(status_code=400, detail=f"Cannot dispute a transaction with status '{txn.status}'. Only CLEARED or SETTLED transactions can be disputed.")

        # Check for existing open dispute
        existing = db.query(Dispute).filter(
            and_(Dispute.transaction_id == txn_id,
                 Dispute.status.in_([DisputeStatus.OPENED.value, DisputeStatus.UNDER_REVIEW.value, DisputeStatus.ESCALATED.value]))
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"An active dispute (case {existing.case_number}) already exists for this transaction")

        # Check dispute window (120 days)
        if (_utcnow() - txn.created_at).days > 120:
            raise HTTPException(status_code=400, detail="Dispute window has expired. Disputes must be raised within 120 days of the transaction date.")

        case_number = _generate_case_number()
        deadline = _utcnow() + timedelta(days=45)

        provisional_credit_issued = False
        prov_credit = None

        if request.request_provisional_credit and request.dispute_type in (DisputeType.UNAUTHORIZED, DisputeType.FRAUD):
            prov_credit = ProvisionalCredit(
                card_id=txn.card_id,
                amount=request.transaction_amount_disputed,
                status=ProvisionalCreditStatus.PROVISIONAL.value,
            )
            db.add(prov_credit)
            db.flush()

            # Credit the card balance
            account = db.query(CreditAccount).filter(CreditAccount.id == txn.account_id).first()
            if account:
                account.available_limit = account.available_limit + request.transaction_amount_disputed
                account.outstanding_amount = account.outstanding_amount - request.transaction_amount_disputed
            provisional_credit_issued = True

        dispute = Dispute(
            transaction_id=txn_id,
            card_id=txn.card_id,
            case_number=case_number,
            dispute_type=request.dispute_type.value,
            status=DisputeStatus.OPENED.value,
            description=request.description,
            amount_disputed=request.transaction_amount_disputed,
            deadline=deadline,
            provisional_credit_id=prov_credit.id if prov_credit else None,
        )
        db.add(dispute)
        txn.status = TransactionStatus.DISPUTED.value

        _write_audit(db, "DISPUTE", str(dispute.id) if hasattr(dispute, 'id') else case_number,
                     AuditAction.DISPUTE_OPENED.value, actor_id=actor_id)
        db.commit()
        db.refresh(dispute)

        return {
            "dispute_id": dispute.id,
            "case_number": case_number,
            "status": dispute.status,
            "provisional_credit_issued": provisional_credit_issued,
            "deadline": deadline,
            "next_steps": "Submit supporting evidence within the deadline. You will be notified of the resolution.",
        }

    @staticmethod
    def resolve_dispute(db: Session, dispute: Dispute, resolution: str, actor_id: str | None = None) -> Dispute:
        if resolution == DisputeStatus.RESOLVED_WON.value:
            dispute.status = DisputeStatus.RESOLVED_WON.value
            # Confirm provisional credit as permanent
            if dispute.provisional_credit_id:
                prov = db.query(ProvisionalCredit).filter(ProvisionalCredit.id == dispute.provisional_credit_id).first()
                if prov:
                    prov.status = ProvisionalCreditStatus.PERMANENT.value
            txn = db.query(Transaction).filter(Transaction.id == dispute.transaction_id).first()
            if txn:
                txn.status = TransactionStatus.CHARGED_BACK.value
        elif resolution == DisputeStatus.RESOLVED_LOST.value:
            dispute.status = DisputeStatus.RESOLVED_LOST.value
            # Reverse provisional credit
            if dispute.provisional_credit_id:
                prov = db.query(ProvisionalCredit).filter(ProvisionalCredit.id == dispute.provisional_credit_id).first()
                if prov and prov.status == ProvisionalCreditStatus.PROVISIONAL.value:
                    prov.status = ProvisionalCreditStatus.REVERSED.value
                    prov.reversed_at = _utcnow()
                    # Re-debit the card
                    account = db.query(CreditAccount).join(Card, Card.credit_account_id == CreditAccount.id).filter(Card.id == prov.card_id).first()
                    if account:
                        account.available_limit = account.available_limit - prov.amount
                        account.outstanding_amount = account.outstanding_amount + prov.amount
            txn = db.query(Transaction).filter(Transaction.id == dispute.transaction_id).first()
            if txn:
                txn.status = TransactionStatus.DISPUTE_REJECTED.value
        else:
            raise HTTPException(status_code=400, detail="Resolution must be RESOLVED_WON or RESOLVED_LOST")

        dispute.resolved_at = _utcnow()
        dispute.resolved_by = str(actor_id) if actor_id else None
        dispute.resolution = resolution

        _write_audit(db, "DISPUTE", str(dispute.id), AuditAction.DISPUTE_RESOLVED.value, actor_id=actor_id)
        db.commit()
        db.refresh(dispute)
        return dispute

    @staticmethod
    def withdraw_dispute(db: Session, dispute: Dispute, actor_id: str | None = None) -> Dispute:
        if dispute.status in (DisputeStatus.RESOLVED_WON.value, DisputeStatus.RESOLVED_LOST.value):
            raise HTTPException(status_code=400, detail="Cannot withdraw an already resolved dispute")

        dispute.status = DisputeStatus.WITHDRAWN.value
        dispute.resolved_at = _utcnow()

        # Reverse provisional credit if exists
        if dispute.provisional_credit_id:
            prov = db.query(ProvisionalCredit).filter(ProvisionalCredit.id == dispute.provisional_credit_id).first()
            if prov and prov.status == ProvisionalCreditStatus.PROVISIONAL.value:
                prov.status = ProvisionalCreditStatus.REVERSED.value
                prov.reversed_at = _utcnow()
                account = db.query(CreditAccount).join(Card, Card.credit_account_id == CreditAccount.id).filter(Card.id == prov.card_id).first()
                if account:
                    account.available_limit = account.available_limit - prov.amount
                    account.outstanding_amount = account.outstanding_amount + prov.amount

        # Return transaction to SETTLED
        txn = db.query(Transaction).filter(Transaction.id == dispute.transaction_id).first()
        if txn:
            txn.status = TransactionStatus.SETTLED.value

        _write_audit(db, "DISPUTE", str(dispute.id), AuditAction.DISPUTE_WITHDRAWN.value, actor_id=actor_id)
        db.commit()
        db.refresh(dispute)
        return dispute


# =====================================================
# GROUP 5 — REFUND SERVICE
# =====================================================
class RefundService:

    @staticmethod
    def process_refund(db: Session, txn_id: uuid.UUID, request, actor_id: str | None = None) -> dict:
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")

        if txn.status != TransactionStatus.SETTLED.value:
            raise HTTPException(status_code=400, detail=f"Refunds can only be issued against SETTLED transactions. Current status: {txn.status}")

        if request.amount > txn.amount:
            raise HTTPException(status_code=400, detail=f"Refund amount ({request.amount}) cannot exceed the original transaction amount ({txn.amount})")

        # Check cumulative refunds
        existing_refunds = db.query(func.coalesce(func.sum(Refund.amount), 0)).filter(
            Refund.original_txn_id == txn_id
        ).scalar()
        if existing_refunds + request.amount > txn.amount:
            raise HTTPException(status_code=400, detail=f"Total refunds ({existing_refunds + request.amount}) would exceed the original transaction amount ({txn.amount})")

        account = db.query(CreditAccount).filter(CreditAccount.id == txn.account_id).first()

        # Create refund transaction
        refund_txn = Transaction(
            card_id=txn.card_id,
            account_id=txn.account_id,
            amount=request.amount,
            currency=txn.currency,
            transaction_type=TransactionType.REFUND.value,
            status=TransactionStatus.SETTLED.value,
            merchant_id=txn.merchant_id,
            merchant_name=txn.merchant_name,
            parent_txn_id=txn.id,
            auth_code=_generate_auth_code(),
        )
        db.add(refund_txn)
        db.flush()

        refund_record = Refund(
            original_txn_id=txn.id,
            refund_txn_id=refund_txn.id,
            amount=request.amount,
            reason=request.reason,
            merchant_reference=request.merchant_reference,
            partial=request.partial,
        )
        db.add(refund_record)

        # Credit to card
        if account:
            account.available_limit = account.available_limit + request.amount
            account.outstanding_amount = account.outstanding_amount - request.amount

        _write_audit(db, "REFUND", str(refund_txn.id), AuditAction.REFUND_POSTED.value, actor_id=actor_id)
        db.commit()
        db.refresh(account)

        return {
            "refund_transaction_id": refund_txn.id,
            "credited_amount": request.amount,
            "new_balance": account.outstanding_amount if account else Decimal("0"),
            "new_available_credit": account.available_limit if account else Decimal("0"),
            "posted_at": _utcnow(),
        }
