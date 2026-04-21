import uuid
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models.card_issuance import CreditAccount
from app.models.billing import Bill, Payment
from app.models.transactions.enums import PaymentStatus
from app.core.app_error import AppError

class PaymentEngine:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    async def process(db: AsyncSession, credit_account_id: str, bill_id: str, user_id: str, payload) -> dict:
        acc_uuid = uuid.UUID(credit_account_id)
        b_uuid = uuid.UUID(bill_id)
        
        async with db.begin():
            stmt_bill = select(Bill).where(Bill.id == b_uuid).with_for_update()
            bill = (await db.execute(stmt_bill)).scalar_one_or_none()
            if not bill:
                raise AppError("BILL_NOT_FOUND", "Bill not found", 404)
            if bill.account_id != acc_uuid:
                raise AppError("INVALID_ACCOUNT", "Bill does not belong to account", 400)
                
            amount = Decimal(str(payload.amount))
            ptype = payload.payment_type
            
            total_due = Decimal(str(bill.total_due))
            min_due = Decimal(str(bill.min_payment_due))
            
            if ptype == "FULL" and amount != total_due:
                raise AppError("INVALID_PAYMENT_AMOUNT", f"FULL payment must be exactly {total_due}", 400)
            if ptype == "MINIMUM" and amount != min_due:
                raise AppError("INVALID_PAYMENT_AMOUNT", f"MINIMUM payment must be exactly {min_due}", 400)
            if ptype == "PARTIAL":
                 if amount <= min_due or amount >= total_due:
                     raise AppError("INVALID_PAYMENT_AMOUNT", f"PARTIAL must be between {min_due} and {total_due}", 400)

            # Record Payment
            pmt = Payment(
                credit_account_id=acc_uuid,
                bill_id=b_uuid,
                amount=amount,
                payment_date=PaymentEngine._utcnow().date(),
                payment_method="DIRECT",
                reference_number=str(uuid.uuid4())[:8],
                status=PaymentStatus.POSTED.value
            )
            db.add(pmt)
            
            # Update Account & Bill
            stmt_acc = select(CreditAccount).where(CreditAccount.id == acc_uuid).with_for_update()
            acc = (await db.execute(stmt_acc)).scalar_one()
            
            available_before = acc.available_limit
            acc.available_limit += amount
            acc.outstanding_amount -= amount
            if acc.outstanding_amount < 0:
                acc.outstanding_amount = Decimal("0.0")
            
            bill.total_due -= amount
            if bill.total_due <= 0:
                bill.total_due = Decimal("0.0")
                bill.status = "PAID"
            elif ptype == "FULL" or bill.total_due <= 0:
                bill.status = "PAID"
            
            await db.flush()
            
            is_full = True if ptype == "FULL" or bill.total_due <= 0 else False
            
            return {
                "payment_id": pmt.id,
                "card_id": uuid.uuid4(),  # Mock linking since mock spec didn't specify strict card fetch here
                "bill_id": bill.id,
                "amount_paid": amount,
                "previous_balance": total_due,
                "new_balance": bill.total_due,
                "available_credit_before": available_before,
                "available_credit_after": acc.available_limit,
                "bill_status": bill.status,
                "remaining_due": bill.total_due,
                "is_full_payment": is_full,
                "timestamp": PaymentEngine._utcnow()
            }
