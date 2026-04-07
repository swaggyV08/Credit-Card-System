"""
Idempotency Service — Week 5

Ensures exactly-once semantics for transaction creation by:
  1. check_idempotency()  — Looks up an existing cached response for a key
  2. store_idempotency_result() — Stores the response for future lookups

Keys expire after 24 hours.  Uses the IdempotencyKey model from billing.py.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.billing import IdempotencyKey
from app.core.exceptions import (
    IdempotencyConflictError, InvalidIdempotencyKeyError,
)

logger = logging.getLogger("zbanque.idempotency")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyService:
    """Manages idempotency key lifecycle."""

    TTL_HOURS = 24

    @staticmethod
    def check_idempotency(
        db: Session,
        key: str,
        card_id: str,
    ) -> dict | None:
        """
        Check if an idempotency key has already been processed.

        Returns the cached response body if found and not expired,
        or None if the key is new.
        """
        if not key:
            return None

        # Validate UUID v4 format
        import uuid as uuid_mod
        try:
            val = uuid_mod.UUID(str(key), version=4)
        except (ValueError, AttributeError):
            raise InvalidIdempotencyKeyError()

        record = db.query(IdempotencyKey).filter(
            IdempotencyKey.key == str(key),
        ).first()

        if record is None:
            return None

        # Handle SQLite offset-naive datetimes
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Check expiration
        if expires_at < _utcnow():
            # Expired — delete and treat as new
            db.delete(record)
            db.flush()
            logger.info("Idempotency key '%s' expired, treating as new request", key)
            return None

        # Verify same card_id
        if str(record.card_id) != str(card_id):
            raise IdempotencyConflictError(key)

        logger.info("Idempotency key '%s' found — returning cached response", key)
        return {
            "response_body": record.response_body,
            "status_code": record.status_code,
        }

    @staticmethod
    def store_idempotency_result(
        db: Session,
        key: str,
        card_id,
        response_body: dict,
        status_code: int = 201,
    ) -> None:
        """
        Store an idempotency key with its response for future lookups.
        """
        if not key:
            return

        import uuid as uuid_mod
        card_uuid = card_id if isinstance(card_id, uuid_mod.UUID) else uuid_mod.UUID(str(card_id))

        record = IdempotencyKey(
            key=key,
            card_id=card_uuid,
            response_body=response_body,
            status_code=status_code,
            expires_at=_utcnow() + timedelta(hours=IdempotencyService.TTL_HOURS),
        )
        db.add(record)
        db.flush()
        logger.info("Stored idempotency key '%s' (expires in %dh)", key, IdempotencyService.TTL_HOURS)
