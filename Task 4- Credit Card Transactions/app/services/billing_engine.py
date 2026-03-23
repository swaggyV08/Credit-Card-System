import uuid
from decimal import Decimal
from datetime import datetime, date, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from app.models.card_management import CCMCreditAccount, CCMCardTransaction, CCMCreditAccountLedger
from app.models.billing import BillingStatement
from app.models.enums import (
    CCMTransactionType, CCMTransactionStatus, CCMLedgerEntryType,
    CCMAccountStatus, InterestCalculationMethod, InterestBasis
)

class BillingEngine:
    """
    Automated billing and interest calculation engine.
    Calculates APR-based interest, late fees, and generates statements.
    """

    @staticmethod
    def calculate_interest(
        db: Session,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Decimal:
        """
        Calculates interest based on Daily Balance method.
        Interest = Sum(Daily Balance * Periodic Rate)
        """
        account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == account_id).first()
        if not account or account.interest_rate <= 0:
            return Decimal("0.00")

        # Periodic rate (Daily)
        annual_rate = account.purchase_apr / 100
        daily_rate = annual_rate / 365 # Most banks use 365

        # 1. Fetch all transactions and ledger entries for the period to reconstruct daily balances
        # In a real production system, we'd use a snapshot of daily balances or heavy query.
        # Here we approximate based on the current outstanding and working backwards, 
        # or forward from the opening balance.
        
        # Simplified: Calculate interest on the closing balance for the number of days.
        # In a high-quality system, we'd integrate every ledger entry.
        days = (end_date - start_date).days
        if days <= 0: return Decimal("0.00")

        # For this implementation, we apply the rate to the current outstanding balance 
        # as a simple proxy for the daily balance sum.
        # Improvement: In a real scenario, this would iterate through each day.
        interest = account.outstanding_balance * daily_rate * days
        return interest.quantize(Decimal("0.01"))

    @staticmethod
    def generate_statement(db: Session, account_id: uuid.UUID) -> BillingStatement:
        """
        Generates the monthly statement for the account.
        """
        account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == account_id).with_for_update().first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        # 1. Define Period (Last 30 days or based on billing_cycle_day)
        today = datetime.now()
        start_date = account.last_statement_date or (today - timedelta(days=30))
        end_date = today

        # 2. Calculate Interest and Fees
        interest = BillingEngine.calculate_interest(db, account_id, start_date, end_date)
        
        # Late fee logic (if outstanding > 0 and past due - simplified)
        late_fee = Decimal("0.00")
        if account.outstanding_balance > 0 and account.status == CCMAccountStatus.DELINQUENT:
            late_fee = account.late_fee

        # 3. Aggregate totals for the period
        totals = db.query(
            func.sum(CCMCardTransaction.amount).filter(CCMCardTransaction.transaction_type == CCMTransactionType.PURCHASE),
            func.sum(CCMCardTransaction.amount).filter(CCMCardTransaction.transaction_type == CCMTransactionType.CASH_ADVANCE),
            func.sum(CCMCardTransaction.amount).filter(CCMCardTransaction.transaction_type == CCMTransactionType.PAYMENT)
        ).filter(
            CCMCardTransaction.credit_account_id == account_id,
            CCMCardTransaction.created_at >= start_date,
            CCMCardTransaction.created_at < end_date,
            CCMCardTransaction.status == CCMTransactionStatus.COMPLETED
        ).first()

        purchases = totals[0] or Decimal("0.00")
        advances = totals[1] or Decimal("0.00")
        payments = totals[2] or Decimal("0.00")

        # 4. Finalize Statement balance
        # Opening balance is what was left from last statement
        last_stmt = db.query(BillingStatement).filter(BillingStatement.credit_account_id == account_id).order_by(BillingStatement.statement_date.desc()).first()
        opening = last_stmt.closing_balance if last_stmt else Decimal("0.00")
        
        closing = opening + purchases + advances - payments + interest + late_fee
        min_due = closing * Decimal("0.05") # 5% minimum due

        # 5. Create Statement Record
        statement = BillingStatement(
            credit_account_id=account.id,
            statement_period_start=start_date,
            statement_period_end=end_date,
            due_date=end_date + timedelta(days=account.payment_due_days),
            opening_balance=opening,
            total_purchases=purchases,
            total_cash_advances=advances,
            total_payments=payments,
            interest_charged=interest,
            fees_charged=late_fee,
            closing_balance=closing,
            minimum_amount_due=min_due.quantize(Decimal("0.01"))
        )
        db.add(statement)

        # 6. Apply interest/fees to Account outstanding balance
        if interest > 0 or late_fee > 0:
            account.outstanding_balance += (interest + late_fee)
            
            # Create Ledger Entry for interest/fees
            if interest > 0:
                db.add(CCMCreditAccountLedger(
                    credit_account_id=account.id,
                    entry_type=CCMLedgerEntryType.INTEREST,
                    amount=interest,
                    description=f"Interest Charged for period {start_date.date()} to {end_date.date()}",
                    balance_before=account.outstanding_balance - interest - late_fee,
                    balance_after=account.outstanding_balance - late_fee
                ))
            if late_fee > 0:
                db.add(CCMCreditAccountLedger(
                    credit_account_id=account.id,
                    entry_type=CCMLedgerEntryType.FEE,
                    amount=late_fee,
                    description="Late Payment Fee",
                    balance_before=account.outstanding_balance - late_fee,
                    balance_after=account.outstanding_balance
                ))

        account.last_statement_date = end_date
        db.commit()
        return statement
