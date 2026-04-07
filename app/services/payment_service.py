"""
Payment Service (RBI Waterfall) — Week 5

Implements the strict RBI-mandated payment allocation waterfall:
    1. Fees & Charges
    2. Interest
    3. Cash Advance Principal
    4. Purchase Principal

All allocations are tracked atomically on the Payment record.
Statement status is updated to PAID/PARTIALLY_PAID as appropriate.
"""
import uuid
import logging
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.admin.models.card_issuance import Card, CreditAccount
from app.models.billing import Statement, Payment
from app.models.transactions.enums import PaymentStatus, StatementStatus
from app.models.enums import CardStatus
from app.core.exceptions import (
    PaymentNotFoundError,
    CardNotActiveError,
    AccountNotActiveError,
)

logger = logging.getLogger("zbanque.payments")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PaymentWaterfallService:
    """
    Processes credit card payments using the RBI waterfall allocation order.
    """

    @staticmethod
    def process_payment(
        db: Session,
        card_id: uuid.UUID,
        amount: Decimal,
        payment_source: str,
        reference_no: str,
        payment_date: date | None = None,
        created_by: uuid.UUID | None = None,
    ) -> Payment:
        """
        Process a payment with full RBI waterfall allocation.

        Waterfall Order:
            1. Fees & charges (from outstanding Statement.total_fees)
            2. Interest (from outstanding Statement.total_interest)
            3. Cash advance principal (from outstanding Statement.total_cash_advances)
            4. Purchase principal (from outstanding Statement.total_purchases)

        After allocation:
            - Payment record is created with line-by-line breakdown
            - Credit account balances are updated atomically
            - Statement status transitions (BILLED → PAID / PARTIALLY_PAID)
        """
        # ── Validate card ──
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:
            raise CardNotActiveError(card_id, "NOT_FOUND")

        account = db.query(CreditAccount).filter(
            CreditAccount.id == card.credit_account_id
        ).first()
        if not account:
            raise AccountNotActiveError(card_id, "NO_ACCOUNT")

        pay_date = payment_date or date.today()

        # ── Find the latest BILLED/OVERDUE/PARTIALLY_PAID statement ──
        stmt = db.query(Statement).filter(
            and_(
                Statement.card_id == card_id,
                Statement.status.in_([
                    StatementStatus.BILLED.value,
                    StatementStatus.OVERDUE.value,
                    StatementStatus.PARTIALLY_PAID.value,
                ]),
            )
        ).order_by(Statement.cycle_end.desc()).first()

        # ── RBI Waterfall Allocation ──
        remaining = amount
        alloc_fees = Decimal("0")
        alloc_interest = Decimal("0")
        alloc_cash_advance = Decimal("0")
        alloc_purchases = Decimal("0")

        if stmt:
            # 1. Fees & Charges
            outstanding_fees = max(stmt.total_fees - _already_allocated(db, stmt.id, "fees"), Decimal("0"))
            alloc_fees = _quantize(min(remaining, outstanding_fees))
            remaining -= alloc_fees

            # 2. Interest
            outstanding_interest = max(stmt.total_interest - _already_allocated(db, stmt.id, "interest"), Decimal("0"))
            alloc_interest = _quantize(min(remaining, outstanding_interest))
            remaining -= alloc_interest

            # 3. Cash Advance Principal
            outstanding_ca = max(stmt.total_cash_advances - _already_allocated(db, stmt.id, "cash_advance"), Decimal("0"))
            alloc_cash_advance = _quantize(min(remaining, outstanding_ca))
            remaining -= alloc_cash_advance

            # 4. Purchase Principal
            outstanding_purchases = max(
                stmt.total_purchases - _already_allocated(db, stmt.id, "purchases"),
                Decimal("0"),
            )
            alloc_purchases = _quantize(min(remaining, outstanding_purchases))
            remaining -= alloc_purchases

            # Any remaining goes to general principal reduction
            if remaining > 0:
                alloc_purchases += _quantize(remaining)

        else:
            # No open statement — apply directly as general credit
            alloc_purchases = amount

        # ── Create Payment record ──
        payment = Payment(
            credit_account_id=account.id,
            card_id=card_id,
            statement_id=stmt.id if stmt else None,
            amount=amount,
            payment_source=payment_source,
            reference_no=reference_no,
            status=PaymentStatus.POSTED.value,
            allocated_fees=alloc_fees,
            allocated_interest=alloc_interest,
            allocated_cash_advance=alloc_cash_advance,
            allocated_purchases=alloc_purchases,
            payment_date=pay_date,
            posted_at=_utcnow(),
            created_by=created_by,
        )
        db.add(payment)

        # ── Update credit account balances ──
        account.outstanding_amount = max(
            Decimal(str(account.outstanding_amount)) - amount,
            Decimal("0"),
        )
        account.available_limit = min(
            Decimal(str(account.available_limit)) + amount,
            Decimal(str(account.credit_limit)),
        )

        # ── Update statement status ──
        if stmt:
            total_paid_for_stmt = db.query(
                func.coalesce(func.sum(Payment.amount), Decimal("0"))
            ).filter(
                and_(
                    Payment.statement_id == stmt.id,
                    Payment.status == PaymentStatus.POSTED.value,
                )
            ).scalar()
            total_paid_for_stmt = Decimal(str(total_paid_for_stmt)) + amount

            if total_paid_for_stmt >= stmt.total_amount_due:
                stmt.status = StatementStatus.PAID.value
                stmt.total_payments = total_paid_for_stmt
            elif total_paid_for_stmt >= stmt.minimum_due:
                stmt.status = StatementStatus.PARTIALLY_PAID.value
                stmt.total_payments = total_paid_for_stmt
            else:
                stmt.total_payments = total_paid_for_stmt

        db.commit()
        db.refresh(payment)

        logger.info(
            "Payment %s processed: ₹%s → fees=%s interest=%s ca=%s purchases=%s",
            payment.id, amount, alloc_fees, alloc_interest, alloc_cash_advance, alloc_purchases,
        )

        return payment


def _already_allocated(db: Session, statement_id: uuid.UUID, bucket: str) -> Decimal:
    """Sum previously allocated amounts for a specific waterfall bucket on a statement."""
    col_map = {
        "fees": Payment.allocated_fees,
        "interest": Payment.allocated_interest,
        "cash_advance": Payment.allocated_cash_advance,
        "purchases": Payment.allocated_purchases,
    }
    col = col_map.get(bucket, Payment.allocated_purchases)
    result = db.query(func.coalesce(func.sum(col), Decimal("0"))).filter(
        and_(
            Payment.statement_id == statement_id,
            Payment.status == PaymentStatus.POSTED.value,
        )
    ).scalar()
    return Decimal(str(result))
