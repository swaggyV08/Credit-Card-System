import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db.session import get_async_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.core.roles import Role
from app.models.auth import User
from app.models.bureau import BureauScore
from app.models.enums import BureauRiskBand, ScoreTrigger

client = TestClient(app)

# Mocked DB
mock_async_db = AsyncMock(spec=AsyncSession)

async def override_get_async_db():
    yield mock_async_db

app.dependency_overrides[get_async_db] = override_get_async_db

@pytest.fixture(autouse=True)
def setup_test_env():
    from app.core.config import settings
    # Ensure SECRET_KEY is long enough for HS256 (32 bytes)
    settings.SECRET_KEY = "supersecretkey_must_be_at_least_32_bytes_long_12345"
    
    # Properly reset the mock
    mock_async_db.reset_mock()
    mock_async_db.execute.side_effect = None
    mock_async_db.execute.return_value = None
    
    app.dependency_overrides[get_async_db] = override_get_async_db
    yield
    app.dependency_overrides.clear()

def _get_token(user_id: str, role: Role):
    from app.core.jwt import create_access_token
    token_type = "admin" if role in [Role.ADMIN, Role.MANAGER, Role.SALES, Role.SUPERADMIN] else "user"
    return create_access_token({"sub": user_id, "role": role.value, "token_type": token_type})

