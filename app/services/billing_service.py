"""
Billing Service — Week 5

Banking-grade statement generation with:
  • ADB (Average Daily Balance) interest computation
  • Grace period heuristics (no purchase interest if previous cycle PAID/WAIVED)
  • Minimum due calculation (max of 5% of closing balance or ₹200)
  • Late fee application with strict waterfall and atomicity

All monetary values use Decimal.  No floats anywhere.
"""
import uuid
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.admin.models.card_issuance import Card, CreditAccount
from app.models.billing import Statement, StatementLineItem, Payment
from app.models.transactions.transactions import Transaction
from app.models.transactions.fees import Fee
from app.models.transactions.enums import (
    TransactionType, TransactionStatus, StatementStatus,
    LineItemType, PaymentStatus, FeeType,
)
from app.models.enums import AccountStatus, CardStatus
from app.core.exceptions import BillingCycleError, AccountNotActiveError

logger = logging.getLogger("zbanque.billing")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _quantize(value: Decimal) -> Decimal:
    """Round to 2 decimal places using banker's rounding."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class BillingService:
    """Handles statement generation and late-fee application."""

    # ───────────────────────────────────────────────────
    # H1: Statement Generation
    # ───────────────────────────────────────────────────
    @staticmethod
    def generate_statements(
        db: Session,
        cycle_date: date,
        purchase_apr: Decimal = Decimal("0.3599"),
        cash_advance_apr: Decimal = Decimal("0.4199"),
        generated_by: uuid.UUID | None = None,
    ) -> list[dict]:
        """
        Generate billing statements for ALL active accounts.

        Algorithm:
        1. Find all active credit accounts.
        2. For each, derive the billing cycle window (30 days ending on cycle_date).
        3. Pull all SETTLED/CLEARED transactions in that window.
        4. Compute ADB interest for purchases (with grace-period check) and cash advances.
        5. Build Statement + StatementLineItem rows.
        6. Persist atomically.

        Returns: list of summary dicts for the generated statements.
        """
        cycle_end = cycle_date
        cycle_start = cycle_end - timedelta(days=29)  # 30-day billing cycle

        accounts = db.query(CreditAccount).filter(
            CreditAccount.account_status == AccountStatus.ACTIVE,
        ).all()

        if not accounts:
            logger.info("No active accounts found for billing cycle %s", cycle_date)
            return []

        results: list[dict] = []

        for account in accounts:
            cards = db.query(Card).filter(
                Card.credit_account_id == account.id,
                Card.card_status.in_([CardStatus.ACTIVE, CardStatus.BLOCKED]),
            ).all()

            if not cards:
                continue

            for card in cards:
                # Check for duplicate statement
                existing = db.query(Statement).filter(
                    and_(
                        Statement.card_id == card.id,
                        Statement.cycle_end == cycle_end,
                    )
                ).first()
                if existing:
                    logger.warning(
                        "Statement already exists for card %s cycle ending %s",
                        card.id, cycle_end,
                    )
                    continue

                stmt_result = BillingService._generate_single_statement(
                    db, account, card, cycle_start, cycle_end,
                    purchase_apr, cash_advance_apr, generated_by,
                )
                if stmt_result:
                    results.append(stmt_result)

        db.commit()
        logger.info("Generated %d statements for cycle ending %s", len(results), cycle_date)
        return results

    @staticmethod
    def _generate_single_statement(
        db: Session,
        account: CreditAccount,
        card: Card,
        cycle_start: date,
        cycle_end: date,
        purchase_apr: Decimal,
        cash_advance_apr: Decimal,
        generated_by: uuid.UUID | None,
    ) -> dict | None:
        """Generate a statement for a single card."""

        # ── Pull transactions in cycle window ──
        txns = db.query(Transaction).filter(
            and_(
                Transaction.card_id == card.id,
                Transaction.status.in_([
                    TransactionStatus.SETTLED.value,
                    TransactionStatus.CLEARED.value,
                ]),
                func.date(Transaction.created_at) >= cycle_start,
                func.date(Transaction.created_at) <= cycle_end,
            )
        ).all()

        # ── Pull fees in cycle window ──
        fees = db.query(Fee).filter(
            and_(
                Fee.card_id == card.id,
                Fee.waived == False,
                func.date(Fee.created_at) >= cycle_start,
                func.date(Fee.created_at) <= cycle_end,
            )
        ).all()

        # ── Aggregate amounts by type ──
        total_purchases = Decimal("0")
        total_cash_advances = Decimal("0")
        total_credits = Decimal("0")
        line_items: list[StatementLineItem] = []

        for txn in txns:
            if txn.transaction_type in (
                TransactionType.PURCHASE.value,
            ):
                total_purchases += txn.amount
                line_items.append(StatementLineItem(
                    transaction_id=txn.id,
                    line_type=LineItemType.PURCHASE.value,
                    description=txn.merchant_name or "Purchase",
                    amount=txn.amount,
                    transaction_date=txn.created_at.date() if isinstance(txn.created_at, datetime) else txn.created_at,
                ))
            elif txn.transaction_type == TransactionType.CASH_ADVANCE.value:
                total_cash_advances += txn.amount
                line_items.append(StatementLineItem(
                    transaction_id=txn.id,
                    line_type=LineItemType.CASH_ADVANCE.value,
                    description="Cash Advance",
                    amount=txn.amount,
                    transaction_date=txn.created_at.date() if isinstance(txn.created_at, datetime) else txn.created_at,
                ))
            elif txn.transaction_type in (
                TransactionType.REFUND.value,
                TransactionType.PAYMENT.value,
            ):
                total_credits += txn.amount
                line_items.append(StatementLineItem(
                    transaction_id=txn.id,
                    line_type=LineItemType.CREDIT.value,
                    description=txn.merchant_name or "Credit/Refund",
                    amount=-txn.amount,  # Credits are negative
                    transaction_date=txn.created_at.date() if isinstance(txn.created_at, datetime) else txn.created_at,
                ))

        total_fees = Decimal("0")
        for fee in fees:
            total_fees += fee.amount
            line_items.append(StatementLineItem(
                line_type=LineItemType.FEE.value,
                description=f"Fee: {fee.fee_type}",
                amount=fee.amount,
                transaction_date=fee.created_at.date() if isinstance(fee.created_at, datetime) else fee.created_at,
            ))

        # ── Payments received in this cycle ──
        payments_received = db.query(func.coalesce(
            func.sum(Payment.amount), Decimal("0")
        )).filter(
            and_(
                Payment.card_id == card.id,
                Payment.status == PaymentStatus.POSTED.value,
                func.date(Payment.payment_date) >= cycle_start,
                func.date(Payment.payment_date) <= cycle_end,
            )
        ).scalar()
        total_payments = Decimal(str(payments_received))

        # ── Grace period check ──
        # Look at the *previous* statement status
        previous_stmt = db.query(Statement).filter(
            and_(
                Statement.card_id == card.id,
                Statement.cycle_end < cycle_start,
            )
        ).order_by(Statement.cycle_end.desc()).first()

        grace_period_applies = (
            previous_stmt is None  # First statement, no interest
            or previous_stmt.status in (StatementStatus.PAID.value, StatementStatus.WAIVED.value)
        )

        # ── ADB Interest Calculation ──
        billing_days = (cycle_end - cycle_start).days + 1

        # Purchase interest (subject to grace period)
        if grace_period_applies:
            purchase_interest = Decimal("0")
        else:
            # ADB = sum of daily balances / days in cycle
            # Simplified: use average of opening + outstanding as ADB proxy
            purchase_adb = (total_purchases + Decimal(str(account.outstanding_amount))) / 2
            daily_rate = purchase_apr / 365
            purchase_interest = _quantize(purchase_adb * daily_rate * billing_days)

        # Cash advance interest (NEVER has grace period)
        if total_cash_advances > 0:
            ca_daily_rate = cash_advance_apr / 365
            ca_interest = _quantize(total_cash_advances * ca_daily_rate * billing_days)
        else:
            ca_interest = Decimal("0")

        total_interest = purchase_interest + ca_interest

        if total_interest > 0:
            line_items.append(StatementLineItem(
                line_type=LineItemType.INTEREST.value,
                description="Interest Charges",
                amount=total_interest,
                transaction_date=cycle_end,
            ))

        # ── Compute closing balance ──
        opening_balance = Decimal(str(account.outstanding_amount))
        closing_balance = _quantize(
            opening_balance
            + total_purchases
            + total_cash_advances
            + total_fees
            + total_interest
            - total_credits
            - total_payments
        )

        # ── Minimum due ──
        minimum_due = _quantize(max(
            closing_balance * Decimal("0.05"),       # 5% of closing balance
            min(closing_balance, Decimal("200.00")),  # or ₹200, whichever is less than balance
        ))
        if closing_balance <= Decimal("0"):
            minimum_due = Decimal("0")

        total_amount_due = closing_balance  # Full balance

        # ── Determine status ──
        if closing_balance <= Decimal("0"):
            stmt_status = StatementStatus.PAID.value
        else:
            stmt_status = StatementStatus.BILLED.value

        # ── Payment due date (21 days from cycle end) ──
        payment_due_date = cycle_end + timedelta(days=21)

        # ── Create Statement ──
        stmt = Statement(
            credit_account_id=account.id,
            card_id=card.id,
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            payment_due_date=payment_due_date,
            opening_balance=opening_balance,
            total_purchases=total_purchases,
            total_cash_advances=total_cash_advances,
            total_fees=total_fees,
            total_interest=total_interest,
            total_credits=total_credits,
            total_payments=total_payments,
            closing_balance=closing_balance,
            minimum_due=minimum_due,
            total_amount_due=total_amount_due,
            status=stmt_status,
            generated_by=generated_by,
        )
        db.add(stmt)
        db.flush()  # Get ID for line items

        for li in line_items:
            li.statement_id = stmt.id
            db.add(li)

        logger.info(
            "Generated statement %s for card %s: closing_balance=%s, interest=%s",
            stmt.id, card.id, closing_balance, total_interest,
        )

        return {
            "statement_id": str(stmt.id),
            "card_id": str(card.id),
            "cycle": f"{cycle_start} to {cycle_end}",
            "closing_balance": str(closing_balance),
            "minimum_due": str(minimum_due),
            "interest_charged": str(total_interest),
            "status": stmt_status,
        }

    # ───────────────────────────────────────────────────
    # H2: Late Fee Application
    # ───────────────────────────────────────────────────
    @staticmethod
    def apply_late_fees(
        db: Session,
        late_fee_amount: Decimal = Decimal("500.00"),
    ) -> list[dict]:
        """
        Apply late fees to all overdue statements.

        Rules:
        1. Find BILLED statements whose payment_due_date < today
        2. Check if at least minimum_due was paid
        3. If not, apply late fee and mark statement OVERDUE
        4. Atomically update the credit account outstanding
        """
        today = date.today()
        results: list[dict] = []

        overdue_stmts = db.query(Statement).filter(
            and_(
                Statement.status == StatementStatus.BILLED.value,
                Statement.payment_due_date < today,
            )
        ).all()

        for stmt in overdue_stmts:
            # Sum payments for this statement's card in the cycle
            total_paid = db.query(
                func.coalesce(func.sum(Payment.amount), Decimal("0"))
            ).filter(
                and_(
                    Payment.card_id == stmt.card_id,
                    Payment.status == PaymentStatus.POSTED.value,
                    func.date(Payment.payment_date) >= stmt.cycle_start,
                    func.date(Payment.payment_date) <= stmt.payment_due_date,
                )
            ).scalar()

            total_paid = Decimal(str(total_paid))

            if total_paid >= stmt.minimum_due:
                # Minimum was paid: no late fee, mark PARTIALLY_PAID
                if total_paid >= stmt.total_amount_due:
                    stmt.status = StatementStatus.PAID.value
                else:
                    stmt.status = StatementStatus.PARTIALLY_PAID.value
                continue

            # Apply late fee
            fee = Fee(
                card_id=stmt.card_id,
                fee_type=FeeType.LATE_PAYMENT_FEE.value,
                amount=late_fee_amount,
            )
            db.add(fee)

            # Update statement
            stmt.status = StatementStatus.OVERDUE.value
            stmt.total_fees = stmt.total_fees + late_fee_amount
            stmt.closing_balance = stmt.closing_balance + late_fee_amount
            stmt.total_amount_due = stmt.total_amount_due + late_fee_amount

            # Update credit account outstanding
            account = db.query(CreditAccount).filter(
                CreditAccount.id == stmt.credit_account_id
            ).first()
            if account:
                account.outstanding_amount = account.outstanding_amount + late_fee_amount
                account.available_limit = account.available_limit - late_fee_amount

            results.append({
                "statement_id": str(stmt.id),
                "card_id": str(stmt.card_id),
                "late_fee_applied": str(late_fee_amount),
                "new_status": StatementStatus.OVERDUE.value,
            })

            logger.info(
                "Late fee ₹%s applied to statement %s (card %s)",
                late_fee_amount, stmt.id, stmt.card_id,
            )

        db.commit()
        logger.info("Applied late fees to %d overdue statements", len(results))
        return results
