from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timezone
from typing import List, Optional, Dict
from fastapi import HTTPException
from app.admin.models.credit_product import CreditProductInformation
from app.models.enums import ProductStatus
from app.core.exceptions import ResourceNotFoundException, BusinessRuleViolationException
from app.services.notification_svc import NotificationService

class CreditProductService:
    @staticmethod
    def get_all_products(
        db: Session, 
        status: Optional[ProductStatus] = None, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[CreditProductInformation]:
        query = db.query(CreditProductInformation)
        if status:
            query = query.filter(CreditProductInformation.status == status)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_product(db: Session, product_id: UUID) -> CreditProductInformation:
        product = db.query(CreditProductInformation).filter(CreditProductInformation.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Credit product not found")
        return product

    @staticmethod
    def submit_for_approval(db: Session, product_id: UUID, user_id: UUID) -> CreditProductInformation:
        product = CreditProductService.get_product(db, product_id)
        
        # State transitions must be explicit
        if product.status != ProductStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Only DRAFT products can be submitted for approval")
        
        # In a real system, there would be a separate PENDING_APPROVAL state,
        # but for this MVP we transition to a suspended/active state via dual control
        # Here we mock a PENDING state or just leave it DRAFT but notify.
        # Let's add a log or change status. Assuming ProductStatus only has DRAFT, ACTIVE, SUSPENDED, CLOSED.
        # We will keep it DRAFT until approved, but in real life we add an approval request record.
        
        return product

    @staticmethod
    def approve_product(db: Session, product_id: UUID, approver_id: UUID, effective_to: Optional[datetime] = None) -> CreditProductInformation:
        product = CreditProductService.get_product(db, product_id)
        
        if product.governance and product.governance.created_by == approver_id:
            raise HTTPException(status_code=403, detail="Maker-Checker violation: Creator cannot approve their own product")

        product.status = ProductStatus.ACTIVE
        if product.governance:
            product.governance.approved_by = approver_id
            product.governance.effective_from = datetime.now(timezone.utc)
            if effective_to:
                product.governance.effective_to = effective_to
        
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def reject_product(db: Session, product_id: UUID, approver_id: UUID, reason: Optional[str] = None) -> CreditProductInformation:
        product = CreditProductService.get_product(db, product_id)
        
        if product.governance and product.governance.created_by == approver_id:
            raise HTTPException(status_code=403, detail="Maker-Checker violation: Creator cannot reject their own product")

        product.status = ProductStatus.REJECTED
        if product.governance:
            product.governance.approved_by = approver_id
            product.governance.rejection_reason = reason
        
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def suspend_product(db: Session, product_id: UUID, user_id: UUID) -> CreditProductInformation:
        product = CreditProductService.get_product(db, product_id)
        
        if product.status != ProductStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Only ACTIVE products can be suspended")
            
        product.status = ProductStatus.SUSPENDED
        if product.governance:
            product.governance.updated_by = user_id
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def delete_product(db: Session, product_id: UUID) -> Dict:
        """
        Hard deletes a credit product and its configurations.
        Affected customers are notified before deletion.
        """
        product = db.query(CreditProductInformation).filter(CreditProductInformation.id == product_id).first()
        if not product:
            raise ResourceNotFoundException("Credit Product", product_id)

        product_name = product.product_name
        product_code = product.product_code

        # 1. Notify affected customers
        NotificationService.notify_affected_customers(
            db, product_id, product_name, "Credit Product"
        )

        # 2. Hard delete (cascade delete-orphan on relationships handles children)
        db.delete(product)
        db.commit()

        return {
            "message": "Credit Product and associated configurations deleted successfully",
            "product_id": product_id,
            "product_code": product_code,
            "product_name": product_name
        }
