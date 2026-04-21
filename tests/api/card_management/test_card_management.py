import os
import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api.deps import get_db
from app.db.base_class import Base

from app.core.config import settings


engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """
    Creates a fresh sqlalchemy session for each test, 
    nested in a transaction that is rolled back at the end.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

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

from app.models.auth import User

@pytest.fixture(scope="function")
def test_user(db_session):
    user_id = uuid.uuid4().hex[:20]
    user = User(
        id=user_id,
        email=f"ccm_test_{uuid.uuid4().hex[:20].hex[:8]}@example.com",
        country_code="+91",
        phone_number="1234567890",
        status="ACTIVE"
    )
    db_session.add(user)
    db_session.flush() 
    return str(user_id)


def test_card_issuance_creates_credit_account(client, db_session, test_user):
    response = client.post("/cards/issue", json={
        "user_id": test_user,
        "credit_limit": 50000.0,
        "card_network": "VISA",
        "card_variant": "CLASSIC"
    })
    
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "INACTIVE"
    assert data["user_id"] == test_user
    
    account = data.get("credit_account")
    assert account is not None
    assert float(account["credit_limit"]) == 50000.0
    assert float(account["available_credit"]) == 50000.0
    assert float(account["outstanding_balance"]) == 0.0
    assert float(account["cash_limit"]) == 10000.0

def test_card_activation(client, db_session, test_user):
    issue_resp = client.post("/cards/issue", json={
        "user_id": test_user,
        "credit_limit": 10000.0
    }).json()
    card_id = issue_resp["id"]
    last_four = issue_resp["card_number"][-4:]
    expiry = issue_resp["expiry_date"]
    
    activate_resp = client.post(f"/cards/{card_id}/activate", json={
        "last_four_digits": last_four,
        "expiry_date": expiry
    })
    
    assert activate_resp.status_code == 200
    data = activate_resp.json()
    assert data["status"] == "ACTIVE"
    assert data["activated_at"] is not None

def test_card_blocking(client, db_session, test_user):
    issue_resp = client.post("/cards/issue", json={"user_id": test_user, "credit_limit": 10000.0}).json()
    card_id = issue_resp["id"]
    client.post(f"/cards/{card_id}/activate", json={
        "last_four_digits": issue_resp["card_number"][-4:],
        "expiry_date": issue_resp["expiry_date"]
    })
    
    block_resp = client.post(f"/cards/{card_id}/block", json={"reason": "USER_REQUEST"})
    assert block_resp.status_code == 200
    assert block_resp.json()["status"] == "BLOCKED_USER"
    assert block_resp.json()["blocked_reason"] == "USER_REQUEST"

def test_credit_limit_update(client, db_session, test_user):
    issue_resp = client.post("/cards/issue", json={"user_id": test_user, "credit_limit": 10000.0}).json()
    card_id = issue_resp["id"]
    
    limit_resp = client.patch(f"/cards/{card_id}/limits", json={"new_credit_limit": 20000.0})
    assert limit_resp.status_code == 200
    assert limit_resp.json()["new_available_credit"] == 20000.0

def test_transaction_deducts_credit(client, db_session, test_user):
    issue_resp = client.post("/cards/issue", json={"user_id": test_user, "credit_limit": 10000.0}).json()
    card_id = issue_resp["id"]
    client.post(f"/cards/{card_id}/activate", json={
        "last_four_digits": issue_resp["card_number"][-4:],
        "expiry_date": issue_resp["expiry_date"]
    })
    
    charge_resp = client.post(f"/v1/cards/{card_id}/transactions", json={
        "amount": 1000.0,
        "merchant": "Test Store",
        "category": "PURCHASE",
        "merchant_country": "US"
    }, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert charge_resp.status_code == 201
    
    card_details = client.get(f"/cards/{card_id}").json()
    acc = card_details["credit_account"]
    
    assert float(acc["available_credit"]) == 9000.0 
    assert float(acc["outstanding_balance"]) == 1000.0

def test_transaction_reversal(client, db_session, test_user):
    issue_resp = client.post("/cards/issue", json={"user_id": test_user, "credit_limit": 10000.0}).json()
    card_id = issue_resp["id"]
    client.post(f"/cards/{card_id}/activate", json={
        "last_four_digits": issue_resp["card_number"][-4:],
        "expiry_date": issue_resp["expiry_date"]
    })
    
    charge_resp = client.post(f"/v1/cards/{card_id}/transactions", json={
        "amount": 2500.0,
        "merchant": "Test Store 2",
        "category": "PURCHASE",
        "merchant_country": "US"
    }, headers={"Idempotency-Key": str(uuid.uuid4())}).json()
    
    tx_id = charge_resp["id"]
    
    rev_resp = client.post(f"/v1/cards/{card_id}/transactions/{tx_id}/reverse", json={"reason": "Test reversal"})
    assert rev_resp.status_code == 200
    
    card_details = client.get(f"/cards/{card_id}").json()
    assert float(card_details["credit_account"]["available_credit"]) == 10000.0
    assert float(card_details["credit_account"]["outstanding_balance"]) == 0.0

def test_card_replacement_flow(client, db_session, test_user):
    issue_resp = client.post("/cards/issue", json={"user_id": test_user, "credit_limit": 15000.0}).json()
    card_id = issue_resp["id"]
    original_account_id = issue_resp["credit_account"]["id"]
    
    client.post(f"/cards/{card_id}/activate", json={
        "last_four_digits": issue_resp["card_number"][-4:],
        "expiry_date": issue_resp["expiry_date"]
    })
    
    rep_resp = client.post(f"/cards/{card_id}/replace")
    assert rep_resp.status_code == 200
    
    new_card = rep_resp.json()
    assert new_card["status"] == "INACTIVE"
    assert new_card["id"] != card_id
    
    old_card = client.get(f"/cards/{card_id}").json()
    assert old_card["status"] == "REPLACED"

    assert new_card["credit_account"]["id"] == original_account_id

def test_fraud_block(client, db_session, test_user):
    issue_resp = client.post("/cards/issue", json={"user_id": test_user, "credit_limit": 10000.0}).json()
    card_id = issue_resp["id"]
    client.post(f"/cards/{card_id}/activate", json={
        "last_four_digits": issue_resp["card_number"][-4:],
        "expiry_date": issue_resp["expiry_date"]
    })
    
    client.post(f"/v1/cards/{card_id}/transactions", json={
        "amount": 500.0,
        "merchant": "Store India",
        "category": "PURCHASE",
        "merchant_country": "IN"
    }, headers={"Idempotency-Key": str(uuid.uuid4())})
    
    charge2 = client.post(f"/v1/cards/{card_id}/transactions", json={
        "amount": 500.0,
        "merchant": "Store US",
        "category": "PURCHASE",
        "merchant_country": "US"
    }, headers={"Idempotency-Key": str(uuid.uuid4())})
    
    assert charge2.status_code == 403
    assert "fraud" in charge2.json()["detail"].lower()
    
    card_after = client.get(f"/cards/{card_id}").json()
    assert card_after["status"] == "BLOCKED_FRAUD"
    assert card_after["blocked_reason"] == "GEO_MISMATCH"
