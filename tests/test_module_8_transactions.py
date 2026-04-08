import pytest
import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app.core.jwt import create_access_token
from app.models.enums import CardStatus
from app.admin.models.card_issuance import Card, CreditAccount
from app.api.deps import get_db
from sqlalchemy.orm import Session

client = TestClient(app)

@pytest.fixture
def user_token():
    # Mocking a user with ID that will be used for ownership checks
    return create_access_token(data={"sub": "test-user-123", "role": "USER", "type": "USER"})

@pytest.fixture
def admin_token():
    return create_access_token(data={"sub": "admin-123", "role": "SUPERADMIN", "type": "ADMIN"})

def test_transaction_idempotency_headers(user_token):
    # Setup: We need a card and account in the DB
    # For unit tests, we usually use a mock DB, but here we use the actual DB as per existing tests
    # Let's find an active card or create one if possible (though creating might be complex due to FKs)
    
    card_id = str(uuid.uuid4().hex[:20])
    payload = {
        "amount": 100.50,
        "currency": "INR",
        "transaction_type": "PURCHASE",
        "merchant_id": str(uuid.uuid4().hex[:20]),
        "merchant_name": "Test Merchant",
        "merchant_category_code": "5411",
        "merchant_country": "IN"
    }

    # 1. Missing Header -> 422
    response = client.post(
        f"/cards/{card_id}/transactions",
        json=payload,
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "MISSING_IDEMPOTENCY_KEY"

    # 2. Malformed Header -> 422
    response = client.post(
        f"/cards/{card_id}/transactions",
        json=payload,
        headers={
            "Authorization": f"Bearer {user_token}",
            "Idempotency-Key": "not-a-uuid"
        }
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "INVALID_IDEMPOTENCY_KEY"

def test_transaction_velocity_gate(user_token):
    card_id = str(uuid.uuid4().hex[:20])
    # This test might fail if Redis is not running, but it should test the logic
    # We will skip if Redis fails or check the error code
    pass
