import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from io import BytesIO

from app.main import app
from app.api.deps import get_db
from app.core.config import settings
from app.models.auth import User, AuthCredential
from app.models.customer import CustomerProfile, OTPCode, OTPPurpose
from app.models.admin import Admin
from app.core.roles import Role
from app.core import otp as otp_util
from app.admin.models.credit_product import CreditProductInformation, CreditProductEligibilityRules, CreditProductGovernance
from app.admin.models.card_product import CardProductCore
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card
from app.models.enums import ApplicationStatus, ApplicationStage, RiskBand, ActorType, KYCState

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

def test_underwriting_full_lifecycle(client, db_session):
    """
    Module 4 Regression: Full Lifecycle of Credit Card Underwriting & Issuance.
    """
    # --- PRE-REQUISITE: Seed Admin ---
    admin = db_session.query(Admin).filter(Admin.role == Role.SUPERADMIN).first()
    if not admin:
        admin = Admin(
            id=uuid.uuid4(),
            email=f"admin_{uuid.uuid4().hex[:6]}@zbanque.com",
            password_hash="fake",
            full_name="Regression Admin",
            role=Role.SUPERADMIN,
            employee_id="REG-01"
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)

    # --- PRE-REQUISITE: Seed Credit Product ---
    product_code = "test_visa_001" 
    product = db_session.query(CreditProductInformation).filter(
        CreditProductInformation.product_code == product_code
    ).first()
    
    if not product:
        product = CreditProductInformation(
            id=uuid.uuid4(),
            product_code=product_code,
            product_name="Test Visa Platinum",
            product_version=1,
            status="ACTIVE"
        )
        db_session.add(product)
        db_session.flush()
        
        rules = CreditProductEligibilityRules(
            credit_product_id=product.id,
            min_age=21,
            max_age=60,
            min_income_required=500000,
            employment_types_allowed=["SALARIED", "SELF_EMPLOYED"],
            min_credit_score=700
        )
        db_session.add(rules)
        
        gov = CreditProductGovernance(
            credit_product_id=product.id,
            cooling_period_days=90,
            created_by=admin.id
        )
        db_session.add(gov)
        
        card_product = CardProductCore(
            id=uuid.uuid4(),
            credit_product_id=product.id,
            card_network="VISA",
            card_bin_range="4532",
            card_branding_code="PLATINUM",
            card_variant="PLATINUM"
        )
        db_session.add(card_product)
        db_session.commit()
    else:
        card_product = db_session.query(CardProductCore).filter(CardProductCore.credit_product_id == product.id).first()

    # --- STEP 1: Register User ---
    test_email = f"underwrite_{uuid.uuid4().hex[:6]}@zbanque.com"
    test_phone = "9988776655"
    
    reg_payload = {
        "full_name": "Underwriting Tester",
        "email": test_email,
        "contact": {"country_code": "+91", "phone_number": test_phone},
        "date_of_birth": "1990-01-01",
        "password": "Password@123456",
        "confirm_password": "Password@123456"
    }
    
    resp = client.post("/auth/registrations", json=reg_payload)
    assert resp.status_code == 201
    initial_user_id = resp.json()["data"]["user_id"]
    
    # Generate OTP
    client.post(f"/auth/otp/{initial_user_id}?command=generate", json={"purpose": "REGISTRATION"})

    # Verify OTP
    otp_record = db_session.query(OTPCode).filter(OTPCode.user_id == initial_user_id).first()
    known_otp = "123456"
    otp_record.otp_hash = otp_util.hash_otp(known_otp)
    otp_record.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db_session.commit()
    
    client.post(f"/auth/otp/{initial_user_id}?command=verify", json={"purpose": "REGISTRATION", "otp": known_otp})
    
    # Login
    login_resp = client.post("/auth/login?command=USER", json={"email": test_email, "password": "Password@123456"})
    initial_jwt = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {initial_jwt}"}
    
    # --- STEP 2: CIF Submission ---
    client.put("/customers/cif?command=personal_details", json={
        "Personal_details": {
            "nationality": "India", "country_of_residence": "India",
            "date_of_birth": {"year": 1990, "month": 1, "day": 1},
            "gender": "MALE", "marital_status": "SINGLE", "preferred_language": "EN"
        }
    }, headers=headers)
    client.put("/customers/cif?command=residential_details", json={
        "Residential_details": {
            "addresses": [{
                "type": "CURRENT", "residence_type": "Owned", "years_at_address": 5,
                "line1": "Integration Blvd", "city": "Mumbai", "state": "Maharashtra", "country": "India", "pincode/Zipcode": "400001"
            }]
        }
    }, headers=headers)
    client.put("/customers/cif?command=employment_details", json={
        "Employment_details": {
            "employment_type": "FULL_TIME", "organisation_name": "TestCorp", "designation": "Engineer", "annual_income": "900000.00"
        }
    }, headers=headers)
    client.put("/customers/cif?command=financial_details", json={
        "Financial_details": {
            "net_annual_income": "850000.00", "monthly_income": "70000.00", "other_income": "0.00", "housing_payment": "10000.00", "other_obligations": "2000.00"
        }
    }, headers=headers)
    client.put("/customers/cif?command=fatca_details", json={"Fatca_details": {"us_citizen": False, "us_tax_resident": False}}, headers=headers)
    
    submit_resp = client.post("/customers/cif?command=submit", headers=headers)
    assert submit_resp.status_code == 200
    new_jwt = submit_resp.json()["data"]["access_token"]
    new_user_id = submit_resp.json()["data"]["user_id"]
    new_headers = {"Authorization": f"Bearer {new_jwt}"}
    
    # --- STEP 3: Manual KYC Approval ---
    # Update User record
    user = db_session.query(User).filter(User.id == new_user_id).first()
    assert user is not None
    user.is_kyc_completed = True
    user.status = "ACTIVE"
    
    # Update Profile record
    profile = db_session.query(CustomerProfile).filter(CustomerProfile.user_id == new_user_id).first()
    assert profile is not None
    profile.kyc_state = KYCState.COMPLETED.value
    profile.customer_status = "ACTIVE"
    
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(profile)

    # --- STEP 4: Submit Application ---
    app_payload = {
        "credit_product_code": product_code,
        "declared_income": 750000.0,
        "income_frequency": "ANNUAL",
        "employment_status": "SALARIED",
        "occupation": "SOFTWARE_ENGINEER",
        "employer_name": "TestCorp",
        "work_experience_years": 5,
        "residential_status": "OWNED",
        "years_at_current_address": 3,
        "preferred_billing_cycle": "15th",
        "statement_delivery_mode": "ELECTRONIC",
        "card_delivery_address_type": "CURRENT",
        "preferred_branch_code": "MUM_001",
        "consent_terms_accepted": True,
        "consent_credit_bureau_check": True,
        "application_declaration_accepted": True
    }
    app_submit_resp = client.post("/applications/", json=app_payload, headers=new_headers)
    assert app_submit_resp.status_code == 200, app_submit_resp.text
    application_id = app_submit_resp.json()["data"]["application_id"]

    # --- STEP 5: Admin Evaluation ---
    from app.core.jwt import create_access_token
    admin_token = create_access_token(data={"sub": str(admin.id), "role": Role.SUPERADMIN.value, "type": "ADMIN"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    eval_resp = client.post(f"/applications/{new_user_id}?command=evaluate&application_id={application_id}", headers=admin_headers)
    assert eval_resp.status_code == 200, eval_resp.text
    assert eval_resp.json()["data"]["application_status"] == "APPROVED"

    # --- STEP 6: Admin Configuration ---
    config_payload = {
        "credit_limit": 100000.0,
        "cash_advance_limit": 20000.0,
        "billing_cycle_id": "CYCLE_01",
        "overlimit_allowed": False,
        "overlimit_percentage": 0.0,
        "autopay_enabled": False
    }
    conf_resp = client.post(f"/applications/{new_user_id}?command=configure&application_id={application_id}", json=config_payload, headers=admin_headers)
    assert conf_resp.status_code == 200, conf_resp.text
    # Note: Schema uses 'credit_account_id' as key, not 'id'
    credit_account_id = conf_resp.json()["data"]["credit_account_id"]

    # --- STEP 7: Card Issuance ---
    issue_payload = {
        "card_product_id": str(card_product.id),
        "card_type": "PRIMARY"
    }
    issue_resp = client.post(f"/applications/{credit_account_id}/card", json=issue_payload, headers=admin_headers)
    assert issue_resp.status_code == 200, issue_resp.text
    card_data = issue_resp.json()["data"]
    assert card_data["card_status"] == "INACTIVE"
    assert "id" in card_data
