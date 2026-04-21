import uuid
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.transactions.transactions import TransactionAuditLog

class RefactoredAuditService:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    async def audit_log(
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        flush: bool = True
    ) -> TransactionAuditLog:
        """
        Record a state-modifying action for auditing.
        This provides parity with the legacy _write_audit but is native to AsyncSession.
        """
        entry = TransactionAuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=RefactoredAuditService._utcnow()
        )
        db.add(entry)
        if flush:
            await db.flush()
        return entry
