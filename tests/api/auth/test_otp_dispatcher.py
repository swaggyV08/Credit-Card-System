import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime, timezone

from app.main import app
from app.api.deps import get_db
from app.db.base_class import Base
from app.core.config import settings
from app.models.customer import OTPCode, OTPPurpose
from app.core import otp as otp_util

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

def test_otp_dispatcher_flow(client, db_session):
    from app.models.auth import User
    user = User(id=str(uuid.uuid4().hex[:20])[:20], email="otpuser@test.com", status="UNVERIFIED")
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    
    # 1. Test Generate
    gen_resp = client.post(f"/auth/otp/{user_id}?command=generate", json={
        "purpose": "LOGIN"
    })
    assert gen_resp.status_code == 200
    assert "OTP dispatched" in gen_resp.json()["data"]["message"]
    
    # 2. Test Verify - Missing OTP (Should fail with 422)
    verify_missing_otp_resp = client.post(f"/auth/otp/{user_id}?command=verify", json={
        "purpose": "LOGIN"
    })
    # Our manual check returns 422
    assert verify_missing_otp_resp.status_code == 422
    
    # 3. Test Verify - Success
    otp_record = db_session.query(OTPCode).filter(OTPCode.user_id == user_id).first()
    # We can't easily get the plain text OTP, so let's mock it in the DB or just know it from logs if we were manual.
    # In this test, we'll brute force or just set a known hash.
    known_otp = "123456"
    otp_record.otp_hash = otp_util.hash_otp(known_otp)
    db_session.commit()
    
    verify_success_resp = client.post(f"/auth/otp/{user_id}?command=verify", json={
        "purpose": "LOGIN",
        "otp": known_otp
    })
    assert verify_success_resp.status_code == 200
    assert "the login otp is verified" in verify_success_resp.json()["data"]["message"]

def test_otp_dispatcher_generate_with_otp_ignored(client, db_session):
    from app.models.auth import User
    user = User(id=str(uuid.uuid4().hex[:20])[:20], email="otpuser2@test.com", status="UNVERIFIED")
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    # Generate should work even if otp is provided in body (it just ignores it)
    gen_resp = client.post(f"/auth/otp/{user_id}?command=generate", json={
        "purpose": "LOGIN",
        "otp": "123456"
    })
    assert gen_resp.status_code == 200
    assert "OTP dispatched" in gen_resp.json()["data"]["message"]
