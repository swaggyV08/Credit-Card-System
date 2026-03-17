import uuid
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.models.card_management import CCMCreditAccount, CCMCreditCard
from app.models.customer import User, CustomerProfile
from app.services.card_management_service import CardManagementService
from app.admin.services.credit_account_admin_svc import CreditAccountAdminService
from app.admin.schemas.credit_account_admin import CreditLimitUpdateRequest
from app.schemas.card_management import CCMCardIssueRequest, CCMCardActivationRequest, CCMCardBlockRequest
from app.models.enums import CCMReissueType, CCMLimitReasonCode, CCMCardStatus

# Use in-memory SQLite for verification
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

def verify():
    db = SessionLocal()
    try:
        # 1. Setup Mock User and Account
        user = User(email="test@zbanque.com", is_active=True)
        db.add(user)
        db.flush()
        profile = CustomerProfile(user_id=user.id, first_name="Test", last_name="User")
        db.add(profile)
        account = CCMCreditAccount(
            user_id=user.id, 
            credit_limit=Decimal("50000"), 
            available_credit=Decimal("50000"),
            outstanding_balance=Decimal("0"),
            product_code="PLATINUM"
        )
        db.add(account)
        db.commit()

        print("--- Testing Credit Limit Update ---")
        limit_req = CreditLimitUpdateRequest(
            new_credit_limit=Decimal("75000"),
            year=2026, month=12, day=31,
            reason_code=CCMLimitReasonCode.MANUAL_OVERRIDE, # Fixed Enum
            notes="Annual review"
        )
        updated_acc, old_limit = CreditAccountAdminService.update_limit(db, account.id, limit_req, uuid.uuid4())
        print(f"Old Limit: {old_limit}, New Limit: {updated_acc.credit_limit}")
        assert updated_acc.credit_limit == Decimal("75000")

        print("\n--- Testing Card Issuance ---")
        issue_req = CCMCardIssueRequest(
            credit_account_id=account.id,
            card_product_id=uuid.uuid4(),
            card_type=CCMReissueType.PHYSICAL,
            embossed_name="TEST USER",
            delivery_address="123 Test St"
        )
        issue_resp = CardManagementService.issue_card(db, account.id, issue_req)
        print(f"Issue Response: {issue_resp['message']}")
        card_id = issue_resp['card_id']
        assert "successfully" in issue_resp['message']

        print("\n--- Testing Activation Stage 1 ---")
        gen_resp = CardManagementService.handle_activation_generate(db, card_id)
        activation_id = uuid.UUID(gen_resp['activation_id'])
        print(f"Activation ID: {activation_id}")

        print("\n--- Testing Activation Stage 3 (Failing without OTP verification) ---")
        try:
            CardManagementService.handle_activation_final(db, card_id, CCMCardActivationRequest(pin="1234", activation_id=activation_id))
        except Exception as e:
            print(f"Expected failure catch: {e.detail}")

        print("\n--- Testing Block Card ---")
        block_req = CCMCardBlockRequest(reason="LOST")
        block_resp = CardManagementService.block_card(db, card_id, block_req)
        print(block_resp['message'])
        card = db.query(CCMCreditCard).get(card_id)
        assert card.status == CCMCardStatus.BLOCKED_USER

        print("\nVerification Successful!")
    finally:
        db.close()

if __name__ == "__main__":
    verify()
