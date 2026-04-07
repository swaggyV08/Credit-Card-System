import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dateutil.relativedelta import relativedelta

from app.main import app
from app.api.deps import get_db
from app.core.config import settings
from app.models.auth import User, AuthCredential
from app.models.customer import CustomerProfile, OTPCode, OTPPurpose
from app.core import otp as otp_util

# Use the same DB as the app for this integration test
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
    app.dependency_overrides.pop(get_db, None)

def test_kyc_regression_full_flow(client, db_session):
    # --- STEP 1: Register User ---
    test_email = f"test_kyc_{uuid.uuid4().hex[:6]}@zbanque.com"
    test_phone = "9876543210"
    dob = date(1990, 1, 1)
    
    reg_payload = {
        "full_name": "KYC Tester",
        "email": test_email,
        "contact": {
            "country_code": "+91",
            "phone_number": test_phone
        },
        "date_of_birth": dob.isoformat(),
        "password": "Password@123456",
        "confirm_password": "Password@123456"
    }
    
    resp = client.post("/auth/registrations", json=reg_payload)
    assert resp.status_code == 201, resp.text
    initial_user_id = resp.json()["data"]["user_id"]
    
    # --- STEP 2: Generate OTP ---
    gen_resp = client.post(f"/auth/otp/{initial_user_id}?command=generate", json={
        "purpose": "REGISTRATION"
    })
    assert gen_resp.status_code == 200
    
    # --- STEP 3: Verify OTP ---
    # Fetch OTP from DB to verify
    otp_record = db_session.query(OTPCode).filter(OTPCode.user_id == initial_user_id).first()
    # We set a known OTP for testing
    known_otp = "111111"
    otp_record.otp_hash = otp_util.hash_otp(known_otp)
    otp_record.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db_session.commit()
    
    verify_resp = client.post(f"/auth/otp/{initial_user_id}?command=verify", json={
        "purpose": "REGISTRATION",
        "otp": known_otp
    })
    assert verify_resp.status_code == 200
    
    # Check user status
    user = db_session.query(User).filter(User.id == initial_user_id).first()
    assert user.status == "ACTIVE"
    
    # --- STEP 4: Login ---
    login_resp = client.post("/auth/login?command=USER", json={
        "email": test_email,
        "password": "Password@123456"
    })
    assert login_resp.status_code == 200
    initial_jwt = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {initial_jwt}"}
    
    # --- STEP 5: Submit CIF (Staged) ---
    # 1. Personal
    cif_p = client.put("/customers/cif?command=personal_details", json={
        "Personal_details": {
            "nationality": "India",
            "country_of_residence": "India",
            "date_of_birth": {"year": 1990, "month": 1, "day": 1},
            "gender": "MALE",
            "marital_status": "SINGLE",
            "preferred_language": "EN"
        }
    }, headers=headers)
    assert cif_p.status_code == 200, cif_p.text
    
    # 2. Residential (Trigger cross-check for < 3 years)
    cif_r = client.put("/customers/cif?command=residential_details", json={
        "Residential_details": {
            "addresses": [
                {
                    "type": "CURRENT",
                    "residence_type": "Owned",
                    "years_at_address": 1, # < 3 years, requires PREVIOUS
                    "line1": "123 Current St",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "country": "India",
                    "pincode/Zipcode": "560001"
                },
                {
                    "type": "PREVIOUS",
                    "residence_type": "Rented",
                    "years_at_address": 5,
                    "line1": "456 Previous St",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "country": "India",
                    "pincode/Zipcode": "400001"
                }
            ]
        }
    }, headers=headers)
    assert cif_r.status_code == 200, cif_r.text
    
    # 3. Employment
    cif_e = client.put("/customers/cif?command=employment_details", json={
        "Employment_details": {
            "employment_type": "FULL_TIME",
            "organisation_name": "ZBANQUe",
            "designation": "Tester",
            "annual_income": "1200000.000"
        }
    }, headers=headers)
    assert cif_e.status_code == 200, cif_e.text
    
    # 4. Financial
    cif_f = client.put("/customers/cif?command=financial_details", json={
        "Financial_details": {
            "net_annual_income": "1000000.000",
            "monthly_income": "80000.000",
            "other_income": "0.000",
            "housing_payment": "20000.000",
            "other_obligations": "5000.000"
        }
    }, headers=headers)
    assert cif_f.status_code == 200, cif_f.text
    
    # 5. FATCA
    cif_fatca = client.put("/customers/cif?command=fatca_details", json={
        "Fatca_details": {
            "us_citizen": False,
            "us_tax_resident": False
        }
    }, headers=headers)
    assert cif_fatca.status_code == 200
    
    # FINAL SUBMIT (Identity Migration)
    submit_resp = client.post("/customers/cif?command=submit", headers=headers)
    assert submit_resp.status_code == 200
    data = submit_resp.json()["data"]
    new_user_id = data["user_id"]
    new_jwt = data["access_token"]
    
    assert new_user_id.startswith("ZBNQ")
    assert new_jwt != initial_jwt
    
    # --- STEP 6: Capture New JWT & STEP 7: POST /customers/kyc ---
    new_headers = {"Authorization": f"Bearer {new_jwt}"}
    
    # Test file upload
    from io import BytesIO
    file_content = b"fake pdf content"
    file_name = "test_kyc.pdf"
    
    kyc_resp = client.post(
        "/customers/kyc",
        params={
            "command": "upload",
            "document_type": "PAN",
            "document_number": "ABCDE1234F"
        },
        files={
            "file": (file_name, BytesIO(file_content), "application/pdf")
        },
        headers=new_headers
    )
    
    # --- STEP 8: Assert 200 ---
    assert kyc_resp.status_code == 200, kyc_resp.text
    kyc_data = kyc_resp.json()["data"]
    assert kyc_data["message"] == "KYC SUBMITTED"
    assert "submission_id" in kyc_data
    assert kyc_data["storage"] == "server_fs"
    
    # Assert final DB state
    final_user = db_session.query(User).filter(User.id == new_user_id).first()
    assert final_user is not None
    assert final_user.is_cif_completed is True
    assert final_user.is_kyc_completed is True
    
    profile = db_session.query(CustomerProfile).filter(CustomerProfile.user_id == new_user_id).first()
    assert profile.customer_status == "ACTIVE"
