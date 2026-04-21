import uuid
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models.card_issuance import Card
from app.models.transactions.fees import Fee
from app.core.app_error import AppError

class FeeEvaluator:
    @staticmethod
    async def assess_fee(db: AsyncSession, credit_card_id: str, request, user_id: str) -> dict:
        card_uuid = uuid.UUID(credit_card_id)
        stmt = select(Card).where(Card.id == card_uuid)
        card = (await db.execute(stmt)).scalar_one_or_none()
        if not card:
            raise AppError("CARD_NOT_FOUND", "Card not found", 404)
            
        fee_amt = Decimal(str(request.amount))
        f = Fee(
            account_id=card.credit_account_id,
            card_id=card.id,
            fee_type=request.fee_type,
            amount=fee_amt,
            status="POSTED",
            description=request.reason
        )
        db.add(f)
        await db.commit()
        return {
            "fee_id": f.id,
            "card_id": card_uuid,
            "account_id": card.credit_account_id,
            "fee_type": request.fee_type,
            "amount": fee_amt,
            "reason": request.reason,
            "status": "POSTED",
            "applied_to_bill": None,
            "assessed_at": datetime.now(timezone.utc),
            "assessed_by": user_id
        }
