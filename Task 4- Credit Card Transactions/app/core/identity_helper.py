from sqlalchemy.orm import Session
from app.models.auth import User, AuthCredential
from app.models.customer import CustomerProfile, CustomerAddress, EmploymentDetail, FinancialInformation, FATCADeclaration, KYCDocumentSubmission, KYCOTPVerification
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card
from app.models.card_management import CCMCreditAccount, CCMCreditCard
from app.models.customer import OTPCode

def update_user_identity(db: Session, old_id: str, new_id: str):
    """
    Manually update all tables that reference user_id because the PK has changed.
    """
    # 1. Update User PK (This is tricky with FKs)
    # Usually, we'd need to update FKs first or use CASCADE.
    # Since we are changing the PK itself, we need to be careful.
    
    # Let's try to update all references first
    db.query(AuthCredential).filter(AuthCredential.user_id == old_id).update({"user_id": new_id})
    db.query(CustomerProfile).filter(CustomerProfile.user_id == old_id).update({"user_id": new_id})
    db.query(CreditCardApplication).filter(CreditCardApplication.user_id == old_id).update({"user_id": new_id})
    db.query(CCMCreditAccount).filter(CCMCreditAccount.user_id == old_id).update({"user_id": new_id})
    db.query(CCMCreditCard).filter(CCMCreditCard.user_id == old_id).update({"user_id": new_id})
    db.query(OTPCode).filter(OTPCode.user_id == old_id).update({"user_id": new_id})
    
    # Now update the User table itself
    user = db.query(User).filter(User.id == old_id).first()
    if user:
        # Special handling for changing PK in SQLAlchemy
        # We might need to delete and re-add or use a raw SQL if it's too complex
        # But let's try a direct update if the DB allows it (no conflicts)
        user.id = new_id
    
    db.flush()
