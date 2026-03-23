import sys
import os
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.main import app
from app.db.session import get_db
from app.models.auth import User
from app.models.customer import OTPPurpose, KYCState, CustomerProfile

client = TestClient(app)

def test_kyc_flow_mock():
    print("\n--- Testing KYC Flow (Mocked) ---")
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    # Mock user
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.is_cif_completed = True
    mock_user.is_kyc_completed = False
    
    # Mock profile
    mock_profile = MagicMock(spec=CustomerProfile)
    mock_profile.kyc_state = KYCState.NOT_STARTED
    
    from app.api.deps import get_current_authenticated_user
    app.dependency_overrides[get_current_authenticated_user] = lambda: mock_user

    # Setup query side effects for KYC
    def query_side_effect(model):
        if model == CustomerProfile:
            m = MagicMock()
            m.filter.return_value.first.return_value = mock_profile
            return m
        # For CreditCardApplication
        m = MagicMock()
        m.filter.return_value.all.return_value = []
        return m

    mock_db.query.side_effect = query_side_effect

    # Mock file upload
    import io
    file = io.BytesIO(b"fake data")
    
    with patch("app.api.customer.shutil.copyfileobj"), \
         patch("app.api.customer.os.makedirs"):
        response = client.post(
            "/customers/kyc?command=upload",
            files={"file": ("test.jpg", file, "image/jpeg")},
            data={"document_type": "PAN", "document_number": "ABCDE1234F"}
        )
    
    if response.status_code != 200:
        print(f"Error KYC: {response.json()}")
    assert response.status_code == 200
    assert response.json()["message"] == "KYC SUBMITTED"
    assert mock_user.is_kyc_completed == True
    assert mock_profile.kyc_state == KYCState.COMPLETED
    print("KYC Flow Verified!")

def test_otp_dispatcher_mock():
    print("\n--- Testing OTP Dispatcher (Mocked) ---")
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock user and registration
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.email = "test@example.com"
    
    from app.models.pending_registration import PendingRegistration
    mock_reg = MagicMock(spec=PendingRegistration)
    mock_reg.email = "test@example.com"
    mock_reg.password = "Pass123"

    mock_profile = MagicMock(spec=CustomerProfile)

    # Dispatcher Logic is complex, let's simplify query mocking
    # 1. Resolve user/registration
    # 2. command=generate: Query OTPCode update, add OTPCode
    # 3. command=verify: Query OTPCode, update verified, side effects
    
    def dispatcher_query_side_effect(model):
        m = MagicMock()
        if model == PendingRegistration:
            m.filter.return_value.first.return_value = mock_reg
            return m
        if model == User:
            m.filter.return_value.first.return_value = mock_user
            return m
        if model == CustomerProfile:
            # Used in registration side effect
            return MagicMock() 
        # For OTPCode in verify
        m.filter_by.return_value.filter.return_value.order_by.return_value.first.return_value = MagicMock()
        return m

    mock_db.query.side_effect = dispatcher_query_side_effect

    # 1. Test Generate
    response = client.post("/auth/otp/test@example.com?command=generate", json={"purpose": "REGISTRATION"})
    assert response.status_code == 200
    assert "generated successfully" in response.json()["message"]
    print("OTP Generate Verified!")

    # 2. Test Verify (Registration)
    with patch("app.api.auth.verify_otp", return_value=True), \
         patch("app.api.auth.hash_value", return_value="hash"):
        response = client.post("/auth/otp/test@example.com?command=verify", json={"purpose": "REGISTRATION", "otp": "123456"})
    
    if response.status_code != 200:
        print(f"Error Verify: {response.json()}")
    assert response.status_code == 200
    assert "Registration successful" in response.json()["message"]
    print("OTP Verify (Registration) Verified!")

if __name__ == "__main__":
    test_kyc_flow_mock()
    test_otp_dispatcher_mock()
    print("\nALL MOCKED TESTS PASSED!")
