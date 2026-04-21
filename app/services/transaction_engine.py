import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from calendar import monthrange
from typing import Optional

from sqlalchemy import select, text, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models.card_issuance import Card, CreditAccount
from app.models.transactions.transactions import Transaction, CreditHold, IdempotencyLog
from app.models.transactions.enums import TransactionStatus, HoldStatus
from app.models.transactions.controls import ProhibitedCountry
from app.services.velocity_service import VelocityService, FraudService
from app.core.app_error import AppError

import string
import random

class TransactionEngine:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    async def authorize(
        db: AsyncSession,
        credit_card_id: str,
        user_id: str,
        idempotency_key: str,
        payload
    ) -> dict:
        now = TransactionEngine._utcnow()
        error_to_raise = None
        resp_obj = None

        card_uuid = uuid.UUID(credit_card_id)

        # Idempotency check with serializable read
        async with db.begin():
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            cutoff = now - timedelta(hours=24)
            stmt_idemp = select(IdempotencyLog).where(
                IdempotencyLog.idempotency_key == idempotency_key,
                IdempotencyLog.created_at >= cutoff
            )
            existing_idemp = (await db.execute(stmt_idemp)).scalar_one_or_none()
            if existing_idemp and existing_idemp.response_body:
                error_to_raise = ("DUPLICATE_IDEMPOTENCY_KEY", "Request already processed", 409)

        if error_to_raise:
            from app.core.exceptions import IdempotencyConflictError
            raise IdempotencyConflictError(error_to_raise[1])

        # Main atomic transaction
        async with db.begin():
            try:
                # 1. Lock Card
                stmt_card = select(Card).where(Card.id == card_uuid).with_for_update()
                card = (await db.execute(stmt_card)).scalar_one_or_none()
                if not card:
                    raise AppError("CARD_NOT_FOUND", f"Card ID {credit_card_id} not found", 404)

                if str(card.card_status) != "ACTIVE" and getattr(card.card_status, "value", card.card_status) != "ACTIVE":
                    raise AppError("CARD_BLOCKED", f"Card ID {credit_card_id} is currently BLOCKED", 403)

                if card.expiry_date:
                    try:
                        parts = card.expiry_date.split("/")
                        exp_m = int(parts[0])
                        exp_y = int(parts[1]) if len(parts[1]) == 4 else int("20" + parts[1])
                        last_day = monthrange(exp_y, exp_m)[1]
                        expiry_dt = datetime(exp_y, exp_m, last_day).date()
                        if expiry_dt < now.date():
                            raise AppError("CARD_EXPIRED", f"Card ID {credit_card_id} has expired", 403)
                    except Exception:
                        pass

                # 2. Check Prohibited Country
                merchant_country = payload.merchant_country.upper()
                stmt_proh = select(ProhibitedCountry).where(ProhibitedCountry.country_code == merchant_country)
                prohibited = (await db.execute(stmt_proh)).scalar_one_or_none()
                if prohibited and prohibited.restriction_type == "PROHIBITED":
                     raise AppError("FORBIDDEN", "IF MERCHAND COUNTRY IS ONE OF THE PROHIBITTED COUNTRIES THEN TRANSACTION IS FORBIDDEN", 403)

                # 3. Lock Account
                stmt_account = select(CreditAccount).where(CreditAccount.id == card.credit_account_id).with_for_update()
                account = (await db.execute(stmt_account)).scalar_one_or_none()
                if not account:
                    raise AppError("ACCOUNT_NOT_FOUND", "No account linked", 404)

                # 4. Compute foreign fee
                is_foreign = False
                foreign_fee = Decimal("0.0")
                amount = Decimal(str(payload.amount))
                if merchant_country != account.home_country.upper():
                    is_foreign = True
                    foreign_fee = amount * Decimal("0.03")

                hold_amount = amount + foreign_fee
                available_before = account.available_limit

                # 5. Check limit
                if available_before < hold_amount:
                    raise AppError("INSUFFICIENT_CREDIT", f"Available credit ₹{available_before} is less than required ₹{hold_amount}", 402)

                # 6. Velocity and Fraud
                try:
                    VelocityService.check_velocity(account.id, hold_amount)
                except Exception as ve:
                    if 'velocity' in str(ve).lower():
                        raise AppError("VELOCITY_EXCEEDED", "Velocity limits exceeded", 429)
                
                fraud_result = FraudService.run_fraud_checks(None, card.id, amount, payload.merchant.upper())
                if fraud_result.get("flagged"):
                    raise AppError("FRAUD_DETECTED", "Transaction flagged", 403)

                # 7. Create authorization
                auth_code_generated = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
                
                txn = Transaction(
                    card_id=card.id,
                    account_id=account.id,
                    amount=amount,
                    currency="INR",
                    transaction_type=payload.category,
                    status=TransactionStatus.AUTHORIZED.value,
                    merchant_name=payload.merchant,
                    merchant_country=merchant_country,
                    is_foreign=is_foreign,
                    foreign_fee=foreign_fee,
                    auth_code=auth_code_generated,
                    idempotency_key=idempotency_key,
                    metadata_json={"description": payload.description} if payload.description else None
                )
                db.add(txn)
                await db.flush()

                # 8. Create Hold
                hold = CreditHold(
                    transaction_id=txn.id,
                    card_id=card.id,
                    amount=hold_amount,
                    currency="INR",
                    status=HoldStatus.ACTIVE.value,
                    hold_expiry=now + timedelta(days=7)
                )
                db.add(hold)

                # 9. Update Account
                account.available_limit -= hold_amount
                account.outstanding_amount += hold_amount
                available_after = account.available_limit
                db.add(account)
                
                # 10. Record idempotency log
                resp_obj = {
                    "transaction_id": str(txn.id),
                    "account_id": str(account.id),
                    "status": "AUTHORIZED",
                    "amount": float(amount),
                    "foreign_fee": float(foreign_fee),
                    "hold_amount": float(hold_amount),
                    "merchant": payload.merchant,
                    "category": payload.category,
                    "merchant_country": merchant_country,
                    "is_foreign": is_foreign,
                    "authorization_code": auth_code_generated,
                    "available_credit_before": float(available_before),
                    "available_credit_after": float(available_after),
                    "idempotency_key": idempotency_key,
                    "timestamp": now.isoformat()
                }

                log_entry = IdempotencyLog(
                    idempotency_key=idempotency_key,
                    transaction_id=txn.id,
                    created_at=now,
                    response_body=resp_obj
                )
                db.add(log_entry)
                
            except Exception as e:
                await db.rollback()
                raise e
            
        VelocityService.record_transaction(account.id, hold_amount)
        return resp_obj

    @staticmethod
    async def query_transactions(
        db: AsyncSession,
        credit_card_id: str,
        user_id: str,
        params: dict
    ) -> dict:
        card_uuid = uuid.UUID(credit_card_id)
        query = select(Transaction).where(Transaction.card_id == card_uuid)
        
        # Exact matching query
        if params.get("transaction_id"):
            query = query.where(Transaction.id == params["transaction_id"])
            
        if params.get("amount_min") is not None:
            query = query.where(Transaction.amount >= Decimal(params["amount_min"]))
        if params.get("amount_max") is not None:
            query = query.where(Transaction.amount <= Decimal(params["amount_max"]))
        if params.get("merchant"):
            query = query.where(Transaction.merchant_name.ilike(f"%{params['merchant']}%"))
        if params.get("category"):
            query = query.where(Transaction.transaction_type == params["category"])
        if params.get("status"):
            query = query.where(Transaction.status == params["status"])
        if params.get("date_from"):
            dt_from = datetime.strptime(params["date_from"], "%Y-%m-%d").date()
            query = query.where(func.date(Transaction.created_at) >= dt_from)
        if params.get("date_to"):
            dt_to = datetime.strptime(params["date_to"], "%Y-%m-%d").date()
            query = query.where(func.date(Transaction.created_at) <= dt_to)

        # Ordering
        sort_by = params.get("sort_by", "timestamp")
        order = params.get("order", "desc")
        
        sort_col = Transaction.created_at
        if sort_by == "amount":
            sort_col = Transaction.amount
        elif sort_by == "merchant":
            sort_col = Transaction.merchant_name
            
        if order == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())

        total_stmt = select(func.count()).select_from(query.subquery())
        total = (await db.execute(total_stmt)).scalar_one()

        limit = params.get("limit", 20)
        page = params.get("page", 1)
        offset = (page - 1) * limit
        
        query = query.offset(offset).limit(limit)
        results = (await db.execute(query)).scalars().all()
        
        items = []
        for r in results:
            items.append({
                "transaction_id": str(r.id),
                "account_id": str(r.account_id),
                "card_id": str(r.card_id),
                "amount": float(r.amount),
                "foreign_fee": float(r.foreign_fee or Decimal("0.0")),
                "hold_amount": float(r.amount + (r.foreign_fee or Decimal("0.0"))),
                "merchant": r.merchant_name,
                "category": r.transaction_type,
                "merchant_country": r.merchant_country,
                "is_foreign": r.is_foreign,
                "status": str(r.status),
                "authorization_code": r.auth_code,
                "description": r.metadata_json.get("description") if r.metadata_json else None,
                "timestamp": r.created_at
            })
            
        return {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit,
            "sort_by": sort_by,
            "order": order,
            "items": items
        }
