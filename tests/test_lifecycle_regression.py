import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api.deps import get_db
from app.core.jwt import create_access_token
from app.models.auth import User
from app.models.enums import CCMAccountStatus, CCMCardStatus, ProductStatus
from app.models.card_management import CCMCreditCard, CCMCreditAccount
from app.core.config import settings

# Use the actual database URL from settings
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# Use a valid admin UUID from the database to satisfy constraints
VALID_ADMIN_ID = "98afcb5a-9a00-4a7e-99d6-7d021b18d6cb"

@pytest.fixture
def admin_token():
    return create_access_token(data={"sub": VALID_ADMIN_ID, "role": "SUPERADMIN", "type": "ADMIN"})

@pytest.fixture
def user_token():
    return create_access_token(data={"sub": "ZBNQ-USER-777", "role": "USER", "type": "USER"})

def test_module_5_card_product_lifecycle(admin_token):
    # 1. Create Card Product
    payload = {
        "credit_product_code": "CRD-PLAT-001",
        "card_network": "VISA",
        "card_bin_range": "450010",
        "card_branding_code": "ZBANQ_PLAT",
        "card_form_factor": "PHYSICAL",
        "card_variant": "PLATINUM",
        "default_card_currency": "INR",
        "billing_config": {
            "billing_cycle_type": "MONTHLY",
            "billing_cycle_day": 1,
            "payment_due_days": 20,
            "minimum_due_formula": "5_PCT",
            "statement_generation_mode": "ELECTRONIC",
            "statement_currency": "INR",
            "grace_period_days": 3
        },
        "transaction_controls": {
            "pos_allowed": True,
            "ecommerce_allowed": True,
            "atm_withdrawal_allowed": True,
            "contactless_enabled": True,
            "international_txn_allowed": False
        },
        "fx_configuration": {
            "fx_rate_source": "VISA",
            "foreign_markup_fee_pct": 3.5
        },
        "usage_limits": {
            "cash_advance_limit_pct": 20.0,
            "domestic_txn_daily_cap": 100000.0
        },
        "rewards_config": {
            "reward_program_code": "REWARD_PLAT",
            "reward_accrual_type": "POINTS",
            "reward_earn_rate": 2.0,
            "reward_redemption_modes": ["CASHBACK"]
        },
        "authorization_rules": {
            "partial_auth_allowed": False
        },
        "lifecycle_rules": {
            "card_validity_years": 5,
            "auto_renew_card": True,
            "replacement_reason_codes": ["LOST", "STOLEN"]
        },
        "fraud_profile": {
            "fraud_monitoring_profile": "STANDARD",
            "velocity_check_profile": "STANDARD"
        }
    }
    
    response = client.post(
        "/card-products/",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if response.status_code != 201:
        print(f"DEBUG: Create Card Product Failed: {response.status_code}")
        print(response.json())
        
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    card_product_id = data["data"]["card_product_id"]
    
    # 2. Approve Card Product
    response = client.post(
        f"/card-products/{card_product_id}?command=approve",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["approved_by"] is not None

def test_module_6_admin_user_views(admin_token):
    # 1. List Users
    response = client.get(
        "/customers/",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) > 0
    user_id = response.json()["data"][0]["user_id"]
    
    # 2. Get User Detail
    response = client.get(
        f"/customers/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "full_name" in data
    assert data["full_name"] is not None

def test_module_6_credit_account_transitions(admin_token):
    # Get an active account
    response = client.get("/credit-accounts/", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    accounts = response.json()["data"]["accounts"]
    if not accounts:
        pytest.skip("No accounts existing for transition test")
        
    account_id = accounts[0]["id"]
    
    # 1. Valid Transition: ACTIVE -> SUSPENDED
    payload = {
        "status": {
            "status": "SUSPENDED",
            "reason_code": "ADMIN_ACTION",
            "notes": "Suspended for testing"
        }
    }
    response = client.patch(
        f"/credit-accounts/{account_id}?command=status",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["new_status"] == "SUSPENDED"
    
    # 2. Invalid Transition: SUSPENDED -> PENDING
    payload["status"]["status"] = "PENDING"
    response = client.patch(
        f"/credit-accounts/{account_id}?command=status",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "INVALID_TRANSITION"

def test_module_7_card_lifecycle_and_gate(admin_token, user_token):
    # Get a card ID owned by a user
    db = TestingSessionLocal()
    card = db.query(CCMCreditCard).filter(CCMCreditCard.status == "ACTIVE").first()
    if not card:
        db.close()
        pytest.skip("No ACTIVE card found for testing")
        
    card_id = str(card.id)
    owner_id = str(card.user_id)
    db.close()
    
    # 1. Ownership Gate: Access with fixture's user_token (ZBNQ-USER-777)
    if owner_id == "ZBNQ-USER-777":
        pytest.skip("Test data dependency: found card owned by fixture user.")
        
    response = client.get(
        f"/cards/{card_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "ACCESS_DENIED"
    
    # 2. Freeze/Unfreeze (Admin access)
    response = client.post(
        f"/cards/{card_id}?command=freeze",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["new_status"] == "BLOCKED_TEMP"
    
    response = client.post(
        f"/cards/{card_id}?command=unfreeze",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["new_status"] == "ACTIVE"
