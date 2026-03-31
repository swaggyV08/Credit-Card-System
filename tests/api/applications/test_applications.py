import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from unittest.mock import MagicMock, patch

from app.main import app
from app.api.deps import get_db
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.credit_product import CreditProductInformation
from app.admin.models.card_product import CardProductCore
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount
from app.models.enums import ApplicationStatus, ApplicationStage

client = TestClient(app)

mock_db = MagicMock()

def override_get_db():
    yield mock_db

app.dependency_overrides[get_db] = override_get_db

def _get_mock_token(role: str):
    from app.core.jwt import create_access_token
    token_type = "ADMIN" if role in ["ADMIN", "MANAGER", "SALES"] else "USER"
    return create_access_token({"sub": str(uuid4()), "role": role, "type": token_type})

@pytest.fixture(autouse=True)
def reset_mocks():
    mock_db.reset_mock()

def test_get_all_applications_rbac():
    token_manager = _get_mock_token("MANAGER")
    token_user = _get_mock_token("USER")
    
    # Needs application:read. Based on typical setup, MANAGER should be allowed. 
    # Let's try MANAGER token.
    mock_db.query.return_value.count.return_value = 0
    mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    
    resp_manager = client.get("/applications?command=all", headers={"Authorization": f"Bearer {token_manager}"})
    assert resp_manager.status_code == 200

def test_get_by_user_input_guard():
    token = _get_mock_token("MANAGER")
    user_id = str(uuid4())
    resp = client.get(
        f"/applications?command=by_user&user_id={user_id}&status_filter=APPROVED",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "INVALID_SIGNATURE"
    
def test_post_evaluate_body_guard():
    token = _get_mock_token("MANAGER")
    user_id = str(uuid4())
    app_id = str(uuid4())
    
    mock_user = User(id=user_id, is_cif_completed=True, is_kyc_completed=True)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    
    resp = client.post(
        f"/applications/{user_id}?command=evaluate&application_id={app_id}",
        json={"some": "body"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "NO_BODY_ACCEPTED"

def test_post_evaluate_success():
    token = _get_mock_token("MANAGER")
    user_id = str(uuid4())
    app_id = str(uuid4())
    
    mock_user = User(id=user_id, is_cif_completed=True, is_kyc_completed=True)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    
    with patch("app.admin.services.issuance_svc.CardIssuanceService.evaluate_application") as eval_mock:
        eval_mock.return_value = {"status": "APPROVED"}
        resp = client.post(
            f"/applications/{user_id}?command=evaluate&application_id={app_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        
def test_application_gateway_cif_incomplete():
    token = _get_mock_token("USER")
    payload = _decode_token(token)
    
    # Missing CIF -> 422 CIF_INCOMPLETE
    mock_user = User(id=payload["sub"], is_cif_completed=False, is_kyc_completed=False)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    
    resp = client.post(
        "/applications/",
        json={
            "credit_product_code": "ZBC_PLATINUM_01", 
            "declared_income": 1000,
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
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert resp.json()["errors"][0]["code"] == "CIF_INCOMPLETE"

def _decode_token(token: str):
    from app.core.jwt import decode_access_token
    return decode_access_token(token)
