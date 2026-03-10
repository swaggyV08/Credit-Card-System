from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException
from app.admin.models.card_product import CardProductCore
from app.models.enums import ProductStatus

class CardProductService:
    @staticmethod
    def get_card(db: Session, card_id: UUID) -> CardProductCore:
        card = db.query(CardProductCore).filter(CardProductCore.id == card_id).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card product not found")
        return card

    @staticmethod
    def approve_card_product(db: Session, card_id: UUID, approver_id: UUID, effective_to: Optional[datetime] = None) -> CardProductCore:
        card = CardProductService.get_card(db, card_id)
        
        # IDEMPOTENCY: If already active, return success
        if card.governance.status == ProductStatus.ACTIVE:
            return card

        if card.governance.status != ProductStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Only DRAFT card products can be approved")
            
        if card.governance.created_by == approver_id:
            raise HTTPException(status_code=403, detail="Maker-Checker violation: Creator cannot approve their own card product")
            
        # Ensure parent Credit Product is active
        if getattr(card.credit_product, 'status', ProductStatus.DRAFT) != ProductStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Cannot approve Card Product if parent Credit Product is not ACTIVE")

        card.governance.status = ProductStatus.ACTIVE
        card.governance.approved_by = approver_id
        card.governance.effective_from = datetime.now(timezone.utc)
        if effective_to:
            card.governance.effective_to = effective_to
        
        db.commit()
        db.refresh(card)
        return card
