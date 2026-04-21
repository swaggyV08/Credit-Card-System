import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from app.main import app
from app.routers.auth import get_db as auth_get_db
from app.db.session import get_db as session_get_db

@pytest.fixture
def mock_db():
    m = MagicMock()
    # Pre-configure to return None for lookups by default to avoid 409s from truthy mocks
    m.query.return_value.filter.return_value.first.return_value = None
    m.execute.return_value.scalar_one_or_none.return_value = None
    return m

@pytest.fixture
def client(mock_db):
    # The nuclear option: patch SessionLocal so everything uses the same mock_db
    # This covers lifespan (seeder) and router dependencies
    with patch("app.db.session.SessionLocal", return_value=mock_db):
        with TestClient(app) as c:
            yield c

def base_payload():
    return {
        "full_name": {"first_name": "John", "last_name": "Doe"},
        "date_of_birth": "2000-05-20",
        "email": "test@example.com",
        "phone": {"country_code": "+1", "number": "1234567890"},
        "password": "Password123!",
        "confirm_password": "Password123!"
    }

def test_register_success(client, mock_db):
    payload = base_payload()
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201

def test_register_email_uppercase_rejected(client):
    payload = base_payload()
    payload["email"] = "Test@example.com"
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["field"] == "email"
    assert "lowercase only" in response.json()["message"].lower()

def test_register_age_under_18_rejected(client):
    payload = base_payload()
    # 17 years old
    current_year = date.today().year
    payload["date_of_birth"] = f"{current_year - 17}-05-20"
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert "at least 18" in response.json()["message"].lower()

def test_register_invalid_date_rejected(client):
    payload = base_payload()
    payload["date_of_birth"] = "2000-02-30"  # Feb 30 doesn't exist
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422  # Pydantic rejects invalid calendar dates

def test_register_unsupported_country_code(client):
    payload = base_payload()
    payload["phone"]["country_code"] = "+99"
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["field"] == "phone"
    assert "country not supported" in response.json()["message"].lower()

@pytest.mark.parametrize("cc, number, is_valid, expected_msg", [
    ("+91", "1234567890", True, ""),
    ("+91", "123456789", False, "must be exactly 10 digits"),
    ("+44", "1234567890", True, ""),
    ("+61", "123456789", True, ""),
    ("+61", "1234567890", False, "must be exactly 9 digits"),
    ("+1", "1234567890", True, ""),
])
def test_register_phone_length_validation(client, mock_db, cc, number, is_valid, expected_msg):
    payload = base_payload()
    payload["phone"]["country_code"] = cc
    payload["phone"]["number"] = number
    # Re-verify it's None for each iteration
    mock_db.query.return_value.filter.return_value.first.return_value = None
    response = client.post("/auth/register", json=payload)
    if is_valid:
        assert response.status_code == 201
    else:
        assert response.status_code == 400
        assert response.json()["field"] == "phone"
        assert expected_msg in response.json()["message"]

def test_register_password_mismatch(client):
    payload = base_payload()
    payload["confirm_password"] = "Mismatch123!"
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert "Passwords do not match" in response.json()["message"]

def test_register_password_weak(client):
    payload = base_payload()
    payload["password"] = "weak"
    payload["confirm_password"] = "weak"
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert "at least 12 characters" in response.json()["message"]

def test_register_password_no_special(client):
    payload = base_payload()
    payload["password"] = "NoSpecialChar123"
    payload["confirm_password"] = "NoSpecialChar123"
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert "special character" in response.json()["message"]
