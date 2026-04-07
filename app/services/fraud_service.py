"""
Fraud Detection Service — Week 5

Transaction-level fraud detection with three heuristics:
  1. Velocity Gate     — Hard decline (>5 txns in 60s window)
  2. Amount Spike      — Soft flag  (>3× the 30-day average)
  3. Unusual Hour      — Soft flag  (transactions between 01:00–05:00 local)

Hard declines raise FraudDeclinedError (HTTP 403).
Soft flags create FraudFlag records + set Transaction.risk_flag = True.
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models.billing import FraudFlag
from app.models.transactions.transactions import Transaction
from app.models.transactions.enums import TransactionStatus
from app.core.exceptions import FraudDeclinedError

logger = logging.getLogger("zbanque.fraud")


class FraudService:
    """Transaction-level fraud detection engine."""

    @staticmethod
    def run_fraud_checks(
        db: Session,
        card_id: uuid.UUID,
        amount: Decimal,
        transaction_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """
        Execute all fraud heuristics against a pending transaction.

        Returns a list of triggered check results.
        Raises FraudDeclinedError for hard-decline rules.
        """
        results: list[dict] = []
        now = datetime.now(timezone.utc)

        # ── Heuristic 1: Velocity Gate (HARD DECLINE) ──
        sixty_seconds_ago = now - timedelta(seconds=60)
        recent_count = db.query(func.count(Transaction.id)).filter(
            and_(
                Transaction.card_id == card_id,
                Transaction.created_at >= sixty_seconds_ago,
                Transaction.status != TransactionStatus.DECLINED.value,
            )
        ).scalar()

        if recent_count >= 5:
            logger.warning(
                "FRAUD HARD DECLINE: Velocity gate triggered for card %s "
                "(%d transactions in 60s)",
                card_id, recent_count,
            )
            # Create fraud flag record
            flag = FraudFlag(
                transaction_id=transaction_id or uuid.uuid4(),
                card_id=card_id,
                rule="VELOCITY",
                action="DECLINED",
                details={
                    "count_60s": recent_count,
                    "threshold": 5,
                },
            )
            db.add(flag)
            db.flush()

            raise FraudDeclinedError(
                rule="VELOCITY",
                detail=f"{recent_count} transactions in last 60 seconds exceeds limit of 5.",
            )

        # ── Heuristic 2: Amount Spike (SOFT FLAG) ──
        thirty_days_ago = now - timedelta(days=30)
        avg_amount = db.query(func.avg(Transaction.amount)).filter(
            and_(
                Transaction.card_id == card_id,
                Transaction.created_at >= thirty_days_ago,
                Transaction.status.in_([
                    TransactionStatus.AUTHORIZED.value,
                    TransactionStatus.CLEARED.value,
                    TransactionStatus.SETTLED.value,
                ]),
            )
        ).scalar()

        if avg_amount and amount > Decimal(str(avg_amount)) * 3:
            logger.info(
                "FRAUD SOFT FLAG: Amount spike for card %s — ₹%s vs 30d avg ₹%s",
                card_id, amount, avg_amount,
            )
            flag = FraudFlag(
                transaction_id=transaction_id or uuid.uuid4(),
                card_id=card_id,
                rule="AMOUNT_SPIKE",
                action="REVIEW",
                details={
                    "transaction_amount": str(amount),
                    "avg_30d": str(round(avg_amount, 2)),
                    "multiplier": str(round(float(amount) / float(avg_amount), 2)),
                },
            )
            db.add(flag)
            results.append({
                "rule": "AMOUNT_SPIKE",
                "action": "REVIEW",
                "detail": f"Amount ₹{amount} is {round(float(amount) / float(avg_amount), 1)}× the 30-day average",
            })

            # Set risk flag on the transaction
            if transaction_id:
                txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
                if txn:
                    txn.risk_flag = True
                    txn.risk_notes = (txn.risk_notes or "") + f"AMOUNT_SPIKE: ₹{amount} vs avg ₹{round(avg_amount, 2)}; "

        # ── Heuristic 3: Unusual Hour (SOFT FLAG) ──
        # UTC+5:30 IST conversion for India
        ist_hour = (now.hour + 5) % 24  # Simplified IST offset
        if 1 <= ist_hour <= 5:
            logger.info(
                "FRAUD SOFT FLAG: Unusual hour for card %s — IST hour %d",
                card_id, ist_hour,
            )
            flag = FraudFlag(
                transaction_id=transaction_id or uuid.uuid4(),
                card_id=card_id,
                rule="UNUSUAL_HOUR",
                action="REVIEW",
                details={
                    "ist_hour": ist_hour,
                    "utc_hour": now.hour,
                },
            )
            db.add(flag)
            results.append({
                "rule": "UNUSUAL_HOUR",
                "action": "REVIEW",
                "detail": f"Transaction at IST {ist_hour}:00 (01:00–05:00 window)",
            })

            if transaction_id:
                txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
                if txn:
                    txn.risk_flag = True
                    txn.risk_notes = (txn.risk_notes or "") + f"UNUSUAL_HOUR: IST {ist_hour}:00; "

        if results:
            db.flush()

        return results
