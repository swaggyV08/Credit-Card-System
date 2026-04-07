import pytest
from fastapi.testclient import TestClient
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.main import app
from app.api.deps import get_db, get_current_admin_user, get_current_authenticated_user
from app.models.auth import User
from app.models.enums import UserRole, ApplicationStatus, CardStatus, InternalRiskRating, AMLRiskCategory, AutoPayType, CardType, AccountStatus
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card, CardActivationOTP
from app.admin.models.card_product import CardProductCore, CardBillingConfiguration
from app.models.credit import BureauReport, RiskAssessment, FraudFlag

client = TestClient(app)

# --- GLOBAL MOCKS ---
mock_db = MagicMock()
mock_admin = User(id=str(uuid4())[:20], email="tester_admin@zbanque.com", status="ACTIVE")
mock_admin.role = UserRole.ADMIN

mock_customer = User(id=str(uuid4())[:20], email="customer@zbanque.com", status="ACTIVE")
mock_customer.role = UserRole.USER

def override_get_db():
    yield mock_db

def override_get_current_admin_user():
    return mock_admin

def override_get_current_authenticated_user():
    return mock_customer

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_admin_user] = override_get_current_admin_user
app.dependency_overrides[get_current_authenticated_user] = override_get_current_authenticated_user

# --- HELPER MOCK DATA ---
APP_ID = uuid4()
ACC_ID = uuid4()
CARD_PROD_ID = uuid4()
CREDIT_PROD_ID = uuid4()
CIF_ID = uuid4()

@pytest.fixture(autouse=True)
def reset_mocks():
    mock_db.reset_mock()
    mock_db.query.side_effect = None
    mock_db.query.return_value.filter.return_value.first.side_effect = None
    mock_db.query.return_value.filter.return_value.all.side_effect = None
    mock_db.query.return_value.filter.return_value.first.return_value = None

