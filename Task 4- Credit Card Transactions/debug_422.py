from fastapi.testclient import TestClient
import uuid
import sys
import os

# Add the current directory to sys.path to import app
sys.path.append(os.getcwd())

from app.main import app
from app.api.deps import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.auth import User
from app.models.card_management import CCMCreditAccount

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def debug_422():
    db = TestingSessionLocal()
    # Mock get_db
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    
    # 1. Setup
    random_id = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"debug_{random_id}@example.com", country_code="+91", phone_number=f"99{random_id[:6]}")
    db.add(user)
    account = CCMCreditAccount(id=uuid.uuid4(), user_id=user.id, status="ACTIVE", credit_limit=1000, available_credit=1000, cash_limit=500)
    db.add(account)
    db.commit()

    # 2. Issue (to get a card_id)
    resp = client.post(f"/cards/{account.id}", json={
        "command": "issue",
        "credit_account_id": str(account.id),
        "card_product_id": str(uuid.uuid4()),
        "card_type": "PHYSICAL",
        "embossed_name": "DEBUG USER",
        "delivery_address": "Debug Address"
    })
    print(f"Issue Status: {resp.status_code}")
    if resp.status_code != 201:
        print(f"Issue Error: {resp.text}")
        return

    import re
    card_id_match = re.search(r"Card ID: ([a-f0-9\-]+)", resp.json())
    card_id = card_id_match.group(1)

    # 3. Test Command (e.g., activate)
    payload = {
        "command": "activate",
        "otp": "123456"
    }
    print(f"Sending Payload: {payload}")
    resp = client.post(f"/cards/{card_id}", json=payload)
    print(f"Response Status: {resp.status_code}")
    if resp.status_code == 422:
        print("422 Validation Error Detail:")
        import json
        print(json.dumps(resp.json(), indent=2))
    else:
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    debug_422()
