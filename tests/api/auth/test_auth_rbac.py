import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.main import app
from app.db.session import get_db
from app.models.auth import User, AuthCredential
from app.models.customer import CustomerProfile, OTPCode, OTPPurpose
from app.models.admin import Admin
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount
from app.core.security import hash_value
from app.core.otp import hash_otp
from app.core.jwt import create_access_token

@pytest.fixture
def mock_db():
    m = MagicMock()
    # Pre-configure to return None for lookups by default to avoid 409s/400s from truthy mocks
    m.query.return_value.filter.return_value.first.return_value = None
    m.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    m.execute.return_value.scalar_one_or_none.return_value = None
    return m

@pytest.fixture
def client(mock_db):
    # Nuclear option: patch SessionLocal so seeder and routers use mock_db
    with patch("app.db.session.SessionLocal", return_value=mock_db):
        with TestClient(app) as c:
            yield c

def _get_mock_token(role: str):
    token_type = "admin" if role in ["SUPERADMIN", "ADMIN", "MANAGER", "SALES"] else "user"
    return create_access_token({"sub": str(uuid4()), "role": role, "type": "ADMIN" if token_type == "admin" else "USER"})

def test_registration_creates_unverified_user(client, mock_db):
    payload = {
        "email": "testreg@example.com",
        "password": "ValidPassword123!",
        "confirm_password": "ValidPassword123!",
        "full_name": {"first_name": "Test", "last_name": "User"},
        "date_of_birth": "1990-01-01",
        "phone": {"country_code": "+1", "number": "1234567890"}
    }
    
    response = client.post("/auth/register", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert "user_id" in data["data"]
    assert data["data"]["message"] == "Verify with OTP"
    assert mock_db.commit.called

def test_otp_verify_registration_success(client, mock_db):
    user_id = str(uuid4())
    mock_user = User(id=user_id, status="UNVERIFIED")
    
    valid_otp_hash = hash_otp("123456")
    mock_otp_entry = OTPCode(
        otp_hash=valid_otp_hash,
        purpose=OTPPurpose.REGISTRATION,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        is_used=False
    )
    
    # Mocking target lookup then OTP lookup
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        mock_user, # target lookup
        mock_otp_entry # OTP lookup
    ]
    
    response = client.post(f"/auth/otp/{user_id}?command=verify", json={"purpose": "REGISTRATION", "otp": "123456"})
    
    assert response.status_code == 200
    assert response.json()["data"]["message"] == "REGISTRATION COMPLETE"
    assert mock_user.status == "ACTIVE"
    assert mock_otp_entry.is_used == True
    assert mock_db.commit.called

def test_otp_verify_wrong_otp(client, mock_db):
    user_id = str(uuid4())
    mock_user = User(id=user_id, status="UNVERIFIED")
    valid_otp_hash = hash_otp("123456")
    mock_otp_entry = OTPCode(
        otp_hash=valid_otp_hash,
        purpose=OTPPurpose.REGISTRATION,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        is_used=False
    )
    
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        mock_user,
        mock_otp_entry
    ]
    
    response = client.post(f"/auth/otp/{user_id}?command=verify", json={"purpose": "REGISTRATION", "otp": "654321"}) # Wrong OTP
    
    assert response.status_code == 422
    assert response.json()["message"] == "Invalid or expired OTP"
    assert response.json()["status"] == "error"

def test_otp_verify_expired_otp(client, mock_db):
    user_id = str(uuid4())
    mock_user = User(id=user_id, status="UNVERIFIED")
    valid_otp_hash = hash_otp("123456")
    mock_otp_entry = OTPCode(
        otp_hash=valid_otp_hash,
        purpose=OTPPurpose.REGISTRATION,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5), # Expired
        is_used=False
    )
    
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        mock_user,
        mock_otp_entry
    ]
    
    response = client.post(f"/auth/otp/{user_id}?command=verify", json={"purpose": "REGISTRATION", "otp": "123456"})
    
    assert response.status_code == 422
    assert "expired" in response.json()["message"].lower()

def test_login_unverified_user(client, mock_db):
    mock_user = User(id=uuid4().hex[:20], email="test@example.com", status="UNVERIFIED")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    
    response = client.post("/auth/login?command=USER", json={"email": "test@example.com", "password": "Password1!"})
    
    assert response.status_code == 403
    assert response.json()["message"] == "Account must be verified with OTP before login"

def test_login_valid_credentials(client, mock_db):
    u_id = "ZNBNQ" + str(uuid4().hex[:10]).upper()
    mock_user = User(id=u_id, email="test@example.com", status="ACTIVE", is_cif_completed=True, is_kyc_completed=True)
    mock_profile = CustomerProfile(first_name="Test", last_name="User", user_id=u_id)
    mock_cred = AuthCredential(password_hash=hash_value("ValidPassword123!"))
    
    # query().filter().first() sequence for USER login:
    # 1. user lookup (line 175)
    # 2. profile lookup (line 232)
    # 3. latest app lookup (line 243)
    # 4. credit account lookup (line 255)
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_user,    # 1. user lookup (line 175)
        mock_profile, # 2. profile lookup (line 232)
        None          # 4. credit_account lookup (line 255)
    ]
    # 3. latest app lookup (line 243) is handled by the order_by chain configured in the fixture
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_cred
    
    response = client.post("/auth/login?command=USER", json={"email": "test@example.com", "password": "ValidPassword123!"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data["data"]
    assert data["data"]["is_cif_completed"] is True
    assert data["data"]["user_id"] == u_id

def test_admin_create_rbac(client, mock_db):
    # Test SUPERADMIN can create admin
    admin_token = _get_mock_token("SUPERADMIN")
    payload = {
        "full_name": {"first_name": "New", "last_name": "Admin"},
        "email": "admin2@zbanque.com",
        "role": "MANAGER",
        "contact": {"country_code": "+1", "phone_number": "1234567890"}, # Corrected field name
        "password": "ValidPassword123!",
        "confirm_password": "ValidPassword123!"
    }
    
    mock_db.query.return_value.filter.return_value.first.return_value = None # No existing admin
    
    response = client.post("/admins", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 201
    assert "added successfully" in response.json()["data"]["admin"]

    # Test ADMIN cannot create admin (only SUPERADMIN can)
    admin_regular_token = _get_mock_token("ADMIN")
    response_adm = client.post("/admins", json=payload, headers={"Authorization": f"Bearer {admin_regular_token}"})
    assert response_adm.status_code == 403
