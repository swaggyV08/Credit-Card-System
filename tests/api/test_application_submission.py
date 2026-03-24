import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from unittest.mock import MagicMock, patch
from datetime import date

from app.main import app
from app.api.deps import get_db, get_current_authenticated_user
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.credit_product import CreditProductInformation
from app.admin.models.card_product import CardProductCore
from app.admin.models.card_issuance import CreditCardApplication

client = TestClient(app)

# --- MOCKS ---
mock_db = MagicMock()
mock_user = User(id=uuid4(), email="test@example.com", is_active=True, is_cif_completed=True, is_kyc_completed=True)

def override_get_db():
    yield mock_db

def override_get_current_user():
    return mock_user

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_authenticated_user] = override_get_current_user

def test_submit_application_refactored_v2():
    """
    Verifies that the refactored application submission endpoint works with base URL 
    and derives card product from credit_product_code.
    """
    card_product_id = uuid4()
    credit_product_id = uuid4()
    
    # Setup database mocks
    mock_cif = MagicMock(spec=CustomerProfile)
    mock_cif.id = uuid4()
    mock_cif.user_id = mock_user.id
    mock_cif.date_of_birth = date(1990, 1, 1)
    mock_cif.country_of_residence = MagicMock()
    mock_cif.country_of_residence.value = "INDIA"
    
    mock_credit_product = MagicMock(spec=CreditProductInformation)
    mock_credit_product.id = credit_product_id
    mock_credit_product.product_code = "ZBC_PLATINUM_01"

    mock_card_product = MagicMock(spec=CardProductCore)
    mock_card_product.id = card_product_id
    mock_card_product.credit_product_id = credit_product_id
    
    # Mock sequence in submit_application:
    # 1. cif check
    # 2. credit product check (via product_code)
    # 3. card product check (via credit_product_id)
    # 4. duplicate app check
    # 5. existing account check
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_cif,           # cif query
        mock_credit_product, # credit product query
        mock_card_product,  # card product query
        None,               # duplicate app check
        None                # existing account check
    ]
    mock_db.query.return_value.filter.return_value.count.return_value = 0 # application count (limit check)
    
    # Mock behavior for application model creation
    def fake_refresh(obj):
        if isinstance(obj, CreditCardApplication):
            obj.id = uuid4()
    mock_db.refresh.side_effect = fake_refresh

    # Payload contains credit_product_code
    payload = {
        "credit_product_code": "ZBC_PLATINUM_01",
        "declared_income": 500000,
        "employment_status": "FULL_TIME",
        "residential_status": "RENTED",
        "years_at_current_address": 3,
        "preferred_billing_cycle": "5",
        "statement_delivery_mode": "ELECTRONIC",
        "card_delivery_address_type": "CURRENT_ADDRESS",
        "preferred_branch_code": "BLR001",
        "consent_terms_accepted": True,
        "consent_credit_bureau_check": True,
        "application_declaration_accepted": True
    }
    
    # Base URL: /applications/
    with patch("app.api.application.simulate_bureau_score") as mock_bureau, \
         patch("app.api.application.detect_fraud_anomalies") as mock_fraud, \
         patch("app.api.application.calculate_risk_assessment") as mock_risk:
        
        mock_bureau.return_value = {"bureau_score": 750, "report_reference_id": "REF123", "snapshot": {}}
        mock_fraud.return_value = []
        mock_risk.return_value = ("LOW", 0.95, "Clear profile")
        
        response = client.post("/applications/", json=payload)
    
    assert response.status_code == 201, response.text
    assert "application_id" in response.json()
    assert mock_db.add.called
