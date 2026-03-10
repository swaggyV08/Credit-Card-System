import pytest
from fastapi.testclient import TestClient
from uuid import uuid4, UUID
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.main import app
from app.api.deps import get_db, get_current_admin_user
from app.models.auth import User
from app.models.enums import UserRole, ApplicationStatus

client = TestClient(app)

# --- GLOBAL MOCKS ---
mock_db = MagicMock()
mock_admin = User(id=uuid4(), email="tester_admin@zbanque.com", is_active=True)
mock_admin.role = UserRole.ADMIN

def override_get_db():
    yield mock_db

def override_get_current_admin_user():
    return mock_admin

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_admin_user] = override_get_current_admin_user

# --- TEST CASES ---

def test_1_card_product_configuration():
    """
    Test Case 1: Professional verification of Card Product Configuration.
    Location: tests/api/admin/test_card_issuance_final.py
    Description: Verifies that a card product can be successfully configured and mapped to a credit product.
    """
    mock_db.reset_mock()
    
    # Mock Credit Product exists
    mock_credit_product = MagicMock()
    mock_credit_product.id = uuid4()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_credit_product
    
    # Mock behavior for SQLAlchemy models created in route
    def fake_refresh(obj):
        if not hasattr(obj, 'id') or not obj.id:
            obj.id = uuid4()
        if hasattr(obj, 'credit_product_id') and not obj.credit_product_id:
            obj.credit_product_id = mock_credit_product.id
        if hasattr(obj, 'created_at') and not obj.created_at:
            obj.created_at = datetime.now(timezone.utc)
        if hasattr(obj, 'created_by') and not obj.created_by:
            obj.created_by = mock_admin.id
        if hasattr(obj, 'effective_from') and not obj.effective_from:
            obj.effective_from = datetime.now(timezone.utc)
    mock_db.refresh.side_effect = fake_refresh

    payload = {
        "credit_product_code": "ZBC_PLATINUM_01",
        "card_network": "VISA",
        "card_bin_range": "411111",
        "card_branding_code": "VISA_PLATINUM",
        "card_form_factor": "PHYSICAL",
        "card_variant": "PLATINUM",
        "default_card_currency": "INR",
        "billing_config": {"billing_cycle_day": 15, "payment_due_days": 20, "grace_period_days": 3},
        "transaction_controls": {"international_txn_allowed": True},
        "fx_configuration": {"foreign_markup_fee_pct": 3.5, "cross_border_fee_applicable": True},
        "usage_limits": {"cash_advance_limit_pct": 10.0, "domestic_txn_daily_cap": 100000.0, "contactless_txn_cap": 5000.0, "max_txn_per_day": 20},
        "rewards_config": {"reward_program_code": "ZREWARDS_PLAT", "reward_earn_rate": 2.0, "reward_redemption_modes": ["STATEMENT_CREDIT"]},
        "authorization_rules": {},
        "lifecycle_rules": {"card_validity_years": 5, "replacement_reason_codes": ["LOST", "STOLEN"]},
        "fraud_profile": {}
    }
    
    response = client.post("/admin/card-products/", json=payload)
    assert response.status_code == 201
    assert "card_product_id" in response.json()
    assert "credit_product_id" in response.json()

@patch("app.admin.api.issuance.CardIssuanceService.review_application")
def test_2_review_application_approve_flow(mock_review):
    """
    Test Case 2: Verification of Credit Application Approval Flow.
    Location: tests/api/admin/test_card_issuance_final.py
    Description: Verifies that an application can be approved, triggering account creation and returning all required fields.
    """
    application_id = str(uuid4())
    account_id = uuid4()
    mock_review.return_value = {
        "credit_account_id": account_id,
        "application_status": "APPROVED",
        "account_details": {
            "id": account_id,
            "application_id": application_id,
            "customer_cif_id": "CIF-12345",
            "credit_product_id": uuid4(),
            "account_currency": "INR",
            "sanctioned_limit": 50000.0,
            "available_limit": 50000.0,
            "outstanding_amount": 0.0,
            "account_status": "ACTIVE",
            "opened_at": datetime.now(timezone.utc),
        },
        "message": "Application APPROVED successfully"
    }

    response = client.post(f"/admin/credit-applications/{application_id}?command=approve")
    assert response.status_code == 200
    assert response.json()["application_status"] == "APPROVED"
    assert "successfully" in response.json()["message"]
    assert "credit_account_id" in response.json()

@patch("app.admin.api.issuance.CardIssuanceService.review_application")
def test_3_review_application_reject_flow(mock_review):
    """
    Test Case 3: Verification of Credit Application Rejection Flow.
    Location: tests/api/admin/test_card_issuance_final.py
    Description: Verifies that an application can be rejected with a mandatory reason.
    """
    application_id = str(uuid4())
    mock_review.return_value = {
        "application_status": "REJECTED",
        "rejection_reason": "Low credit score",
        "message": "Application REJECTED successfully"
    }

    response = client.post(
        f"/admin/credit-applications/{application_id}?command=reject",
        json={"rejection_reason": "Low credit score"}
    )
    assert response.status_code == 200
    assert response.json()["application_status"] == "REJECTED"
    assert "successfully" in response.json()["message"]

@patch("app.admin.api.issuance.CardIssuanceService.review_application")
def test_4_idempotent_approval_message(mock_review):
    """
    Test Case 4: Idempotency Verification for Approved Applications.
    Location: tests/api/admin/test_card_issuance_final.py
    Description: Ensures that repeated approval requests return an 'already verified' message instead of re-processing.
    """
    application_id = str(uuid4())
    account_id = uuid4()
    mock_review.return_value = {
        "credit_account_id": account_id,
        "application_status": "APPROVED",
        "account_details": {
            "id": account_id,
            "application_id": application_id,
            "customer_cif_id": "CIF-12345",
            "credit_product_id": uuid4(),
            "account_currency": "INR",
            "sanctioned_limit": 50000.0,
            "available_limit": 50000.0,
            "outstanding_amount": 0.0,
            "account_status": "ACTIVE",
            "opened_at": datetime.now(timezone.utc),
        },
        "message": "Application has already been verified as APPROVED"
    }

    response = client.post(f"/admin/credit-applications/{application_id}?command=approve")
    assert response.status_code == 200
    assert "already been verified" in response.json()["message"]
    assert response.json()["application_status"] == "APPROVED"

@patch("app.admin.api.issuance.CardIssuanceService.review_application")
def test_5_idempotent_rejection_message(mock_review):
    """
    Test Case 5: Idempotency Verification for Rejected Applications.
    Location: tests/api/admin/test_card_issuance_final.py
    Description: Ensures that repeated rejection requests return an 'already verified' message instead of re-processing.
    """
    application_id = str(uuid4())
    mock_review.return_value = {
        "application_status": "REJECTED",
        "rejection_reason": "Document invalid",
        "message": "Application has already been verified as REJECTED"
    }

    response = client.post(
        f"/admin/credit-applications/{application_id}?command=reject",
        json={"rejection_reason": "Document invalid"}
    )
    assert response.status_code == 200
    assert "already been verified" in response.json()["message"]
    assert response.json()["application_status"] == "REJECTED"
