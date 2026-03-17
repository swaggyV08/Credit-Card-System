from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.auth import User

class NotificationService:
    @staticmethod
    def send_product_expiration_notice(
        db: Session, 
        user_id: UUID, 
        product_name: str, 
        product_type: str = "Credit Product"
    ):
        """
        Sends a professional notification to the customer about product expiration.
        In this MVP, we log the message. In a real system, this would trigger an Email/SMS.
        """
        message = (
            f"Dear valued customer, we wish to inform you that the {product_name} ({product_type}) "
            "has reached its end-of-life cycle and will no longer be available. "
            "To continue enjoying our premium credit services, we invite you to explore and "
            "reapply for our updated offerings at your earliest convenience."
        )
        
        # Mocking notification delivery
        print(f"NOTIFICATION SENT TO USER {user_id}: {message}")
        
        # In a real system:
        # notification = Notification(user_id=user_id, content=message, type="PRODUCT_EXPIRATION")
        # db.add(notification)
        # db.commit()
        
        return True

    @staticmethod
    def notify_affected_customers(
        db: Session, 
        product_id: UUID, 
        product_name: str, 
        product_type: str
    ):
        """
        Identifies all customers using a specific product and notifies them.
        """
        from app.admin.models.card_issuance import CreditAccount
        
        # Find accounts linked to this product (assuming product_id is either credit or card)
        if product_type == "Credit Product":
            accounts = db.query(CreditAccount).filter(CreditAccount.credit_product_id == product_id).all()
        else:
            accounts = db.query(CreditAccount).filter(CreditAccount.card_product_id == product_id).all()
            
        for account in accounts:
            NotificationService.send_product_expiration_notice(
                db, 
                account.user_id, 
                product_name, 
                product_type
            )
        
        return len(accounts)