def test_full_banking_workflow():
    """
    Integration test for the multi-stage banking workflow:
    SUBMITTED -> KYC_REVIEW -> PENDING -> ACCOUNT_CREATED -> Card INACTIVE -> Card ACTIVE
    """
    
    # 1. Setup Mock Application
    mock_app = MagicMock(spec=CreditCardApplication)
    mock_app.id = APP_ID
    mock_app.user_id = mock_customer.id
    mock_app.cif_id = CIF_ID
    mock_app.application_status = ApplicationStatus.SUBMITTED
    mock_app.credit_product_id = CREDIT_PROD_ID
    mock_app.card_product_id = CARD_PROD_ID
    mock_app.declared_income = 100000
    mock_app.credit_product = MagicMock()
    mock_app.credit_product.eligibility_rules.min_credit_score = 700
    mock_app.credit_product.eligibility_rules.min_income_required = 20000
    
    # Mock related models for evaluate engine
    mock_bureau = MagicMock()
    mock_bureau.bureau_score = 750
    mock_risk = MagicMock()
    mock_risk.risk_band.value = "LOW"
    mock_risk.assessment_explanation = "Low Risk Profile"
    
    mock_acc = MagicMock(spec=CreditAccount)
    mock_acc.id = ACC_ID
    mock_acc.credit_product_id = CREDIT_PROD_ID
    mock_acc.cif_id = CIF_ID
    mock_acc.credit_limit = 200000.0
    mock_acc.available_limit = 200000.0
    mock_acc.cash_advance_limit = 40000.0
    mock_acc.billing_cycle_id = "CYCLE_05"
    mock_acc.internal_risk_rating = InternalRiskRating.LOW
    mock_acc.aml_risk_category = AMLRiskCategory.LOW
    mock_acc.account_status = AccountStatus.ACTIVE
    mock_acc.account_currency = "INR"

    mock_card_prod = MagicMock(spec=CardProductCore)
    mock_card_prod.id = CARD_PROD_ID
    mock_card_prod.credit_product_id = CREDIT_PROD_ID
    mock_card_prod.card_bin_range = "411111"

    mock_billing = MagicMock(spec=CardBillingConfiguration)
    mock_billing.billing_cycle_day = 5
    mock_billing.payment_due_days = 20

    mock_otp_record = MagicMock(spec=CardActivationOTP)
    mock_otp_record.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    mock_otp_record.otp_hash = "mock_hash"
    mock_otp_record.is_verified = False

    mock_card = MagicMock(spec=Card)
    mock_card.id = uuid4()
    mock_card.card_status = CardStatus.INACTIVE
    mock_card.credit_account = mock_acc

    def side_effect_query(*args):
        q = MagicMock()
        q.filter.return_value = q
        q.join.return_value = q
        q.order_by.return_value = q
        
        model = args[0]
        if len(args) > 1:
            # Multi-model query for get_credit_account
            q.all.return_value = [(mock_acc, mock_card_prod, mock_billing)]
            return q

        if model == CreditCardApplication:
            q.filter.return_value.first.return_value = mock_app
        elif model == BureauReport:
            q.filter.return_value.first.return_value = mock_bureau
        elif model == RiskAssessment:
            q.filter.return_value.first.return_value = mock_risk
        elif model == FraudFlag:
            q.filter.return_value.all.return_value = []
        elif model == CardProductCore:
            q.filter.return_value.first.return_value = mock_card_prod
        elif model == CreditAccount:
            q.filter.return_value.first.return_value = mock_acc
        elif model == CardBillingConfiguration:
            q.filter.return_value.first.return_value = mock_billing
        elif model == Card:
            q.filter.return_value.first.return_value = mock_card
        elif model == CardActivationOTP:
            q.first.return_value = mock_otp_record
            q.filter.return_value.order_by.return_value.first.return_value = mock_otp_record
        return q

    mock_db.query.side_effect = side_effect_query

    # --- STEP 1: Skip Manual KYC_REVIEW (Now Automatic) ---
    # Application status should already be KYC_REVIEW after KYC verification in the real flow.
    # For this test, we just ensure it's in a state that can be evaluated.
    mock_app.application_status = ApplicationStatus.KYC_REVIEW

    # --- STEP 2: Evaluate Application ---
    response = client.post(f"/applications/{APP_ID}/evaluate")
    assert response.status_code == 200, response.text
    assert response.json()["application_status"] == "APPROVED"
    assert mock_app.application_status == ApplicationStatus.APPROVED

    # --- STEP 3: Manual Configuration and Account Creation ---
    mock_db.query.side_effect = None
    # Seq: Re-fetch app, Check existing account (return None)
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_app, None]
    
    # Mock behavior for Account model creation
    def fake_refresh_acc(obj):
        if isinstance(obj, CreditAccount):
            obj.id = ACC_ID
            obj.cif_id = CIF_ID
            # Mock the property/relationship for serialization
            obj.customer_profile = MagicMock()
            obj.customer_profile.cif_number = str(CIF_ID)
            
            obj.credit_limit = 200000.0
            obj.available_limit = 200000.0
            obj.cash_advance_limit = 40000.0
            obj.outstanding_amount = 0.0
            obj.billing_cycle_id = "CYCLE_05"
            obj.internal_risk_rating = InternalRiskRating.LOW
            obj.aml_risk_category = AMLRiskCategory.LOW
            obj.account_status = AccountStatus.ACTIVE
            obj.account_currency = "INR"
            obj.opened_at = datetime.now(timezone.utc)
            obj.overlimit_allowed = True
            obj.overlimit_percentage = 10.0
    mock_db.refresh.side_effect = fake_refresh_acc

    config_payload = {
        "credit_limit": 200000.0,
        "cash_advance_limit": 40000.0,
        "billing_cycle_id": "CYCLE_05",
        "overlimit_allowed": True,
        "overlimit_percentage": 10.0,
        "autopay_enabled": False,
        "autopay_type": "MINIMUM"
    }
    
    response = client.post(f"/applications/{APP_ID}/account", json=config_payload)
    if response.status_code != 200:
        print(f"STEP 3 FAILURE: {response.status_code} - {response.text}")
    assert response.status_code == 200, response.text
    assert response.json()["credit_limit"] == 200000.0
    assert mock_app.application_status == ApplicationStatus.ACCOUNT_CREATED

    # --- STEP 4: Manual Card Issuance ---
    # Seq: Re-fetch Account, CardProduct, Check existing card (None)
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_acc, mock_card_prod, None]

    # Mock behavior for Card model creation
    def fake_refresh_card(obj):
        if isinstance(obj, Card):
            obj.id = uuid4()
            obj.credit_account_id = ACC_ID
            obj.card_product_id = CARD_PROD_ID
            obj.card_type = CardType.PRIMARY
            obj.pan_masked = "411111XXXXXX1234"
            obj.expiry_date_masked = "XX/28"
            obj.cvv_masked = "***"
            obj.card_status = CardStatus.INACTIVE
            obj.issued_at = datetime.now(timezone.utc)
            obj.international_usage_enabled = False
            obj.ecommerce_enabled = True
            obj.atm_enabled = True
    mock_db.refresh.side_effect = fake_refresh_card
    
    issue_payload = {
        "card_product_id": str(CARD_PROD_ID),
        "card_type": "PRIMARY"
    }
    
    response = client.post(f"/applications/{ACC_ID}/card", json=issue_payload)
    assert response.status_code == 200, response.text
    assert response.json()["card_status"] == "INACTIVE"
    assert response.json()["pan_masked"].startswith("411111")
    card_id = response.json()["id"]

    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_card]
    
    # --- STEP 5: Phase 1 - Generate Activation Token ---
    response = client.post(f"/customers/cards/{card_id}/activate?command=activate")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "OTP_SENT"

    # --- STEP 6: Phase 2 - Verify OTP & Set PIN ---
    # Setup mock for OTP verification success
    # mock_otp_record already defined and mocked in side_effect_query
    
    # We need to mock the sequence of queries in finalize_card_activation:
    # 1. Fetch Card
    # 2. Fetch OTP Record
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_card, mock_otp_record]
    
    # Mock verify_otp to return True
    with patch("app.admin.services.issuance_svc.verify_otp", return_value=True):
        activate_payload = {
            "otp": "123456"
        }
        
        response = client.post(f"/customers/cards/{card_id}/activate?command=verify", json=activate_payload)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ACTIVE"
        assert mock_card.card_status == CardStatus.ACTIVE

    # --- STEP 7: Set PIN ---
    set_pin_payload = {"pin": "1234"}
    response = client.post(f"/customers/cards/{card_id}/set-pin", json=set_pin_payload)
    assert response.status_code == 200, response.text
    assert "PIN has been set successfully" in response.json()["message"]

