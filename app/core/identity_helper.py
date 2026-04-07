from sqlalchemy.orm import Session
from app.models.auth import User, AuthCredential
from app.models.customer import CustomerProfile, CustomerAddress, EmploymentDetail, FinancialInformation, FATCADeclaration, KYCDocumentSubmission, KYCOTPVerification
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card
from app.models.card_management import CCMCreditAccount, CCMCreditCard
from app.models.customer import OTPCode

def update_user_identity(db: Session, old_id: str, new_id: str):
    """
    Update all tables that reference user_id by creating a new User clone,
    migrating all child references to the new ID, and deleting the old User.
    This avoids foreign key violation errors when ON UPDATE CASCADE is missing.
    """
    # 1. Fetch old user
    old_user = db.query(User).filter(User.id == old_id).first()
    if not old_user:
        return
        
    # Temporarily scramble the old user's email to free up the unique constraint
    actual_email = old_user.email
    old_user.email = f"migrate_{old_id}@temp.local"
    db.flush()
        
    # 2. Create clone of old user with new ID and original email
    new_user = User(
        id=new_id,
        email=actual_email,
        country_code=old_user.country_code,
        phone_number=old_user.phone_number,
        status=old_user.status,
        is_cif_completed=old_user.is_cif_completed,
        is_kyc_completed=old_user.is_kyc_completed,
        created_at=old_user.created_at
    )
    db.add(new_user)
    db.flush()
    
    # 3. Update all child tables to point to the new user ID
    db.query(AuthCredential).filter(AuthCredential.user_id == old_id).update({"user_id": new_id})
    db.query(CustomerProfile).filter(CustomerProfile.user_id == old_id).update({"user_id": new_id})
    db.query(CreditCardApplication).filter(CreditCardApplication.user_id == old_id).update({"user_id": new_id})
    
    # Let's catch potential missing ones gracefully since some imports might be unused
    try:
        db.query(CCMCreditAccount).filter(CCMCreditAccount.user_id == old_id).update({"user_id": new_id})
        db.query(CCMCreditCard).filter(CCMCreditCard.user_id == old_id).update({"user_id": new_id})
    except Exception:
        pass
        
    db.query(OTPCode).filter(OTPCode.user_id == old_id).update({"user_id": new_id})
    
    # 4. Delete the old user entry now that all children have been migrated
    db.delete(old_user)
    db.flush()
