import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.main import app
from app.api.deps import get_db, get_current_admin_user
from app.models.auth import User
from app.models.enums import UserRole

client = TestClient(app)

# --- MOCKS ---
mock_db = MagicMock()
mock_admin = User(id=uuid4(), email="admin@zbanque.com", is_active=True)
mock_admin.role = UserRole.ADMIN

def override_get_db():
    yield mock_db

def override_get_current_admin_user():
    return mock_admin

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_admin_user] = override_get_current_admin_user

# --- TESTS ---

def test_1_create_card_product():
    """
    Test Case 1: Create Card Product Configuration
    Description: Verifies that an admin can configure a new card product.
    Location: tests/api/admin/test_card_issuance_v2.py
    """
    mock_db.reset_mock()
    mock_credit_product = MagicMock()
    mock_credit_product.id = uuid4()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_credit_product
    
    def fake_refresh(obj):
        if not hasattr(obj, 'id') or not obj.id: obj.id = uuid4()
        if hasattr(obj, 'created_at') and not obj.created_at: obj.created_at = datetime.now(timezone.utc)
        if hasattr(obj, 'created_by') and not obj.created_by: obj.created_by = mock_admin.id
    mock_db.refresh.side_effect = fake_refresh

    payload = {
        "credit_product_code": "ZBC_PLAT_01",
        "card_network": "VISA",
        "card_bin_range": "411111",
        "card_branding_code": "VISA_PLAT",
        "card_form_factor": "PHYSICAL",
        "card_variant": "PLATINUM",
        "billing_config": {"billing_cycle_day": 1, "payment_due_days": 20, "grace_period_days": 3},
        "transaction_controls": {"international_txn_allowed": True},
        "fx_configuration": {"foreign_markup_fee_pct": 3.5, "cross_border_fee_applicable": True},
        "usage_limits": {"cash_advance_limit_pct": 10.0, "domestic_txn_daily_cap": 50000.0, "contactless_txn_cap": 5000.0, "max_txn_per_day": 10},
        "rewards_config": {"reward_program_code": "R1", "reward_earn_rate": 1.0, "reward_redemption_modes": ["CASH"]},
        "authorization_rules": {},
        "lifecycle_rules": {"card_validity_years": 5, "replacement_reason_codes": ["LOST"]},
        "fraud_profile": {}
    }
    
    response = client.post("/admin/card-products/", json=payload)
    assert response.status_code == 201
    assert "card_product_id" in response.json()

@patch("app.admin.services.issuance_svc.CardIssuanceService.review_application")
def test_2_approve_application(mock_review):
    """
    Test Case 2: Approve Credit Application
    Description: Verifies that an application is successfully approved.
    Location: tests/api/admin/test_card_issuance_v2.py
    """
    app_id = str(uuid4())
    mock_review.return_value = {
        "credit_account_id": uuid4(),
        "application_status": "APPROVED",
        "account_details": {"account_status": "ACTIVE"},
        "message": "Application APPROVED successfully"
    }

    response = client.post(f"/admin/credit-applications/{app_id}?command=approve")
    assert response.status_code == 200
    assert response.json()["application_status"] == "APPROVED"
    assert "successfully" in response.json()["message"]

@patch("app.admin.services.issuance_svc.CardIssuanceService.review_application")
def test_3_reject_application_idempotent(mock_review):
    """
    Test Case 3: Idempotent Rejection
    Description: Verifies that repeated rejection returns the already verified message.
    Location: tests/api/admin/test_card_issuance_v2.py
    """
    app_id = str(uuid4())
    mock_review.return_value = {
        "application_status": "REJECTED",
        "rejection_reason": "Low Score",
        "message": "Application has already been verified as REJECTED"
    }

    response = client.post(f"/admin/credit-applications/{app_id}?command=reject", json={"rejection_reason": "Low Score"})
    assert response.status_code == 200
    assert "already been verified" in response.json()["message"]
