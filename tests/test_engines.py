import os
os.environ["TESTING"] = "true"

import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.transaction_engine import TransactionEngine
from app.services.billing_engine import BillingEngine
from app.services.payment_engine import PaymentEngine
from app.services.batch_processing import BatchProcessingEngine
from app.services.fee_evaluator import FeeEvaluator
from app.core.app_error import AppError

pytestmark = pytest.mark.asyncio

class MockSession(AsyncMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adds = []
        
    async def flush(self):
        pass
        
    async def commit(self):
        pass
        
    async def rollback(self):
        pass
        
    def add(self, entity):
        self.adds.append(entity)
        
    def begin(self):
        class Ctx:
            async def __aenter__(self):
                pass
            async def __aexit__(self, *a):
                pass
        return Ctx()

def make_mock_result(scalar_val=None, scalars_list=None):
    m = MagicMock()
    m.scalar_one_or_none.return_value = scalar_val
    m.scalar_one.return_value = scalar_val
    m.scalar.return_value = scalar_val
    sm = MagicMock()
    sm.all.return_value = scalars_list or []
    m.scalars.return_value = sm
    return m

# ---- Transaction Engine ----
async def test_tx_engine_success():
    db = MockSession()
    # Mocking in order of execution
    card_mock = MagicMock(id=uuid.uuid4(), credit_account_id=uuid.uuid4(), card_status="ACTIVE", expiry_date="12/2099")
    acc_mock = MagicMock(id=uuid.uuid4(), home_country="IN", available_limit=Decimal("50000"), outstanding_amount=Decimal("0"))
    db.execute = AsyncMock(side_effect=[
        make_mock_result(), # idempotency
        make_mock_result(card_mock), # card
        make_mock_result(), # prohibited
        make_mock_result(acc_mock), # account
        make_mock_result(), # velocity/fraud... wait these are direct functions not DB
    ])
    
    req = MagicMock(merchant_country="IN", amount=100.0, category="PURCHASE", merchant="A", description="desc")
    
    with patch("app.services.velocity_service.VelocityService.check_velocity"), \
         patch("app.services.velocity_service.VelocityService.record_transaction"), \
         patch("app.services.velocity_service.FraudService.run_fraud_checks", return_value={"flagged": False}):
        
        res = await TransactionEngine.authorize(db, str(card_mock.id), "user1", "idem1", req)
        
    assert res["status"] == "AUTHORIZED"
    
async def test_tx_engine_errors():
    db = MockSession()
    
    # 1. Card not found
    db.execute = AsyncMock(side_effect=[make_mock_result(), make_mock_result()])
    with pytest.raises(AppError) as ci:
        await TransactionEngine.authorize(db, str(uuid.uuid4()), "user", "idem", MagicMock())
    assert ci.value.code == "CARD_NOT_FOUND"

    # 2. Blocked Card
    cmock = MagicMock(card_status="BLOCKED")
    db.execute = AsyncMock(side_effect=[make_mock_result(), make_mock_result(cmock)])
    with pytest.raises(AppError):
        await TransactionEngine.authorize(db, str(uuid.uuid4()), "user", "idem", MagicMock())


# ---- Billing Engine ----
async def test_billing_generate():
    db = MockSession()
    acc_mock = MagicMock(id=uuid.uuid4())
    card_mock = MagicMock(id=uuid.uuid4(), credit_account_id=acc_mock.id)
    prev_bill = MagicMock(total_due=Decimal("1000"))
    
    mock_txn = MagicMock(amount=Decimal("500"), foreign_fee=None, transaction_type="PURCHASE")
    
    db.execute = AsyncMock(side_effect=[
        make_mock_result(acc_mock), # Account
        make_mock_result(),         # Bill idempotency
        make_mock_result(scalars_list=[card_mock]), # Cards
        make_mock_result(prev_bill), # Prev bill
        make_mock_result(scalars_list=[mock_txn]), # Txns
        make_mock_result(scalars_list=[]), # Fees
        make_mock_result(scalars_list=[]), # Pmts
    ])
    
    res = await BillingEngine.generate_bill(db, str(acc_mock.id), "2026-04-01")
    assert "bill_id" in res
    assert float(res["total_due"]) > 1000

# ---- Payment Engine ----
async def test_payment_engine():
    db = MockSession()
    acc_id = uuid.uuid4()
    bill_id = uuid.uuid4()
    
    bill_mock = MagicMock(id=bill_id, account_id=acc_id, total_due=Decimal("1000.00"), min_payment_due=Decimal("100.00"), status="UNPAID")
    acc_mock = MagicMock(id=acc_id, available_limit=Decimal("5000"), outstanding_amount=Decimal("1000"))
    
    db.execute = AsyncMock(side_effect=[
        make_mock_result(bill_mock),
        make_mock_result(acc_mock)
    ])
    
    req = MagicMock(amount=Decimal("1000.00"), payment_type="FULL")
    res = await PaymentEngine.process(db, str(acc_id), str(bill_id), "user", req)
    
    assert res["is_full_payment"] is True
    assert res["amount_paid"] == Decimal("1000.00")

# ---- Batch Processing Mock ----
async def test_batch_clearing():
    db = MockSession()
    txn_mock = MagicMock(amount=Decimal("100.00"), status="AUTHORIZED")
    db.execute = AsyncMock(side_effect=[make_mock_result(scalars_list=[txn_mock])])
    res = await BatchProcessingEngine.process_clearing(db, "2026-04-01", "user")
    assert res["transactions_cleared"] == 1

# ---- Fee Evaluator Mock ----
async def test_fee_evaluate():
    db = MockSession()
    card_mock = MagicMock(id=uuid.uuid4(), credit_account_id=uuid.uuid4())
    db.execute = AsyncMock(side_effect=[make_mock_result(card_mock)])
    req = MagicMock(amount=50.0, fee_type="LATE", reason="test")
    res = await FeeEvaluator.assess_fee(db, str(card_mock.id), req, "user")
    assert res["status"] == "POSTED"

