import os
os.environ["TESTING"] = "true"

import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from app.main import app
from app.core.app_error import AppError
from app.core.rbac import require, AuthenticatedPrincipal

pytestmark = pytest.mark.asyncio

HEADERS = {
    "Authorization": "Bearer fake-token",
    "Idempotency-Key": "test-idem-key",
    "card_id": str(uuid.uuid4())
}

def _mock_decode(token: str) -> dict:
    return {"sub": str(uuid.uuid4()), "role": "USER", "exp": 9999999999}

def _base_auth_req():
    return {
        "amount": 100.50,
        "merchant": "Amazon",
        "category": "PURCHASE",
        "merchant_country": "US",
        "description": "Test"
    }

# 1. SUCCESS
async def test_auth_success():
    mock_resp = {
        "transaction_id": str(uuid.uuid4()),
        "account_id": str(uuid.uuid4()),
        "status": "AUTHORIZED",
        "amount": 100.50,
        "foreign_fee": 3.01,
        "hold_amount": 103.51,
        "merchant": "Amazon",
        "category": "PURCHASE",
        "merchant_country": "US",
        "is_foreign": True,
        "authorization_code": "ABCDEF12",
        "available_credit_before": 1000.0,
        "available_credit_after": 896.49,
        "idempotency_key": "test-idem-key",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, return_value=mock_resp):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 201
        assert res.json()["status"] == "AUTHORIZED"

# 2. 422 VALIDATION_ERROR (Amount < 0)
async def test_auth_invalid_amount():
    req = _base_auth_req()
    req["amount"] = -10
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=req, headers=HEADERS)
        assert res.status_code == 422
        assert res.json()["error_code"] == "VALIDATION_ERROR"

# 3. 422 VALIDATION_ERROR (Invalid Country code)
async def test_auth_invalid_country():
    req = _base_auth_req()
    req["merchant_country"] = "USA"
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=req, headers=HEADERS)
        assert res.status_code == 422
        assert res.json()["error_code"] == "VALIDATION_ERROR"

# 4. 422 MISSING_IDEMPOTENCY_KEY
async def test_auth_missing_idempotency_key():
    headers = HEADERS.copy()
    del headers["Idempotency-Key"]
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=headers)
        assert res.status_code == 422
        assert res.json()["error_code"] == "VALIDATION_ERROR"

# 5. 402 INSUFFICIENT_CREDIT
async def test_auth_insufficient_credit():
    err = AppError("INSUFFICIENT_CREDIT", "Not enough", 402)
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 402
        assert res.json()["error_code"] == "INSUFFICIENT_CREDIT"

# 6. 403 CARD_BLOCKED
async def test_auth_card_blocked():
    err = AppError("CARD_BLOCKED", "Blocked", 403)
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 403
        assert res.json()["error_code"] == "CARD_BLOCKED"

# 7. 403 CARD_EXPIRED
async def test_auth_card_expired():
    err = AppError("CARD_EXPIRED", "Expired", 403)
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 403
        assert res.json()["error_code"] == "CARD_EXPIRED"

# 8. 403 FRAUD_DETECTED
async def test_auth_fraud_detected():
    err = AppError("FRAUD_DETECTED", "Fraud", 403)
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 403
        assert res.json()["error_code"] == "FRAUD_DETECTED"

# 9. 404 CARD_NOT_FOUND
async def test_auth_card_not_found():
    err = AppError("CARD_NOT_FOUND", "No card", 404)
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 404
        assert res.json()["error_code"] == "CARD_NOT_FOUND"

# 10. 409 DUPLICATE_IDEMPOTENCY_KEY
async def test_auth_duplicate_idem():
    from app.core.exceptions import IdempotencyConflictError
    err = IdempotencyConflictError("Duplicate!")
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 409
        assert res.json()["error_code"] == "DUPLICATE_IDEMPOTENCY_KEY"

# 11. 429 VELOCITY_EXCEEDED
async def test_auth_velocity_exceeded():
    err = AppError("VELOCITY_EXCEEDED", "Too fast", 429)
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 429
        assert res.json()["error_code"] == "VELOCITY_EXCEEDED"

# 12. 403 FORBIDDEN (Prohibited Country)
async def test_auth_prohibited_country():
    err = AppError("FORBIDDEN", "Prohibited Country", 403)
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.authorize", new_callable=AsyncMock, side_effect=err):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/credit-cards/{HEADERS['card_id']}/transactions", json=_base_auth_req(), headers=HEADERS)
        assert res.status_code == 403
        assert res.json()["error_code"] == "FORBIDDEN"

# Query Transaction Dual Mode
async def test_query_transactions():
    mock_resp = {
        "page": 1, "limit": 20, "total": 1, "pages": 1, "sort_by": "timestamp", "order": "desc",
        "items": []
    }
    with patch("app.core.rbac.decode_access_token", side_effect=_mock_decode), \
         patch("app.routers.transactions.TransactionEngine.query_transactions", new_callable=AsyncMock, return_value=mock_resp):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(f"/credit-cards/{HEADERS['card_id']}/transactions?transaction_id={uuid.uuid4()}", headers=HEADERS)
        assert res.status_code == 200
        assert res.json()["total"] == 1
