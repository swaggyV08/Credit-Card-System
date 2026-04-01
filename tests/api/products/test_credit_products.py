import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.main import app
from app.api.deps import get_db
from app.admin.models.credit_product import CreditProductInformation

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

def test_get_all_credit_products_rbac_admin_allowed():
    token = _get_mock_token("ADMIN")
    mock_db.query.return_value.count.return_value = 0
    mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    
    resp = client.get("/credit-products?command=all", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

def test_get_all_credit_products_rbac_manager_allowed():
    token = _get_mock_token("MANAGER")
    mock_db.query.return_value.count.return_value = 0
    mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    
    resp = client.get("/credit-products?command=all", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

def test_get_all_credit_products_rbac_user_forbidden():
    token = _get_mock_token("USER")
    resp = client.get("/credit-products?command=all", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

def test_get_by_id_valid():
    token = _get_mock_token("ADMIN")
    product_id = str(uuid4())
    
    mock_product = MagicMock(spec=CreditProductInformation)
    mock_product.id = product_id
    # We must mock validate dumps to avoid pydantic errors on MagicMock
    with patch("app.admin.api.credit_product.CreditProductResponse.model_validate") as mock_val:
        mock_val.return_value.model_dump.return_value = {"id": product_id, "status": "DRAFT"}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        
        resp = client.get(f"/credit-products?command=by_id&product_id={product_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

def test_get_by_id_missing_param_returns_422():
    token = _get_mock_token("ADMIN")
    resp = client.get("/credit-products?command=by_id", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "MISSING_PRODUCT_ID"

def test_post_create_admin_allowed():
    token = _get_mock_token("ADMIN")
    payload = {
        "product_name": "Test Card",
        "product_category": "CREDIT",
        "limits": {"min_credit_limit": 1000, "max_credit_limit": 50000},
        "interest_framework": {"annual_percentage_rate": 18.0},
        "fees": {"annual_fee": 100},
        "eligibility_rules": {"min_age": 18, "min_income": 20000},
        "compliance_metadata": {"kyc_required": True},
        "accounting_mapping": {"gl_asset_account": "1000"},
        "auto_renewal_allowed": True,
        "cooling_period_days": 30
    }
    
    mock_product = MagicMock()
    mock_product.id = str(uuid4())
    mock_product.product_code = "cp-12345"
    
    with patch("app.admin.api.credit_product.CreditProductCreateResponse.model_validate") as mock_val:
        mock_val.return_value.model_dump.return_value = {"id": mock_product.id}
        def fake_refresh(obj):
            obj.id = mock_product.id
            obj.product_code = mock_product.product_code
        mock_db.refresh.side_effect = fake_refresh
        
        resp = client.post("/credit-products", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

def test_post_create_manager_forbidden():
    token = _get_mock_token("MANAGER")
    resp = client.post("/credit-products", json={"product_name": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

def test_delete_admin_allowed():
    token = _get_mock_token("ADMIN")
    product_id = str(uuid4())
    
    with patch("app.admin.services.credit_product_svc.CreditProductService.delete_product") as mock_delete:
        mock_delete.return_value = {"message": "deleted", "product_id": product_id}
        resp = client.delete(f"/credit-products/{product_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

def test_delete_sales_forbidden():
    token = _get_mock_token("SALES")
    resp = client.delete(f"/credit-products/{str(uuid4())}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

def test_pagination():
    token = _get_mock_token("ADMIN")
    mock_db.query.return_value.count.return_value = 45
    mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    
    resp = client.get("/credit-products?command=all&page=2&page_size=20", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total"] == 45
    assert data["meta"]["total_pages"] == 3
    assert data["meta"]["has_next"] is True
    assert data["meta"]["has_previous"] is True
