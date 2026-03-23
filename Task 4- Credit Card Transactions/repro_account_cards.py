import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from app.main import app
from app.db.base_class import Base
from app.api.deps import get_db, get_current_admin_user
from app.core.config import settings
from app.models.auth import User
from app.models.card_management import CCMCreditAccount, CCMCreditCard
from app.models.enums import CCMCardStatus, UserRole

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

mock_admin = User(id=uuid.uuid4(), email="admin@test.com", is_active=True)
mock_admin.role = UserRole.ADMIN

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

def override_admin():
    return mock_admin

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_admin_user] = override_admin

client = TestClient(app)

def run_test():
    db = TestingSessionLocal()
    # Create user & account & card
    test_user = User(id=uuid.uuid4(), email="test_card_view@test.com", phone_number="9999999997", country_code="+91", is_active=True)
    test_account = CCMCreditAccount(id=uuid.uuid4(), user_id=test_user.id, credit_limit=50000, available_credit=50000, status="ACTIVE", outstanding_balance=0, cash_limit=10000, billing_cycle_day=1, minimum_due=0, interest_rate=1, late_fee=0)
    
    card_id = uuid.uuid4()
    test_card = CCMCreditCard(id=card_id, user_id=test_user.id, card_number="4111111111111113", card_network="VISA", card_variant="CLASSIC", expiry_date="12/25", cvv_hash="abc", status=CCMCardStatus.ACTIVE, credit_account=test_account, is_contactless_enabled=True, is_international_enabled=True, is_online_enabled=True, is_atm_enabled=True, is_domestic_enabled=True)
    
    # Needs to manually map card_id for older SQLAlchemy back_populates if it doesn't auto-flush
    db.add_all([test_user, test_account, test_card])
    db.commit()

    test_account.card_id = test_card.id
    db.commit()

    try:
        resp = client.get(f"/admin/credit-accounts/{test_account.id}")
        data = resp.json()
        print("Response from GET /admin/credit-accounts/{id}:")
        import json
        print(json.dumps(data, indent=2))
        
        assert "card_count" in data, "card_count missing"
        assert data["card_count"] == 1, f"Expected 1 card, got {data['card_count']}"
        assert "cards" in data, "cards array missing"
        assert len(data["cards"]) == 1, "Expected 1 card in array"
        assert data["cards"][0]["card_number"] == "4111111111111113"
        print("SUCCESS! Model properties successfully serialized by Pydantic.")
        
    finally:
        db.delete(test_card)
        db.delete(test_account)
        db.delete(test_user)
        db.commit()
        db.close()

if __name__ == "__main__":
    run_test()
