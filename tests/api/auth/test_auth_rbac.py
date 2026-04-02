import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.main import app
from app.db.session import get_db
from app.core.rbac import require
from app.models.auth import User, AuthCredential
from app.models.customer import CustomerProfile, OTPCode, OTPPurpose
from app.models.admin import Admin
from app.core.security import hash_value
from app.core.otp import hash_otp

client = TestClient(app)

# --- MOCKS ---
mock_db = MagicMock()

def override_get_db():
    yield mock_db

app.dependency_overrides[get_db] = override_get_db

# Helper to mock require dependency for testing RBAC
def override_require(permission: str):
    def _mock_require():
        # For our test, if we set a specific role in request headers, we simulate it
        pass
    return _mock_require

@pytest.fixture(autouse=True)
def reset_mocks():
    mock_db.reset_mock()

def test_registration_creates_unverified_user():
    payload = {
        "email": "testreg@example.com",
        "password": "ValidPassword123!",
        "confirm_password": "ValidPassword123!",
        "name": {"first_name": "Test", "last_name": "User"},
        "contact": {"country_code": "+1", "phone_number": "1234567890"}
    }
    
    mock_db.execute.return_value.scalar_one_or_none.return_value = None # No existing user
    
    response = client.post("/auth/registrations", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert "user_id" in data["data"]
    assert "otp" not in data["data"] # Never return OTP
    assert data["data"]["message"] == "Verify OTP sent"
    assert mock_db.commit.called

def test_otp_verify_registration_success():
    user_id = str(uuid4())
    mock_user = User(id=user_id, status="UNVERIFIED")
    
    valid_otp_hash = hash_otp("123456")
    mock_otp_entry = OTPCode(
        otp_hash=valid_otp_hash,
        purpose=OTPPurpose.REGISTRATION,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        is_used=False
    )
    
    # Mocking user lookup then OTP lookup
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_user), # User lookup
        MagicMock(scalar_one_or_none=lambda: mock_otp_entry) # OTP lookup
    ]
    
    response = client.post(f"/auth/otp/{user_id}?command=verify", json={"purpose": "REGISTRATION", "otp": "123456"})
    
    assert response.status_code == 200
    assert response.json()["data"]["message"] == "REGISTRATION COMPLETE"
    assert mock_user.status == "ACTIVE"
    assert mock_otp_entry.is_used == True
    assert mock_db.commit.called

def test_otp_verify_wrong_otp():
    user_id = str(uuid4())
    mock_user = User(id=user_id, status="UNVERIFIED")
    valid_otp_hash = hash_otp("123456")
    mock_otp_entry = OTPCode(
        otp_hash=valid_otp_hash,
        purpose=OTPPurpose.REGISTRATION,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        is_used=False
    )
    
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_user),
        MagicMock(scalar_one_or_none=lambda: mock_otp_entry)
    ]
    
    response = client.post(f"/auth/otp/{user_id}?command=verify", json={"purpose": "REGISTRATION", "otp": "654321"}) # Wrong OTP
    
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "INVALID_OTP"

def test_otp_verify_expired_otp():
    user_id = str(uuid4())
    mock_user = User(id=user_id, status="UNVERIFIED")
    valid_otp_hash = hash_otp("123456")
    mock_otp_entry = OTPCode(
        otp_hash=valid_otp_hash,
        purpose=OTPPurpose.REGISTRATION,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5), # Expired
        is_used=False
    )
    
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_user),
        MagicMock(scalar_one_or_none=lambda: mock_otp_entry)
    ]
    
    response = client.post(f"/auth/otp/{user_id}?command=verify", json={"purpose": "REGISTRATION", "otp": "123456"})
    
    assert response.status_code == 422
    assert "expired" in response.json()["errors"][0]["message"].lower()

def test_login_unverified_user():
    mock_user = User(id=uuid4(), email="test@example.com", status="UNVERIFIED")
    
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_user)
    ]
    
    response = client.post("/auth/sessions/email", json={"email": "test@example.com", "password": "Password1!"})
    
    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "UNAUTHORIZED"

def test_login_valid_credentials():
    mock_user = User(id=uuid4(), email="test@example.com", status="ACTIVE", is_cif_completed=True, is_kyc_completed=True)
    mock_profile = CustomerProfile(first_name="Test", last_name="User")
    mock_user.customer_profile = mock_profile
    
    mock_cred = AuthCredential(password_hash=hash_value("ValidPassword123!"))
    
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_user),
        MagicMock(scalar_one_or_none=lambda: mock_cred)
    ]
    
    response = client.post("/auth/sessions/email", json={"email": "test@example.com", "password": "ValidPassword123!"})
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data["data"]
    assert data["data"]["is_cif_completed"] is True
    
def _get_mock_token(role: str):
    from app.core.jwt import create_access_token
    token_type = "admin" if role in ["ADMIN", "MANAGER", "SALES"] else "user"
    return create_access_token({"sub": str(uuid4()), "role": role, "token_type": token_type})

def test_admin_create_rbac():
    # Test ADMIN can create admin
    admin_token = _get_mock_token("ADMIN")
    payload = {
        "full_name": "New Admin",
        "email": "admin2@zbanque.com",
        "role": "MANAGER",
        "department": "Credit",
        "password": "StrongPassword1!"
    }
    
    mock_db.query.return_value.filter.return_value.first.return_value = None # No existing admin
    
    response = client.post("/admin/auth/admins", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 201
    assert "added successfully" in response.json()["data"]["admin"]

    # Test MANAGER/USER cannot create admin
    manager_token = _get_mock_token("MANAGER")
    response_mgr = client.post("/admin/auth/admins", json=payload, headers={"Authorization": f"Bearer {manager_token}"})
    assert response_mgr.status_code == 403
