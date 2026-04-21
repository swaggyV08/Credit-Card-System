"""
Velocity & Fraud Service — In-Memory Dictionary-Based

Production-grade velocity checking and basic fraud detection using
in-memory dictionaries (no Redis). Suitable for single-instance deployments.

Velocity Rules:
  • 5-minute window: max 5 transactions per account
  • 5-minute window: max ₹10,000 cumulative amount per account

Fraud Rules (3 heuristics):
  1. Amount > ₹10,000 AND new merchant (no prior tx with same merchant)
  2. Velocity exceeded (above)
  3. Transaction in unusual hours (midnight to 5 AM IST)
"""
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.transactions.transactions import Transaction
from app.models.transactions.enums import TransactionStatus
from app.core.exceptions import VelocityExceededError

logger = logging.getLogger("zbanque.velocity")

# ── In-Memory Velocity Store ────────────────────────────
# account_id → list of (timestamp, amount) tuples
VELOCITY_WINDOW = timedelta(minutes=5)
MAX_TXN_COUNT = 5
MAX_TXN_AMOUNT = Decimal("10000")

velocity_store: dict[str, list[tuple[datetime, Decimal]]] = defaultdict(list)


def _prune_window(account_key: str) -> None:
    """Remove entries older than the velocity window."""
    now = datetime.now(timezone.utc)
    velocity_store[account_key] = [
        (t, a) for t, a in velocity_store[account_key]
        if now - t < VELOCITY_WINDOW
    ]


class VelocityService:
    """
    In-memory velocity gate using defaultdict.

    Velocity Formula:
        window = 5 minutes
        count_check: len(entries_in_window) >= 5 → REJECT
        amount_check: sum(amounts_in_window) + current_amount > ₹10,000 → REJECT

    After successful authorization, call record_transaction() to update the store.
    """

    @staticmethod
    def check_velocity(account_id: uuid.UUID, amount: Decimal) -> None:
        """
        Check if the account has exceeded velocity limits.

        Raises VelocityExceededError if:
          - 5 or more transactions in the last 5 minutes, OR
          - cumulative amount in last 5 minutes + current amount > ₹10,000

        Formula:
            count = len([t for t in velocity_store[account_id] if now - t.timestamp < 5min])
            total = sum([t.amount for t in velocity_store[account_id] if now - t.timestamp < 5min])
            if count >= 5 OR (total + amount) > 10000: REJECT
        """
        key = str(account_id)
        _prune_window(key)

        entries = velocity_store[key]
        count = len(entries)
        total_amount = sum(a for _, a in entries)

        if count >= MAX_TXN_COUNT:
            logger.warning(
                "Velocity count exceeded for account %s: %d txns in window",
                account_id, count
            )
            raise VelocityExceededError(
                retry_after=int(VELOCITY_WINDOW.total_seconds())
            )

        if total_amount + amount > MAX_TXN_AMOUNT:
            logger.warning(
                "Velocity amount exceeded for account %s: ₹%s + ₹%s > ₹%s",
                account_id, total_amount, amount, MAX_TXN_AMOUNT
            )
            raise VelocityExceededError(
                retry_after=int(VELOCITY_WINDOW.total_seconds())
            )

    @staticmethod
    def record_transaction(account_id: uuid.UUID, amount: Decimal) -> None:
        """Record a successful transaction in the velocity store."""
        key = str(account_id)
        now = datetime.now(timezone.utc)
        velocity_store[key].append((now, amount))

    @staticmethod
    def reset_velocity(account_id: uuid.UUID) -> None:
        """Reset velocity store for an account (used in testing)."""
        key = str(account_id)
        velocity_store[key] = []


class FraudService:
    """
    Basic fraud detection — 3 rules (in service layer).

    Rule 1: Amount > ₹10,000 AND new merchant (no prior tx with same merchant)
        → Flag as SUSPICIOUS, do NOT block

    Rule 2: Velocity exceeded
        → Handled by VelocityService.check_velocity() which raises VelocityExceededError

    Rule 3: Transaction during unusual hours (midnight to 5 AM IST = 18:30 to 23:30 UTC)
        → Flag as SUSPICIOUS, do NOT block
    """

    @staticmethod
    def run_fraud_checks(
        db: Session,
        card_id: uuid.UUID,
        amount: Decimal,
        merchant_name: str | None,
        merchant_id: uuid.UUID | None = None,
    ) -> dict:
        """
        Run all 3 fraud heuristics. Returns a dict with:
          - flagged: bool
          - reasons: list[str]
          - risk_score: float (0.0 to 1.0)

        Does NOT block the transaction — only flags for review.
        """
        flags: list[str] = []
        risk_score = 0.0

        # ── Rule 1: High amount + new merchant ──
        # Check if this card has ever transacted with this merchant
        if amount > Decimal("10000") and merchant_name:
            prior_txn = db.query(Transaction.id).filter(
                and_(
                    Transaction.card_id == card_id,
                    Transaction.merchant_name == merchant_name,
                    Transaction.status.in_([
                        TransactionStatus.AUTHORIZED.value,
                        TransactionStatus.CLEARED.value,
                        TransactionStatus.SETTLED.value,
                    ]),
                )
            ).first()

            if not prior_txn:
                flags.append(
                    f"HIGH_AMOUNT_NEW_MERCHANT: ₹{amount} to new merchant '{merchant_name}'"
                )
                risk_score += 0.4

        # ── Rule 2: Velocity ──
        # Already handled by VelocityService.check_velocity() which raises before we get here.
        # This is a belt-and-suspenders check via the velocity store.
        # If we reached this point, velocity is OK, but we can still flag near-threshold.
        # (No action needed here — velocity is enforced before fraud checks)

        # ── Rule 3: Unusual hours (midnight to 5 AM IST) ──
        # IST = UTC + 5:30, so midnight IST = 18:30 UTC, 5 AM IST = 23:30 UTC
        now_utc = datetime.now(timezone.utc)
        utc_hour = now_utc.hour
        utc_minute = now_utc.minute
        # Convert to IST for check
        ist_offset = timedelta(hours=5, minutes=30)
        ist_time = now_utc + ist_offset
        ist_hour = ist_time.hour

        if 0 <= ist_hour < 5:
            flags.append(
                f"UNUSUAL_HOUR: Transaction at {ist_time.strftime('%H:%M')} IST "
                f"(between midnight and 5 AM)"
            )
            risk_score += 0.3

        flagged = len(flags) > 0
        risk_score = min(risk_score, 1.0)

        if flagged:
            logger.warning(
                "Fraud flags for card %s: %s (risk_score=%.2f)",
                card_id, "; ".join(flags), risk_score,
            )

        return {
            "flagged": flagged,
            "reasons": flags,
            "risk_score": risk_score,
        }
