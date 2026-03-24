import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.card_management import (
    CCMCreditAccount, CCMCreditCard, CCMCardTransaction, 
    CCMCreditAccountLedger, CCMCreditAccountAdjustment
)
from app.models.billing import RewardEntry
from app.models.enums import (
    CCMTransactionType, CCMTransactionStatus, CCMLedgerEntryType,
    CCMCardStatus, CCMAccountStatus
)

class TransactionEngine:
    """
    Production-grade transaction engine for credit cards.
    Handles Auth, Capture, Refund, and Reversal with double-entry logic.
    """

    @staticmethod
    def authorize_transaction(
        db: Session,
        card_id: uuid.UUID,
        amount: Decimal,
        merchant_name: str,
        transaction_type: CCMTransactionType,
        idempotency_key: Optional[str] = None
    ) -> CCMCardTransaction:
        """
        Initial authorization phase.
        1. Lock Account
        2. Validate Status/Limits
        3. Create Pending Transaction
        """
        # 1. Idempotency Check
        if idempotency_key:
            existing = db.query(CCMCardTransaction).filter(CCMCardTransaction.idempotency_key == idempotency_key).first()
            if existing: return existing

        # 2. Fetch and Lock Account/Card
        # We lock the account to prevent concurrent limit depletion
        card = db.query(CCMCreditCard).filter(CCMCreditCard.id == card_id).first()
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        
        account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == card.credit_account_id).with_for_update().first()
        if not account:
            raise HTTPException(status_code=404, detail="Credit account not found")

        # 3. Validations
        if card.status != CCMCardStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Transaction rejected: Card is {card.status}")
        
        if account.status != CCMAccountStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Transaction rejected: Account is {account.status}")

        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")

        if transaction_type == CCMTransactionType.CASH_ADVANCE:
            if amount > account.cash_limit:
                raise HTTPException(status_code=400, detail="Cash advance limit exceeded")
        
        if amount > account.available_credit:
            # Check if overlimit is allowed
            if not account.overlimit_enabled or amount > (account.available_credit + account.overlimit_buffer):
                raise HTTPException(status_code=400, detail="Insufficient credit limit")

        # 4. Create Transaction Record (PENDING/AUTHORIZED)
        new_tx = CCMCardTransaction(
            card_id=card.id,
            credit_account_id=account.id,
            amount=amount,
            merchant_name=merchant_name,
            transaction_type=transaction_type,
            status=CCMTransactionStatus.AUTHORIZED,
            idempotency_key=idempotency_key
        )
        db.add(new_tx)
        
        # 5. Hold the limit (Atomic update)
        account.available_credit -= amount
        # We don't update outstanding_balance until settlement (capture)
        
        db.flush() # Flush to get new_tx.id
        return new_tx

    @staticmethod
    def settle_transaction(db: Session, transaction_id: uuid.UUID) -> CCMCardTransaction:
        """
        Settlement phase (Capture).
        Updates balances and creates ledger entries.
        """
        tx = db.query(CCMCardTransaction).filter(CCMCardTransaction.id == transaction_id).with_for_update().first()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        if tx.status != CCMTransactionStatus.AUTHORIZED:
            raise HTTPException(status_code=400, detail=f"Cannot settle transaction in {tx.status} status")

        account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == tx.credit_account_id).with_for_update().first()

        # 1. Update balances
        # available_credit was already deducted at auth
        account.outstanding_balance += tx.amount
        
        # 2. Double-entry Ledger Entry
        ledger_entry = CCMCreditAccountLedger(
            credit_account_id=account.id,
            entry_type=CCMLedgerEntryType.PURCHASE if tx.transaction_type == CCMTransactionType.PURCHASE else CCMLedgerEntryType.CASH_ADVANCE,
            amount=tx.amount,
            description=f"Settlement: {tx.merchant_name}",
            reference_id=tx.id,
            balance_before=account.outstanding_balance - tx.amount,
            balance_after=account.outstanding_balance
        )
        db.add(ledger_entry)

        # 3. Finalize Transaction
        tx.status = CCMTransactionStatus.COMPLETED
        tx.settlement_date = datetime.now()
        
        # 4. Reward Accrual (Basic logic)
        reward_points = Decimal(tx.amount * Decimal("0.01")) # 1% cashback
        reward = RewardEntry(
            credit_account_id=account.id,
            transaction_id=tx.id,
            points_earned=reward_points,
            description=f"Rewards for {tx.merchant_name}"
        )
        db.add(reward)

        db.commit()
        return tx

    @staticmethod
    def refund_transaction(db: Session, original_transaction_id: uuid.UUID) -> CCMCardTransaction:
        """
        Refund / Reversal logic.
        Restores limit and creates reversal ledger entry.
        """
        orig_tx = db.query(CCMCardTransaction).filter(CCMCardTransaction.id == original_transaction_id).with_for_update().first()
        if not orig_tx or orig_tx.status != CCMTransactionStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Original completed transaction not found")

        account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == orig_tx.credit_account_id).with_for_update().first()

        # 1. Create Refund Transaction
        refund_tx = CCMCardTransaction(
            card_id=orig_tx.card_id,
            credit_account_id=account.id,
            amount=orig_tx.amount,
            merchant_name=f"REFUND: {orig_tx.merchant_name}",
            transaction_type=CCMTransactionType.REFUND,
            status=CCMTransactionStatus.COMPLETED,
            settlement_date=datetime.now()
        )
        db.add(refund_tx)

        # 2. Update balances
        account.available_credit += orig_tx.amount
        account.outstanding_balance -= orig_tx.amount

        # 3. Ledger Entry (Credit)
        ledger_entry = CCMCreditAccountLedger(
            credit_account_id=account.id,
            entry_type=CCMLedgerEntryType.REFUND,
            amount=orig_tx.amount,
            description=f"Refund: {orig_tx.merchant_name}",
            reference_id=refund_tx.id,
            balance_before=account.outstanding_balance + orig_tx.amount,
            balance_after=account.outstanding_balance
        )
        db.add(ledger_entry)

        # 4. Rollback Rewards
        reward = db.query(RewardEntry).filter(RewardEntry.transaction_id == orig_tx.id).first()
        if reward:
            reward.points_reversed = reward.points_earned
            reward.description += " (REVERSED)"

        db.commit()
        return refund_tx
