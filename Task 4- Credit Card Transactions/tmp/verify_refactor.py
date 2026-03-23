import sys
import os
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import Query
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Monkeypatch PostgreSQL types for SQLite compatibility
import sqlalchemy.dialects.postgresql as postgresql
from sqlalchemy import JSON, String
postgresql.JSONB = JSON

class MockUUID(String):
    def __init__(self, *args, **kwargs):
        kwargs.pop('as_uuid', None)
        super().__init__(*args, **kwargs)
postgresql.UUID = MockUUID

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.main import app
from app.db.session import get_db
from app.db.base_class import Base
from app.models.auth import User, AuthCredential
from app.models.pending_registration import PendingRegistration
from app.models.customer import CustomerProfile, OTPCode, OTPPurpose, CustomerAddress
from app.admin.models.card_issuance import CreditAccount, Card
from app.admin.models.card_product import CardProductCore
from app.models.enums import KYCState, CardStatus, CCMCardStatus

# SQLite in-memory database for testing
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def test_registration_flow():
    print("\n--- Testing Registration Flow ---")
    # 1. Create Registration
    payload = {
        "name": {"first_name": "Test", "last_name": "User"},
        "contact": {"country_code": "+91", "phone_number": "9876543210"},
        "email": "test@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!"
    }
    response = client.post("/auth/registrations", json=payload)
    assert response.status_code == 201
    reg_id = response.json()["registration_id"]
    print(f"Registration Created: {reg_id}")

    # 2. Generate OTP via dispatcher
    # Old linkage_id is now user_id
    response = client.post(f"/auth/otp/{reg_id}?command=generate", json={"purpose": "REGISTRATION"})
    assert response.status_code == 200
    print("OTP Generated via Dispatcher")

    # Get OTP from DB (as we can't see the terminal)
    db = TestingSessionLocal()
    otp_code = db.query(OTPCode).filter(OTPCode.email == "test@example.com").first()
    # We need the actual OTP, but it's hashed. Let's mock the verify_otp or find it in logs?
    # Actually, in tests we can use a fixed OTP or just bypass.
    # But wait, our generic_otp_dispatcher uses verify_otp.
    # For testing, let's just use the fact that it *was* generated and we can try to verify with "123456" 
    # and monkeypatch if needed.
    
    from app.core import otp as otp_module
    original_verify = otp_module.verify_otp
    otp_module.verify_otp = lambda otp, hash: True # Bypass for test

    # 3. Verify OTP via dispatcher (should trigger user creation)
    response = client.post(f"/auth/otp/{reg_id}?command=verify", json={"purpose": "REGISTRATION", "otp": "123456"})
    assert response.status_code == 200
    assert "Registration successful" in response.json()["message"]
    print("Registration Verified via Dispatcher")

    # 4. Check if User exists
    user = db.query(User).filter(User.email == "test@example.com").first()
    assert user is not None
    assert user.is_active == True
    print("User Successfully Created")
    
    otp_module.verify_otp = original_verify # Restore
    return user.id

def test_kyc_flow(user_id):
    print("\n--- Testing KYC Flow ---")
    # Mock authentication
    from app.api.deps import get_current_authenticated_user
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    app.dependency_overrides[get_current_authenticated_user] = lambda: user

    # Ensure CIF is completed (requirement for KYC)
    user.is_cif_completed = True
    db.commit()

    # Simplified KYC POST
    import io
    file_content = b"fake image content"
    file = io.BytesIO(file_content)
    
    response = client.post(
        "/customers/kyc?command=upload",
        files={"file": ("test.jpg", file, "image/jpeg")},
        data={"document_type": "PAN", "document_number": "ABCDE1234F"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "KYC SUBMITTED"
    print("KYC POST returned 'KYC SUBMITTED'")

    # Check status
    db.refresh(user)
    assert user.is_kyc_completed == True
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    assert profile.kyc_state == KYCState.COMPLETED
    print("User is_kyc_completed is True and kyc_state is COMPLETED")

def test_password_reset_flow(user_id):
    print("\n--- Testing Password Reset Flow ---")
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    
    # 1. Generate OTP via dispatcher
    response = client.post(f"/auth/otp/{user.id}?command=generate", json={"purpose": "PASSWORD_RESET"})
    assert response.status_code == 200
    
    # 2. Verify OTP via dispatcher
    from app.core import otp as otp_module
    original_verify = otp_module.verify_otp
    otp_module.verify_otp = lambda otp, hash: True
    
    response = client.post(f"/auth/otp/{user.id}?command=verify", json={"purpose": "PASSWORD_RESET", "otp": "123456"})
    assert response.status_code == 200
    print("Password Reset OTP Verified via Dispatcher")

    # 3. Patch Password (no OTP in body now)
    payload = {
        "new_password": "NewPassword123!",
        "confirm_password": "NewPassword123!"
    }
    response = client.patch(f"/auth/passwords/{user.country_code}/{user.phone_number}", json=payload)
    if response.status_code != 200:
        print(f"Error reset password: {response.json()}")
    assert response.status_code == 200
    assert "Password updated successfully" in response.json()["message"]
    print("Password Updated Successfully without OTP in body")
    
    otp_module.verify_otp = original_verify

def test_get_commands(user_id):
    print("\n--- Testing GET Commands ---")
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    
    # Profile GET
    response = client.get("/customers/profile?command=profile")
    assert response.status_code == 200
    print("GET /profile?command=profile Successful")

    response = client.get("/customers/profile?command=invalid")
    assert response.status_code == 400
    print("GET /profile?command=invalid correctly failed with 400")

    # Credit Cards GET
    response = client.get("/customers/credit-cards?command=credit_cards")
    assert response.status_code == 200
    print("GET /customers/credit-cards?command=credit_cards Successful")

    # Credit Account GET
    # Create a dummy account
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user_id).first()
    # Need a card product first
    from app.admin.models.credit_product import CreditProductInformation
    from app.admin.models.card_product import CardBillingConfiguration
    cp = CreditProductInformation(product_code="TEST", product_name="Test Product")
    db.add(cp)
    db.flush()
    card_prod = CardProductCore(credit_product_id=cp.id, card_branding_code="TEST_CARD", card_network="VISA", card_variant="GOLD")
    db.add(card_prod)
    db.flush()
    billing = CardBillingConfiguration(card_product_id=card_prod.id, billing_cycle_day=1, payment_due_days=20)
    db.add(billing)
    
    acc = CreditAccount(cif_id=profile.id, card_product_id=card_prod.id, outstanding_amount=100.0, credit_limit=5000.0, available_limit=4900.0, cash_advance_limit=1000.0)
    db.add(acc)
    db.commit()

    response = client.get(f"/customers/{acc.id}?command=credit_account")
    if response.status_code != 200:
        print(f"Error account: {response.json()}")
    assert response.status_code == 200
    print("GET /customers/{id}?command=credit_account Successful")

if __name__ == "__main__":
    try:
        u_id = test_registration_flow()
        test_kyc_flow(u_id)
        test_password_reset_flow(u_id)
        test_get_commands(u_id)
        print("\nALL TESTS PASSED!")
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        sys.exit(1)
