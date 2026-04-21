import uuid
import calendar
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.models.card_issuance import Card, CreditAccount
from app.models.billing import Bill, Statement, StatementLineItem, Payment
from app.models.transactions.transactions import Transaction
from app.models.transactions.fees import Fee
from app.models.transactions.enums import TransactionStatus, LineItemType, PaymentStatus
from app.models.enums import AccountStatus
from app.core.app_error import AppError

class BillingEngine:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    async def generate_bill(db: AsyncSession, account_id: str, cycle_end_str: str) -> dict:
        acc_uuid = uuid.UUID(account_id)
        
        parsed_dt = datetime.strptime(cycle_end_str, "%Y-%m-%d").date()
        # Default rigidly to last day of specified month
        last_day = calendar.monthrange(parsed_dt.year, parsed_dt.month)[1]
        cycle_date = date(parsed_dt.year, parsed_dt.month, last_day)
        
        if cycle_date > BillingEngine._utcnow().date():
            raise AppError("INVALID_CYCLE_DATE", "Cycle end date cannot be evaluated in the future.", 400)
        
        stmt = select(CreditAccount).where(CreditAccount.id == acc_uuid)
        acc = (await db.execute(stmt)).scalar_one_or_none()
        if not acc:
            raise AppError("ACCOUNT_NOT_FOUND", "Account not found", 404)
        
        cycle_end_dt = datetime.combine(cycle_date, datetime.min.time(), tzinfo=timezone.utc)
        stmt_dup = select(Bill).where(
            and_(Bill.account_id == acc_uuid, Bill.billing_cycle_end == cycle_end_dt)
        )
        if (await db.execute(stmt_dup)).scalar_one_or_none():
            raise AppError("BILL_ALREADY_GENERATED", "Bill already exists for this cycle", 409)

        cycle_start = cycle_date - timedelta(days=30)
        cycle_start_dt = datetime.combine(cycle_start, datetime.min.time(), tzinfo=timezone.utc)
        
        stmt_cards = select(Card).where(Card.credit_account_id == acc.id)
        cards = (await db.execute(stmt_cards)).scalars().all()
        
        total_new_charges = Decimal("0.0")
        total_foreign_fees = Decimal("0.0")
        total_interest = Decimal("0.0")
        total_other_fees = Decimal("0.0")
        total_credits = Decimal("0.0")
        total_pmts = Decimal("0.0")
        txn_count = 0

        stmt_prev = select(Bill).where(Bill.account_id == acc.id).order_by(Bill.billing_cycle_end.desc()).limit(1)
        prev_bill = (await db.execute(stmt_prev)).scalar_one_or_none()
        previous_balance = prev_bill.total_due if prev_bill else Decimal("0.0")

        new_bill = Bill(
            account_id=acc.id,
            status="GENERATED",
            billing_cycle_start=cycle_start_dt,
            billing_cycle_end=cycle_end_dt,
            previous_balance=previous_balance,
            total_due=Decimal("0.0"),
            min_payment_due=Decimal("0.0"),
            due_date=cycle_end_dt + timedelta(days=21)
        )
        db.add(new_bill)
        await db.flush()

        for card in cards:
            stmt_txns = select(Transaction).where(
                and_(
                    Transaction.card_id == card.id,
                    Transaction.status == TransactionStatus.SETTLED.value,
                    Transaction.created_at >= cycle_start_dt,
                    Transaction.created_at <= cycle_end_dt
                )
            )
            txns = (await db.execute(stmt_txns)).scalars().all()
            
            card_charges = Decimal("0.0")
            card_ff = Decimal("0.0")
            card_credits = Decimal("0.0")
            
            for t in txns:
                t_amt = Decimal(str(t.amount))
                ff_amt = Decimal(str(t.foreign_fee or 0))
                
                if t.transaction_type == "REFUND":
                    card_credits += t_amt
                else:
                    card_charges += t_amt
                    card_ff += ff_amt
                txn_count += 1

            apr = Decimal("0.36")
            avg_daily_bal = previous_balance + (card_charges / 2)
            interest = BillingEngine._quantize((avg_daily_bal * apr / Decimal("365")) * Decimal("30"))
            if interest < 0: interest = Decimal("0.0")
            
            total_new_charges += card_charges
            total_foreign_fees += card_ff
            total_interest += interest
            total_credits += card_credits

        stmt_fees = select(Fee).where(
            and_(
                Fee.account_id == acc.id,
                Fee.status == "POSTED",
                Fee.applied_to_bill_id == None,
                Fee.created_at <= cycle_end_dt
            )
        )
        unapplied_fees = (await db.execute(stmt_fees)).scalars().all()
        for f in unapplied_fees:
            total_other_fees += Decimal(str(f.amount))
            f.applied_to_bill_id = new_bill.id
            db.add(f)

        stmt_pmts = select(Payment).where(
            and_(
                Payment.credit_account_id == acc.id,
                Payment.status == PaymentStatus.POSTED.value,
                Payment.payment_date >= cycle_start,
                Payment.payment_date <= cycle_date
            )
        )
        pmts = (await db.execute(stmt_pmts)).scalars().all()
        for p in pmts:
            total_pmts += Decimal(str(p.amount))
            p.bill_id = new_bill.id
            db.add(p)

        new_bill.new_charges = total_new_charges
        new_bill.foreign_fees_total = total_foreign_fees
        new_bill.interest = total_interest
        new_bill.other_fees = total_other_fees
        new_bill.credits = total_credits
        
        new_bill.total_due = BillingEngine._quantize(
            previous_balance + total_new_charges + total_foreign_fees + total_interest + total_other_fees - total_credits - total_pmts
        )
        if new_bill.total_due < 0:
            new_bill.total_due = Decimal("0.0")

        val_5_percent = BillingEngine._quantize(new_bill.total_due * Decimal("0.05"))
        fees_and_int = total_interest + total_other_fees + total_foreign_fees
        new_bill.min_payment_due = max(Decimal("100.00"), val_5_percent, fees_and_int)
        if new_bill.min_payment_due > new_bill.total_due:
            new_bill.min_payment_due = new_bill.total_due
        
        new_bill.transactions_count = txn_count
        db.add(new_bill)
        await db.commit()
        
        return {
            "bill_id": new_bill.id,
            "account_id": acc.id,
            "status": new_bill.status,
            "billing_cycle_start": new_bill.billing_cycle_start,
            "billing_cycle_end": new_bill.billing_cycle_end,
            "previous_balance": float(new_bill.previous_balance),
            "new_charges": float(new_bill.new_charges),
            "foreign_fees_total": float(new_bill.foreign_fees_total),
            "interest": float(new_bill.interest),
            "other_fees": float(new_bill.other_fees),
            "credits": float(new_bill.credits),
            "total_due": float(new_bill.total_due),
            "min_payment_due": float(new_bill.min_payment_due),
            "due_date": new_bill.due_date,
            "generated_at": new_bill.generated_at,
            "transactions_count": new_bill.transactions_count
        }

    @staticmethod
    async def list_bills(db: AsyncSession, card_id: str, user_id: str, page: int, limit: int, status: Optional[str]) -> dict:
        card_uuid = uuid.UUID(card_id)
        stmt_card = select(Card).where(Card.id == card_uuid)
        card = (await db.execute(stmt_card)).scalar_one_or_none()
        if not card:
            raise AppError("CARD_NOT_FOUND", "Card not found", 404)

        offset = (page - 1) * limit
        query = select(Bill).where(Bill.account_id == card.credit_account_id)
        
        total_stmt = select(func.count()).select_from(query.subquery())
        total = (await db.execute(total_stmt)).scalar_one()
        
        items = (await db.execute(query.offset(offset).limit(limit))).scalars().all()
        
        res_items = []
        for x in items:
            res_items.append({
                "bill_id": x.id,
                "account_id": x.account_id,
                "status": x.status,
                "billing_cycle_start": x.billing_cycle_start,
                "billing_cycle_end": x.billing_cycle_end,
                "total_due": x.total_due,
                "min_payment_due": x.min_payment_due,
                "due_date": x.due_date,
                "generated_at": x.generated_at
            })
            
        return {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max((total + limit - 1) // limit, 1),
            "items": res_items
        }

    @staticmethod
    async def get_bill_detail(db: AsyncSession, bill_id: str, user_id: str) -> dict:
        b_uuid = uuid.UUID(bill_id)
        stmt = select(Bill).where(Bill.id == b_uuid)
        bill = (await db.execute(stmt)).scalar_one_or_none()
        if not bill:
            raise AppError("BILL_NOT_FOUND", "Bill not found", 404)
        
        stmt_pmts = select(Payment).where(Payment.bill_id == b_uuid)
        pmts = (await db.execute(stmt_pmts)).scalars().all()
        
        pmt_list = []
        for p in pmts:
            pmt_list.append({
                "payment_id": p.id,
                "amount": p.amount,
                "paid_at": datetime.combine(p.payment_date, datetime.min.time(), tzinfo=timezone.utc)
            })
            
        return {
            "bill_id": bill.id,
            "account_id": bill.account_id,
            "status": bill.status,
            "billing_cycle_start": bill.billing_cycle_start,
            "billing_cycle_end": bill.billing_cycle_end,
            "previous_balance": bill.previous_balance,
            "new_charges": bill.new_charges,
            "foreign_fees_total": bill.foreign_fees_total,
            "interest": bill.interest,
            "other_fees": bill.other_fees,
            "credits": bill.credits,
            "total_due": bill.total_due,
            "min_payment_due": bill.min_payment_due,
            "due_date": bill.due_date,
            "generated_at": bill.generated_at,
            "transactions": [],
            "payments": pmt_list
        }


class StatementEngine:
    @staticmethod
    async def generate(db: AsyncSession, credit_card_id: str, billing_cycle: str) -> dict:
        raise AppError("NOT_IMPLEMENTED", "Placeholder", 500)
    
    @staticmethod
    async def fetch(db: AsyncSession, credit_card_id: str, user_id: str, cycle: Optional[str], page: int, limit: int) -> dict:
        raise AppError("NOT_IMPLEMENTED", "Placeholder", 500)