def test_get_score_user_success():
    user_id = str(uuid.uuid4().hex[:20])
    token = _get_token(user_id, Role.USER)
    
    mock_user = User(id=user_id, email="test@zbanque.com", is_cif_completed=True)
    mock_score = BureauScore(
        user_id=uuid.UUID(user_id), score=750, risk_band=BureauRiskBand.VERY_GOOD,
        trigger_event=ScoreTrigger.PAYMENT_MADE, computed_at=datetime.now(timezone.utc),
        payment_history_score=350, utilisation_score=300, credit_history_score=100,
        transaction_behaviour_score=0, derogatory_score=0, on_time_payment_count=10,
        late_payment_count=0, missed_payment_count=0, current_utilisation_pct=10.5,
        account_age_days=365, total_transactions_90d=5, disputes_90d=0, chargebacks_total=0
    )

    # Mock execute calls: user exist query, then latest score query
    mock_async_db.execute.side_effect = [
        MagicMock(scalar=lambda: mock_user),  # user existence
        MagicMock(scalar=lambda: mock_score)  # latest score
    ]

    response = client.get("/bureau/score", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["score"] == 750
    assert data["data"]["risk_band"] == "VERY_GOOD"
    assert "score_interpretation" in data["data"]

def test_get_score_admin_success():
    admin_id = str(uuid.uuid4().hex[:20])
    target_user_id = str(uuid.uuid4().hex[:20])
    token = _get_token(admin_id, Role.ADMIN)
    
    mock_user = User(id=target_user_id, email="target@zbanque.com", is_cif_completed=True)
    mock_score = BureauScore(
        user_id=uuid.UUID(target_user_id), score=600, risk_band=BureauRiskBand.FAIR,
        trigger_event=ScoreTrigger.MANUAL_REQUEST, computed_at=datetime.now(timezone.utc),
        payment_history_score=100, utilisation_score=100, credit_history_score=100,
        transaction_behaviour_score=100, derogatory_score=100, on_time_payment_count=5,
        late_payment_count=0, missed_payment_count=0, current_utilisation_pct=50.0,
        account_age_days=100, total_transactions_90d=10, disputes_90d=0, chargebacks_total=0
    )

    mock_async_db.execute.side_effect = [
        MagicMock(scalar=lambda: mock_user),
        MagicMock(scalar=lambda: mock_score)
    ]

    response = client.get(f"/bureau/score?user_id={target_user_id}", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 200
    assert response.json()["data"]["score"] == 600

def test_get_score_missing_user_id_400():
    admin_id = str(uuid.uuid4().hex[:20])
    token = _get_token(admin_id, Role.ADMIN)
    
    response = client.get("/bureau/score", headers={"Authorization": f"Bearer {token}"}) # No user_id query param
    
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "MISSING_USER_ID"

def test_get_score_user_not_found_404():
    user_id = str(uuid.uuid4().hex[:20])
    token = _get_token(user_id, Role.USER)
    
    mock_async_db.execute.return_value = MagicMock(scalar=lambda: None) # User not found
    
    response = client.get("/bureau/score", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "USER_NOT_FOUND"

def test_get_score_cif_incomplete_400():
    user_id = str(uuid.uuid4().hex[:20])
    token = _get_token(user_id, Role.USER)
    
    mock_user = User(id=user_id, is_cif_completed=False)
    mock_async_db.execute.return_value = MagicMock(scalar=lambda: mock_user)
    
    response = client.get("/bureau/score", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "CIF_INCOMPLETE"

def test_get_score_not_yet_computed_404():
    user_id = str(uuid.uuid4().hex[:20])
    token = _get_token(user_id, Role.USER)
    
    mock_user = User(id=user_id, is_cif_completed=True)
    mock_async_db.execute.side_effect = [
        MagicMock(scalar=lambda: mock_user),
        MagicMock(scalar=lambda: None) # Score not found
    ]
    
    response = client.get("/bureau/score", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "SCORE_NOT_YET_COMPUTED"

@patch("app.routers.bureau.compute_bureau_score")
@patch("app.core.redis.redis_service.get_client")
def test_trigger_score_success(mock_redis, mock_compute):
    user_id = str(uuid.uuid4().hex[:20])
    admin_id = str(uuid.uuid4().hex[:20])
    token = _get_token(admin_id, Role.ADMIN)
    
    mock_user = User(id=user_id, is_cif_completed=True)
    mock_async_db.execute.return_value = MagicMock(scalar=lambda: mock_user)
    
    mock_redis_client = MagicMock()
    mock_redis.return_value = mock_redis_client
    mock_redis_client.get.return_value = None # No rate limit hit
    
    mock_new_score = BureauScore(
        score=800, risk_band=BureauRiskBand.VERY_GOOD, computed_at=datetime.now(timezone.utc),
        trigger_event=ScoreTrigger.MANUAL_REQUEST
    )
    mock_compute.return_value = mock_new_score
    
    response = client.post(f"/bureau/score/trigger?user_id={user_id}", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 201
    assert response.json()["data"]["score"] == 800
    assert mock_redis_client.setex.called or mock_redis_client.incr.called

@patch("app.core.redis.redis_service.get_client")
def test_trigger_score_rate_limit_429(mock_redis):
    user_id = str(uuid.uuid4().hex[:20])
    admin_id = str(uuid.uuid4().hex[:20])
    token = _get_token(admin_id, Role.ADMIN)
    
    mock_user = User(id=user_id, is_cif_completed=True)
    mock_async_db.execute.return_value = MagicMock(scalar=lambda: mock_user)
    
    mock_redis_client = MagicMock()
    mock_redis.return_value = mock_redis_client
    mock_redis_client.get.return_value = "3" # Hit limit
    mock_redis_client.ttl.return_value = 1800
    
    response = client.post(f"/bureau/score/trigger?user_id={user_id}", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 429
    assert response.json()["errors"][0]["code"] == "TRIGGER_RATE_LIMIT"
    assert response.headers["Retry-After"] == "1800"

def test_trigger_score_no_body_accepted_422():
    user_id = str(uuid.uuid4().hex[:20])
    admin_id = str(uuid.uuid4().hex[:20])
    token = _get_token(admin_id, Role.ADMIN)
    
    response = client.post(f"/bureau/score/trigger?user_id={user_id}", json={"something": "not allowed"}, headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "NO_BODY_ACCEPTED"

def test_get_history_invalid_date_range_400():
    user_id = str(uuid.uuid4().hex[:20])
    token = _get_token(user_id, Role.USER)
    
    response = client.get(f"/bureau/score/history?from_date=2024-01-02&to_date=2024-01-01", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "INVALID_DATE_RANGE"
