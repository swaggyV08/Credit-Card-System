import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime, timezone

from app.main import app
from app.api.deps import get_db
from app.db.base_class import Base
from app.core.hmac_security import verify_banking_signature
from app.core.config import settings
from app.models.auth import User
from app.models.card_management import CCMCreditAccount, CCMCreditCard
from app.models.enums import CCMCardStatus, CardNetwork, CardVariant, ActorType
from app.models.customer import OTPCode, OTPPurpose

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    # Clear overrides
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture(scope="function")
def test_user(db_session):
    user = User(
        id=uuid.uuid4(),
        email=f"test_{uuid.uuid4().hex[:6]}@example.com",
        country_code="+91",
        phone_number="1234567890",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture(scope="function")
def test_account(db_session, test_user):
    account = CCMCreditAccount(
        id=uuid.uuid4(),
        user_id=test_user.id,
        credit_limit=50000.0,
        available_credit=50000.0,
        cash_limit=10000.0,
        status="ACTIVE"
    )
    db_session.add(account)
    db_session.commit()
    return account

def test_full_card_lifecycle(client, db_session, test_user, test_account):
    # 1. Issue Card
    resp = client.post(f"/cards/{test_account.id}/issue", json={
        "credit_account_id": str(test_account.id),
        "card_product_id": str(uuid.uuid4()),
        "card_type": "PHYSICAL",
        "embossed_name": "JOHN SMITH",
        "delivery_address": "Hyderabad"
    })
    
    assert resp.status_code == 201
    output = resp.json()
    assert "Card issued successfully" in output
    # Extract card_id from output using regex or string splitting
    import re
    card_id_match = re.search(r"Card ID: ([a-f0-9\-]+)", output)
    card_id = card_id_match.group(1)

    # 2. Activate Card - Stage 1 (Verify OTP)
    # Generic OTP generate
    otp_resp = client.post("/auth/otp/generate", json={
        "purpose": "ACTIVATION",
        "user_id": str(test_user.id)
    })
    assert otp_resp.status_code == 200
    
    # Get and set known OTP
    known_otp = "123456"
    from app.core import otp as otp_util
    otp_record = db_session.query(OTPCode).filter(OTPCode.user_id == test_user.id).order_by(OTPCode.created_at.desc()).first()
    otp_record.otp_hash = otp_util.hash_otp(known_otp)
    db_session.commit()

    resp = client.post(f"/cards/{card_id}/activate", params={"command": "verify otp"}, json={
        "otp": known_otp
    })
    assert resp.status_code == 200
    assert "OTP Verified" in resp.json()

    # 3. Activate Card - Stage 2 (Set PIN / Activate)
    resp = client.post(f"/cards/{card_id}/activate", params={"command": "activate"}, json={
        "pin": "1234",
        "confirm_pin": "1234"
    })
    assert resp.status_code == 200
    assert resp.json() == "Card Activated"

    # 4. Block Card
    resp = client.post(f"/cards/{card_id}", params={"command": "block"}, json={
        "reason": "LOST"
    })
    assert resp.status_code == 200
    assert "Card Blocked" in resp.json()

    # 5. Unblock Card - Stage 1 (OTP)
    resp = client.post(f"/cards/{card_id}", params={"command": "unblock_otp"}, json={
        "reason": "CARD_FOUND"
    })
    assert resp.status_code == 200
    assert "Authenticate with otp" in resp.json()
    
    # Get and set known OTP for unblock
    otp_record = db_session.query(OTPCode).filter(OTPCode.user_id == test_user.id, OTPCode.purpose == "UNBLOCK").order_by(OTPCode.created_at.desc()).first()
    otp_record.otp_hash = otp_util.hash_otp(known_otp)
    db_session.commit()

    # 6. Unblock Card - Stage 2 (Confirm)
    resp = client.post(f"/cards/{card_id}", params={"command": "unblock"}, json={
        "otp": known_otp
    })
    assert resp.status_code == 200
    assert "Card Active Again" in resp.json()

    # 7. Replace Card
    resp = client.post(f"/cards/{card_id}", params={"command": "replace"}, json={
        "reason": "DAMAGED",
        "reissue_type": "PHYSICAL",
        "Delivery Address": "Bangalore"
    })
    assert resp.status_code == 200
    assert "Replacement Card Ordered" in resp.json()

    # 8. Features
    resp = client.patch(f"/cards/{card_id}/features", json={
        "international_enabled": True,
        "contactless_enabled": True,
        "online_enabled": True
    })
    assert resp.status_code == 200
    assert resp.json() == "Card settings updated"

    # 9. Limits
    resp = client.patch(f"/cards/{card_id}/limits", json={
        "daily_limit": 100000,
        "online_limit": 50000,
        "atm_limit": 20000
    })
    assert resp.status_code == 200
    assert resp.json() == "Limits updated successfully"
    # Generate
    resp = client.post("/auth/otp/generate", json={
        "purpose": "REGISTRATION",
        "email": "test@example.com"
    })
    assert resp.status_code == 200
    
    # Verify (will fail because we don't know the OTP)
    resp = client.post("/auth/otp/verify", json={
        "purpose": "REGISTRATION",
        "email": "test@example.com",
        "otp": "000000"
    })
    assert resp.status_code == 400
