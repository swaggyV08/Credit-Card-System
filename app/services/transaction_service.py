import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.card_management import CCMCreditCard, CCMCreditAccount, CCMCardTransaction
from app.models.enums import CCMCardStatus, CCMTransactionType, CCMTransactionStatus, CCMFraudBlockReason
from app.schemas.card_management import CCMChargeRequest, CCMTransactionReverseRequest
from app.services.card_management_service import CardManagementService

class TransactionService:

    @staticmethod
    def process_transaction(db: Session, request: CCMChargeRequest) -> CCMCardTransaction:
        card = db.query(CCMCreditCard).filter(CCMCreditCard.id == request.card_id).first()
        if not card:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
            
        if card.status != CCMCardStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction declined: Card is not ACTIVE")

        credit_account = db.query(CCMCreditAccount).filter(CCMCreditAccount.card_id == card.id).first()
        if not credit_account:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Credit Account missing")

        if credit_account.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction declined: Account is CLOSED")

        # 1. Evaluate specific transaction flags
        # Default behavior: assume it's a domestic/point of sale unless specified.
        # This is a sample check for a hypothetical "international" check
        # A more complex system would check `merchant_category` and currency
        if request.currency != "INR" and not card.is_international_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="International transactions disabled for this card")

        # 2. Check limits
        if request.transaction_type in [CCMTransactionType.PURCHASE, CCMTransactionType.CASH_ADVANCE]:
            if credit_account.available_credit < request.amount:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction declined: Insufficient limit")
            if request.transaction_type == CCMTransactionType.CASH_ADVANCE:
                if request.amount > credit_account.cash_limit:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction declined: Exceeds cash limit")

        # 3. Fraud Monitoring (Geo-Mismatch Mock)
        # Check last transaction location vs current location loosely
        last_tx = db.query(CCMCardTransaction).filter(
            CCMCardTransaction.card_id == card.id,
            CCMCardTransaction.status == CCMTransactionStatus.COMPLETED
        ).order_by(CCMCardTransaction.created_at.desc()).first()
        
        is_fraud = False
        if last_tx and last_tx.geo_location and request.geo_location:
            # Simplistic geo-mismatch rule:
            # If the last_tx geo string is radically different from current, trigger block
            # For testing purposes, we define a simple keyword difference.
            if last_tx.geo_location.split(',')[0] != request.geo_location.split(',')[0]:
                is_fraud = True

        # Process the ledger if not fraud
        if is_fraud:
            # Lock the card
            CardManagementService.block_card(db, card.id, CCMFraudBlockReason.GEO_MISMATCH)
            
            tx = CCMCardTransaction(
                card_id=card.id,
                credit_account_id=credit_account.id,
                amount=request.amount,
                merchant_name=request.merchant_name,
                merchant_category=request.merchant_category,
                currency=request.currency,
                transaction_type=request.transaction_type,
                status=CCMTransactionStatus.FAILED,
                geo_location=request.geo_location,
                is_fraud_flagged=True
            )
            db.add(tx)
            db.commit()
            db.refresh(tx)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Transaction blocked due to suspected fraud. Card locked.")

        # Ledger Update for valid charge
        if request.transaction_type == CCMTransactionType.PURCHASE or request.transaction_type == CCMTransactionType.CASH_ADVANCE:
            credit_account.available_credit -= request.amount
            credit_account.outstanding_balance += request.amount

            # If it were a credit-type transaction (e.g., REFUND from merchant)
        elif request.transaction_type == CCMTransactionType.REFUND:
            credit_account.available_credit += request.amount
            credit_account.outstanding_balance -= request.amount
            
            # Ensure outstanding_balance != negative in simple logic, or keep as negative = overpay
            # If negative, cap available_credit at limit? Depending on rules.
            # Assuming basic math applies.
            
        tx = CCMCardTransaction(
            card_id=card.id,
            credit_account_id=credit_account.id,
            amount=request.amount,
            merchant_name=request.merchant_name,
            merchant_category=request.merchant_category,
            currency=request.currency,
            transaction_type=request.transaction_type,
            status=CCMTransactionStatus.COMPLETED,
            geo_location=request.geo_location,
            is_fraud_flagged=False
        )
        
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx


    @staticmethod
    def reverse_transaction(db: Session, request: CCMTransactionReverseRequest) -> CCMCardTransaction:
        orig_tx = db.query(CCMCardTransaction).filter(CCMCardTransaction.id == request.transaction_id).first()
        if not orig_tx:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original transaction not found")
            
        if orig_tx.status != CCMTransactionStatus.COMPLETED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only completed transactions can be reversed")

        credit_account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == orig_tx.credit_account_id).first()
        if not credit_account:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Credit account not found")

        # Reverse the ledger impact
        if orig_tx.transaction_type in [CCMTransactionType.PURCHASE, CCMTransactionType.CASH_ADVANCE]:
            # Add back credit
            credit_account.available_credit += orig_tx.amount
            credit_account.outstanding_balance -= orig_tx.amount
        elif orig_tx.transaction_type == CCMTransactionType.REFUND:
            # Reversing a refund removes available credit
            credit_account.available_credit -= orig_tx.amount
            credit_account.outstanding_balance += orig_tx.amount

        # Update original trans status? Or log a new REVERSAL row? requirement says:
        # "Reversal updates credit account ... system must allow reverse_transaction()"
        # Logging new is safer.
        orig_tx.status = CCMTransactionStatus.REVERSED
        
        rev_tx = CCMCardTransaction(
            card_id=orig_tx.card_id,
            credit_account_id=credit_account.id,
            amount=orig_tx.amount,
            merchant_name=orig_tx.merchant_name,
            merchant_category=orig_tx.merchant_category,
            currency=orig_tx.currency,
            transaction_type=CCMTransactionType.REVERSAL,
            status=CCMTransactionStatus.COMPLETED,
            geo_location=orig_tx.geo_location,
            is_fraud_flagged=False
        )

        db.add(rev_tx)
        db.commit()
        db.refresh(rev_tx)
        return rev_tx
