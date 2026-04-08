import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from unittest.mock import MagicMock

from app.main import app
from app.api.deps import get_current_admin_user, get_db
from app.models.auth import User
from app.models.enums import UserRole, AccountStatus, CardStatus
from app.models.customer import CustomerProfile
from app.admin.models.card_issuance import CreditAccount, Card

client = TestClient(app)

# Mock Data
USER_ID = uuid4()
CIF_ID = uuid4()
ACC_ID = uuid4()
CARD_ID = uuid4()

def override_get_current_admin_user():
    user = User(id=uuid4().hex[:20], email="admin@zbanque.com", status="ACTIVE")
    user.role = UserRole.ADMIN
    return user

def override_get_db():
    db = MagicMock()
    
    # Mock for list view
    mock_item = MagicMock()
    mock_item.cif_id = "CIF123"
    mock_item.credit_account_id = ACC_ID
    mock_item.card_id = CARD_ID
    mock_item.account_status = AccountStatus.ACTIVE
    
    db.query.return_value.select_from.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.all.return_value = [mock_item]
    
    # Mock for detail view
    mock_user = User(id=USER_ID, email="user@test.com", phone_number="1234567890", status="ACTIVE", is_cif_completed=True)
    mock_profile = CustomerProfile(user_id=USER_ID, id=CIF_ID, first_name="John", last_name="Doe", cif_number="CIF123")
    mock_account = CreditAccount(id=ACC_ID, cif_id=CIF_ID, readable_id="ACC001", account_status=AccountStatus.ACTIVE)
    mock_card = Card(id=CARD_ID, credit_account_id=ACC_ID, readable_id="CARD001", card_status=CardStatus.ACTIVE, pan_masked="4111XXXX1234")
    
    # Configure query mock to return these based on the calls in user_mgmt.py
    def side_effect(model):
        q = MagicMock()
        if model == User:
            q.filter.return_value.first.return_value = mock_user
        elif model == CustomerProfile:
            q.filter.return_value.first.return_value = mock_profile
        elif model == CreditAccount:
            q.filter.return_value.all.return_value = [mock_account]
        elif model == Card:
            q.filter.return_value.all.return_value = [mock_card]
        return q
    
    db.query.side_effect = side_effect
    
    return db

app.dependency_overrides[get_current_admin_user] = override_get_current_admin_user
app.dependency_overrides[get_db] = override_get_db

def test_list_customers_admin():
    response = client.get("/customers/")
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert response.json()[0]["cif_id"] == "CIF123"

def test_get_customer_detail_admin():
    response = client.get(f"/customers/{USER_ID}")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@test.com"
    assert data["total_credit_accounts"] == 1
    assert data["total_cards"] == 1
    assert data["credit_accounts"][0]["cards"][0]["card_readable_id"] == "CARD001"
