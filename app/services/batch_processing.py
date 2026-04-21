import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transactions.transactions import Transaction
from app.models.transactions.enums import TransactionStatus
from app.core.app_error import AppError

class BatchProcessingEngine:
    @staticmethod
    async def process_clearing(db: AsyncSession, cycle_date_str: str, user_id: str) -> dict:
        cycle_date = datetime.strptime(cycle_date_str, "%Y-%m-%d").date()
        dt_start = datetime.combine(cycle_date, datetime.min.time(), tzinfo=timezone.utc)
        dt_end = dt_start + timedelta(days=1)

        stmt = select(Transaction).where(
            and_(
                Transaction.status == TransactionStatus.AUTHORIZED.value,
                Transaction.created_at >= dt_start,
                Transaction.created_at < dt_end
            )
        )
        txns = (await db.execute(stmt)).scalars().all()
        
        amt = Decimal("0.0")
        for t in txns:
            t.status = TransactionStatus.CLEARED.value
            amt += t.amount
            
        await db.commit()
        return {
            "job_name": "process_clearing",
            "run_at": datetime.now(timezone.utc),
            "cycle_date": cycle_date_str,
            "transactions_cleared": len(txns),
            "total_amount_cleared": amt,
            "accounts_affected": len(set([t.account_id for t in txns])),
            "errors": []
        }

    @staticmethod
    async def process_settlement(db: AsyncSession, settlement_date_str: str, request, user_id: str) -> dict:
        stmt = select(Transaction).where(Transaction.status == TransactionStatus.CLEARED.value)
        txns = (await db.execute(stmt)).scalars().all()
        
        amt = Decimal("0.0")
        for t in txns:
            t.status = TransactionStatus.SETTLED.value
            amt += t.amount
            
        net = amt * Decimal("0.98") # Net issuer obligation mock
        await db.commit()
        return {
            "settlement_id": uuid.uuid4(),
            "settlement_date": datetime.strptime(settlement_date_str, "%Y-%m-%d").date(),
            "transactions_settled": len(txns),
            "total_settled_amount": amt,
            "net_issuer_obligation": net,
            "status": "COMPLETED",
            "processed_at": datetime.now(timezone.utc),
            "errors": []
        }
