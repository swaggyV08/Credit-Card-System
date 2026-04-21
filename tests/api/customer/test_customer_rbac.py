import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from unittest.mock import MagicMock
from app.main import app
from app.api.deps import get_db
from app.models.auth import User
from app.models.customer import CustomerProfile

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

def test_cif_write_requires_user_role():
    token = _get_mock_token("ADMIN") # Admins cannot write CIF
    response = client.put(
        "/customers/cif?command=personal_details",
        json={"Personal_details": {
            "nationality": "India",
            "country_of_residence": "India",
            "date_of_birth": "1990-01-01",
            "gender": "MALE",
            "marital_status": "SINGLE"
        }},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403 # RBAC forbidden
    
def test_cif_write_user_role_success():
    user_id = str(uuid4())
    token = _get_mock_token("USER") # Only users can write CIF
    from app.core.jwt import decode_access_token
    payload = decode_access_token(token)
    token_sub = payload.get("sub")
    
    mock_user = User(id=token_sub, is_cif_completed=False)
    
    # First query is get_current_user, second is profile lookup
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_user, # user
        None       # profile (none exists yet)
    ]
    
    response = client.put(
        "/customers/cif?command=personal_details",
        json={"Personal_details": {
            "nationality": "India",
            "country_of_residence": "India",
            "date_of_birth": "1990-01-01",
            "gender": "MALE",
            "marital_status": "SINGLE"
        }},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["message"] == "Personal details saved"

def test_cif_read_manager_role():
    token = _get_mock_token("MANAGER") # Manager reading CIF profile
    from app.core.jwt import decode_access_token
    payload = decode_access_token(token)
    token_sub = payload.get("sub")
    
    mock_user = User(id=token_sub, is_cif_completed=False)
    
    # Missing profile
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_user, # user lookup
        None # profile lookup
    ]
    
    response = client.get("/customers/cif/summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "PREREQUISITE_MISSING"

def test_cif_already_completed_blocked():
    token = _get_mock_token("USER")
    from app.core.jwt import decode_access_token
    payload = decode_access_token(token)
    token_sub = payload.get("sub")
    
    mock_user = User(id=token_sub, is_cif_completed=True)
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user]
    
    response = client.post("/customers/cif?command=submit", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "ALREADY_COMPLETED"
