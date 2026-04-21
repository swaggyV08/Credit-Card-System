import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.main import app
from app.db.session import get_db
from app.models.auth import User
from app.models.customer import OTPCode, OTPPurpose
from app.core import otp as otp_util

@pytest.fixture
def mock_db():
    m = MagicMock()
    # Pre-configure to return None for lookups by default to avoid truthy mock issues
    m.query.return_value.filter.return_value.first.return_value = None
    m.execute.return_value.scalar_one_or_none.return_value = None
    return m

@pytest.fixture
def client(mock_db):
    # Nuclear option: patch SessionLocal so seeder and routers use mock_db
    with patch("app.db.session.SessionLocal", return_value=mock_db):
        with TestClient(app) as c:
            yield c

def test_otp_dispatcher_flow(client, mock_db):
    user_id = str(uuid4())
    mock_user = User(id=user_id, email="otpuser@test.com", status="UNVERIFIED")
    
    # 1. Test Generate
    # Resolving target entity (User lookup via execute)
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user
    
    gen_resp = client.post(f"/auth/otp/{user_id}?command=generate", json={
        "purpose": "LOGIN"
    })
    assert gen_resp.status_code == 200
    assert "OTP dispatched" in gen_resp.json()["data"]["message"]
    
    # 2. Test Verify - Missing OTP (Should fail with 422)
    verify_missing_otp_resp = client.post(f"/auth/otp/{user_id}?command=verify", json={
        "purpose": "LOGIN"
    })
    assert verify_missing_otp_resp.status_code == 422
    
    # 3. Test Verify - Success
    known_otp = "123456"
    otp_record = OTPCode(
        otp_hash=otp_util.hash_otp(known_otp),
        purpose=OTPPurpose.LOGIN,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        is_used=False
    )
    
    # scalar_one_or_none calls: 1. find target, 2. find OTP in verify
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        mock_user,   # target lookup
        otp_record   # OTP lookup
    ]
    
    verify_success_resp = client.post(f"/auth/otp/{user_id}?command=verify", json={
        "purpose": "LOGIN",
        "otp": known_otp
    })
    assert verify_success_resp.status_code == 200
    assert "verified" in verify_success_resp.json()["data"]["message"].lower()

def test_otp_dispatcher_generate_with_otp_ignored(client, mock_db):
    user_id = str(uuid4())
    mock_user = User(id=user_id, email="otpuser2@test.com", status="UNVERIFIED")
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user

    # Generate should work even if otp is provided in body (it just ignores it)
    gen_resp = client.post(f"/auth/otp/{user_id}?command=generate", json={
        "purpose": "LOGIN",
        "otp": "123456"
    })
    assert gen_resp.status_code == 200
    assert "OTP dispatched" in gen_resp.json()["data"]["message"]