def test_negative_issuance_product_mismatch():
    """
    Test that card issuance fails if the card product belongs to a different credit product.
    """
    mock_acc = MagicMock(spec=CreditAccount)
    mock_acc.id = ACC_ID
    mock_acc.credit_product_id = CREDIT_PROD_ID
    
    mock_card_prod = MagicMock(spec=CardProductCore)
    mock_card_prod.id = CARD_PROD_ID
    mock_card_prod.credit_product_id = uuid4() # DIFFERENT!
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_acc, mock_card_prod]
    
    issue_payload = {
        "card_product_id": str(CARD_PROD_ID),
        "card_type": "PRIMARY"
    }
    
    response = client.post(f"/applications/{ACC_ID}/card", json=issue_payload)
    assert response.status_code == 400
    assert "product does not match" in response.text

def test_negative_activation_invalid_otp():
    """
    Test that card activation fails with wrong OTP.
    """
    card_id = str(uuid4())
    mock_card = MagicMock(spec=Card)
    mock_card.id = UUID(card_id)
    mock_card.card_status = CardStatus.INACTIVE
    mock_card.credit_account = MagicMock()
    mock_card.credit_account.cif_id = CIF_ID

    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_card]
    
    activate_payload = {
        "otp": "000000" # WRONG
    }
    
    # Mocking verify_otp to return False
    with patch("app.admin.services.issuance_svc.verify_otp", return_value=False):
        mock_otp_record = MagicMock() # Needs to exist to hit the verify check
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_card, mock_otp_record]
        
        response = client.post(f"/customers/cards/{card_id}/activate?command=verify", json=activate_payload)
        assert response.status_code == 400
        assert "Invalid or expired OTP" in response.text
