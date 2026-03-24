from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from app.main import app
from app.db.base_class import Base
from app.api.deps import get_db
from app.core.config import settings
from app.models.auth import User
from app.models.card_management import CCMCreditAccount, CCMCreditCard
from app.models.customer import OTPCode
from app.models.enums import CCMCardStatus
from app.core import otp as otp_util

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def run_test():
    db = TestingSessionLocal()
    # Create user & account & card
    test_user = User(id=uuid.uuid4(), email="test_unblock@test.com", phone_number="9999999999", country_code="+91", is_active=True)
    test_account = CCMCreditAccount(id=uuid.uuid4(), user_id=test_user.id, credit_limit=50000, available_credit=50000, status="ACTIVE", outstanding_balance=0, cash_limit=10000, billing_cycle_day=1, minimum_due=0, interest_rate=1, late_fee=0)
    
    card_id = uuid.uuid4()
    test_card = CCMCreditCard(id=card_id, user_id=test_user.id, card_number="4111111111111111", card_network="VISA", card_variant="CLASSIC", expiry_date="12/25", cvv_hash="abc", status=CCMCardStatus.BLOCKED_USER, credit_account=test_account, is_contactless_enabled=True, is_international_enabled=True, is_online_enabled=True, is_atm_enabled=True, is_domestic_enabled=True)
    
    db.add_all([test_user, test_account, test_card])
    db.commit()

    # 1. Initiate Unblock
    resp = client.post(f"/cards/{card_id}?command=unblock_otp", json={"reason": "FOUND"})
    print("Initiate UNBLOCK:", resp.json())
    unblock_id = resp.json()["unblock_id"]

    # 2. Generate OTP
    resp = client.post(f"/auth/otp/{unblock_id}?command=generate", json={"purpose": "UNBLOCK"})
    print("Generate OTP:", resp.json())

    # Get OTP from DB
    otp_record = db.query(OTPCode).filter(OTPCode.linkage_id == unblock_id).first()
    known_otp = "123456"
    otp_record.otp_hash = otp_util.hash_otp(known_otp)
    db.commit()

    # 3. Verify OTP
    resp = client.post(f"/auth/otp/{unblock_id}?command=verify", json={"purpose": "UNBLOCK", "otp": known_otp})
    print("Verify OTP:", resp.json())

    # Check OTP status in DB
    db.refresh(otp_record)
    print("DB OTP Status: is_verified=", otp_record.is_verified, "is_used=", otp_record.is_used)

    # 4. Confirm Unblock
    resp = client.post(f"/cards/{card_id}?command=unblock", json={"unblock_id": unblock_id})
    print("Confirm Unblock:", resp.status_code, resp.json())
    
    db.delete(test_card)
    db.delete(test_account)
    db.delete(test_user)
    db.commit()
    db.close()

if __name__ == "__main__":
    run_test()
