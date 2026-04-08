import pytest
from fastapi.testclient import TestClient
from uuid import uuid4, UUID
from datetime import datetime, date, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.main import app
from app.api.deps import get_db, get_current_admin_user
from app.models.auth import User
from app.models.enums import (
    UserRole, CCMAccountStatus, CCMAccountRiskFlag, 
    CCMAdjustmentType, CCMLedgerEntryType, CCMLimitReasonCode, 
    CCMStatusReasonCode, CCMAdjustmentReasonCode
)

client = TestClient(app)

# --- FIXTURES & MOCKS ---

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_admin():
    admin = User(id=uuid4().hex[:20], email="admin@zbanque.com", status="ACTIVE")
    admin.role = UserRole.ADMIN
    return admin

@pytest.fixture(autouse=True)
def setup_dependencies(mock_db, mock_admin):
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def test_account():
    account = MagicMock()
    account.id = uuid4()
    account.user_id = uuid4()
    account.product_code = "PLATINUM_CARD"
    account.status = CCMAccountStatus.ACTIVE
    account.credit_limit = Decimal("500000.00")
    account.available_credit = Decimal("420000.00")
    account.outstanding_balance = Decimal("80000.00")
    account.cash_limit = Decimal("150000.00")
    account.billing_cycle_day = 5
    account.payment_due_days = 20
    account.interest_rate = Decimal("3.49")
    account.late_fee = Decimal("1000.00")
    account.risk_flag = CCMAccountRiskFlag.NONE
    account.overlimit_enabled = False
    account.overlimit_buffer = Decimal("0.00")
    account.overlimit_fee = Decimal("0.00")
    account.purchase_apr = Decimal("3.49")
    account.cash_apr = Decimal("3.99")
    account.penalty_apr = Decimal("4.99")
    account.created_at = datetime.now()
    account.updated_at = datetime.now()
    return account

# --- TEST CASES ---

def test_list_accounts(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.count.return_value = 1
    mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [test_account]
    
    response = client.get("/admin/credit-accounts/?status=ACTIVE")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] >= 0
    assert len(data["accounts"]) > 0
    assert data["accounts"][0]["status"] == "ACTIVE"

def test_get_account_detail(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    response = client.get(f"/admin/credit-accounts/{test_account.id}")
    assert response.status_code == 200
    assert response.json()["credit_account_id"] == str(test_account.id)

def test_update_limit(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    payload = {
        "new_credit_limit": 750000,
        "reason_code": "INCOME_REVIEW",
        "notes": "Income verification completed"
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/limit", json=payload)
    assert response.status_code == 200
    assert float(response.json()["new_credit_limit"]) == 750000
    assert mock_db.commit.called

def test_update_status_flow(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    # Valid Transition: ACTIVE -> SUSPENDED
    payload = {
        "status": "SUSPENDED",
        "reason_code": "KYC_REVIEW",
        "notes": "KYC mismatch detected"
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/status", json=payload)
    assert response.status_code == 200
    assert response.json()["new_status"] == "SUSPENDED"
    
    # Invalid Transition: SUSPENDED -> DELINQUENT (assuming our logic prohibits this)
    test_account.status = CCMAccountStatus.SUSPENDED
    payload = {
        "status": "DELINQUENT",
        "reason_code": "COMPLIANCE"
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/status", json=payload)
    assert response.status_code == 400

def test_freeze_account(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    payload = {
        "freeze": True,
        "reason_code": "FRAUD_ALERT",
        "notes": "Suspicious transactions detected"
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/freeze", json=payload)
    assert response.status_code == 200
    assert response.json()["freeze_status"] == "FROZEN"

def test_update_billing_cycle(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    payload = {
        "billing_cycle_day": 15,
        "payment_due_days": 18
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/billing-cycle", json=payload)
    assert response.status_code == 200
    assert response.json()["billing_cycle_day"] == 15

def test_update_risk_flag(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    payload = {
        "risk_flag": "HIGH_RISK",
        "reason": "Multiple international transactions"
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/risk", json=payload)
    assert response.status_code == 200
    assert response.json()["risk_flag"] == "HIGH_RISK"

def test_interest_config(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    payload = {
        "purchase_apr": 3.49,
        "cash_apr": 3.99,
        "penalty_apr": 5.49
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/interest", json=payload)
    assert response.status_code == 200
    assert float(response.json()["penalty_apr"]) == 5.49

def test_overlimit_config(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    payload = {
        "overlimit_enabled": True,
        "overlimit_buffer": 50000,
        "overlimit_fee": 1000
    }
    response = client.patch(f"/admin/credit-accounts/{test_account.id}/overlimit", json=payload)
    assert response.status_code == 200
    assert response.json()["overlimit_enabled"] is True

def test_manual_adjustment(test_account, mock_db, mock_admin):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    def fake_add(obj):
        if not hasattr(obj, 'id') or not obj.id:
            obj.id = uuid4()
        if hasattr(obj, 'created_at') and not obj.created_at:
            obj.created_at = datetime.now()
            
    mock_db.flush.side_effect = lambda: None
    mock_db.add.side_effect = fake_add

    payload = {
        "adjustment_type": "CREDIT",
        "amount": 2000,
        "reason_code": "MERCHANT_DISPUTE",
        "notes": "Refund after dispute resolution"
    }
    response = client.post(f"/admin/credit-accounts/{test_account.id}/adjustment", json=payload)
    assert response.status_code == 200
    assert response.json()["adjustment_id"] is not None
    assert float(response.json()["amount"]) == 2000

def test_get_ledger(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    mock_entry = MagicMock()
    mock_entry.id = uuid4()
    mock_entry.entry_type = CCMLedgerEntryType.PURCHASE
    mock_entry.amount = Decimal("4500.00")
    mock_entry.description = "Amazon"
    mock_entry.balance_before = Decimal("0.00")
    mock_entry.balance_after = Decimal("4500.00")
    mock_entry.created_at = datetime.now()
    
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_entry]
    
    response = client.get(f"/admin/credit-accounts/{test_account.id}/ledger")
    assert response.status_code == 200
    assert len(response.json()["ledger_entries"]) == 1
    assert response.json()["ledger_entries"][0]["description"] == "Amazon"

def test_get_limits(test_account, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = test_account
    
    response = client.get(f"/admin/credit-accounts/{test_account.id}/limits")
    assert response.status_code == 200
    assert float(response.json()["credit_limit"]) == 500000
