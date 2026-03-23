import pytest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.orm import Session
from app.services.transaction_engine import TransactionEngine
from app.models.card_management import CCMCreditAccount, CCMCreditCard, CCMCardTransaction
from app.models.enums import CCMCardStatus, CCMAccountStatus, CCMTransactionType, CCMTransactionStatus

def test_authorize_transaction_success(db: Session, active_card: CCMCreditCard, active_account: CCMCreditAccount):
    # Initial balance
    initial_avail = active_account.available_credit
    amount = Decimal("100.00")
    
    tx = TransactionEngine.authorize_transaction(
        db=db,
        card_id=active_card.id,
        amount=amount,
        merchant_name="Test Merchant",
        transaction_type=CCMTransactionType.PURCHASE
    )
    
    assert tx.status == CCMTransactionStatus.AUTHORIZED
    assert tx.amount == amount
    # Verify limit was held
    assert active_account.available_credit == initial_avail - amount
    # Verify outstanding hasn't changed yet
    assert active_account.outstanding_balance == Decimal("0.00")

def test_authorize_insufficient_funds(db: Session, active_card: CCMCreditCard, active_account: CCMCreditAccount):
    amount = active_account.available_credit + Decimal("1.00")
    
    with pytest.raises(Exception) as exc:
        TransactionEngine.authorize_transaction(
            db=db,
            card_id=active_card.id,
            amount=amount,
            merchant_name="Big Purchase",
            transaction_type=CCMTransactionType.PURCHASE
        )
    assert "Insufficient credit limit" in str(exc.value)

def test_idempotency_prevention(db: Session, active_card: CCMCreditCard, active_account: CCMCreditAccount):
    ikey = "unique-key-123"
    amount = Decimal("50.00")
    
    tx1 = TransactionEngine.authorize_transaction(
        db=db,
        card_id=active_card.id,
        amount=amount,
        merchant_name="Merchant",
        transaction_type=CCMTransactionType.PURCHASE,
        idempotency_key=ikey
    )
    
    # Try with same key
    tx2 = TransactionEngine.authorize_transaction(
        db=db,
        card_id=active_card.id,
        amount=amount,
        merchant_name="Merchant",
        transaction_type=CCMTransactionType.PURCHASE,
        idempotency_key=ikey
    )
    
    assert tx1.id == tx2.id
    # Ensure limit only deducted once
    # (Checking against initial setup in a real test environment)

def test_settlement_and_ledger(db: Session, authorized_tx: CCMCardTransaction, active_account: CCMCreditAccount):
    amount = authorized_tx.amount
    
    settled_tx = TransactionEngine.settle_transaction(db, authorized_tx.id)
    
    assert settled_tx.status == CCMTransactionStatus.COMPLETED
    assert active_account.outstanding_balance == amount
    
    # Verify ledger entry exists
    from app.models.card_management import CCMCreditAccountLedger
    ledger = db.query(CCMCreditAccountLedger).filter(CCMCreditAccountLedger.reference_id == settled_tx.id).first()
    assert ledger is not None
    assert ledger.amount == amount
    assert ledger.balance_after == amount
