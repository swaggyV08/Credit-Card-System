from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from app.models.card_management import (
    CCMCreditAccount, CCMCreditAccountAdjustment, CCMCreditAccountLedger, CCMCreditCard
)
from app.models.enums import (
    CCMAccountStatus, CCMAccountRiskFlag, CCMAdjustmentType,
    CCMLedgerEntryType, CCMLimitReasonCode, CCMStatusReasonCode,
    CCMAdjustmentReasonCode
)
from app.admin.schemas.credit_account_admin import (
    CreditAccountDetail, CreditAccountSummary, CreditLimitUpdateRequest, AccountStatusUpdateRequest,
    AccountFreezeRequest, BillingCycleUpdateRequest,
    RiskFlagUpdateRequest, InterestUpdateRequest,
    OverlimitConfigRequest, ManualAdjustmentRequest
)
from app.core.exceptions import BankGradeException

class CreditAccountAdminService:
    @staticmethod
    def get_account(db: Session, account_id: UUID) -> CCMCreditAccount:
        account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == account_id).first()
        if not account:
            raise BankGradeException(
                status_code=404,
                code="ZBANQ-40.4-002",
                message="Credit account not found",
                details={"account_id": str(account_id)}
            )
        # Populate extra fields for response schema
        response_dict = CreditAccountDetail.model_validate(account).model_dump()
        response_dict["card_count"] = account.card_count
        response_dict["cards"] = account.cards
        return response_dict

    @staticmethod

    def list_accounts(
        db: Session,
        page: int = 1,
        limit: int = 20,
        status: Optional[CCMAccountStatus] = None,
        product_code: Optional[str] = None
    ) -> Tuple[List[CCMCreditAccount], int]:
        query = db.query(CCMCreditAccount)
        
        if status:
            query = query.filter(CCMCreditAccount.status == status)
        if product_code:
            query = query.filter(CCMCreditAccount.product_code == product_code)
            
        total = query.count()
        accounts = query.order_by(desc(CCMCreditAccount.created_at)).offset((page - 1) * limit).limit(limit).all()
        
        # Convert to dicts and inject card_count
        account_summaries = []
        for acc in accounts:
            summary_dict = CreditAccountSummary.model_validate(acc).model_dump()
            summary_dict["card_count"] = acc.card_count
            account_summaries.append(summary_dict)
            
        return account_summaries, total

    @staticmethod
    def _create_ledger_entry(
        db: Session,
        account: CCMCreditAccount,
        entry_type: CCMLedgerEntryType,
        amount: Decimal,
        description: str,
        balance_before: Decimal,
        balance_after: Decimal,
        reference_id: Optional[UUID] = None
    ) -> CCMCreditAccountLedger:
        ledger_entry = CCMCreditAccountLedger(
            credit_account_id=account.id,
            entry_type=entry_type,
            amount=amount,
            description=description,
            reference_id=reference_id,
            balance_before=balance_before,
            balance_after=balance_after
        )
        db.add(ledger_entry)
        return ledger_entry

    @staticmethod
    def update_limit(db: Session, account_id: UUID, req: CreditLimitUpdateRequest, admin_id: UUID):
        account = CreditAccountAdminService.get_account(db, account_id)
        old_limit = account.credit_limit
        new_limit = req.new_credit_limit
        
        limit_diff = new_limit - old_limit
        
        # Auto-generate effective_from using nested structure
        try:
            effective_from = datetime(req.effective_from.Year, req.effective_from.Month, req.effective_from.Date)
        except ValueError as e:
            raise BankGradeException(
                status_code=400,
                code="ZBANQ-40.0-003",
                message=f"Invalid date for effective_from: {str(e)}",
                details={"Year": req.effective_from.Year, "Month": req.effective_from.Month, "Date": req.effective_from.Date}
            )

        account.credit_limit = new_limit
        account.available_credit += limit_diff
        
        CreditAccountAdminService._create_ledger_entry(
            db=db,
            account=account,
            entry_type=CCMLedgerEntryType.LIMIT_CHANGE,
            amount=limit_diff,
            description=f"Limit updated from {old_limit} to {new_limit}. Reason: {req.reason_code.value}. Effective From: {effective_from.date()}. Notes: {req.notes or ''}",
            balance_before=account.outstanding_balance,
            balance_after=account.outstanding_balance
        )
        
        db.commit()
        db.refresh(account)
        return account, old_limit

    @staticmethod
    def update_status(db: Session, account_id: UUID, req: AccountStatusUpdateRequest):
        account = CreditAccountAdminService.get_account(db, account_id)
        old_status = account.status
        new_status = req.status
        
        valid_transitions = {
            CCMAccountStatus.PENDING: [CCMAccountStatus.ACTIVE, CCMAccountStatus.CLOSED],
            CCMAccountStatus.ACTIVE: [CCMAccountStatus.SUSPENDED, CCMAccountStatus.FROZEN, CCMAccountStatus.DELINQUENT, CCMAccountStatus.CLOSED],
            CCMAccountStatus.SUSPENDED: [CCMAccountStatus.ACTIVE, CCMAccountStatus.FROZEN, CCMAccountStatus.CLOSED],
            CCMAccountStatus.FROZEN: [CCMAccountStatus.ACTIVE, CCMAccountStatus.SUSPENDED, CCMAccountStatus.CLOSED],
            CCMAccountStatus.DELINQUENT: [CCMAccountStatus.ACTIVE, CCMAccountStatus.SUSPENDED, CCMAccountStatus.CHARGED_OFF, CCMAccountStatus.CLOSED],
            CCMAccountStatus.CHARGED_OFF: [CCMAccountStatus.CLOSED],
            CCMAccountStatus.CLOSED: []
        }
        
        if new_status not in valid_transitions.get(old_status, []):
            raise BankGradeException(
                status_code=400,
                code="ZBANQ-40.0-002",
                message="Invalid account status transition",
                details={
                    "current_status": old_status.value,
                    "target_status": new_status.value
                }
            )
            
        account.status = new_status
        CreditAccountAdminService._create_ledger_entry(
            db=db,
            account=account,
            entry_type=CCMLedgerEntryType.ADJUSTMENT,
            amount=Decimal("0.0"),
            description=f"Status changed from {old_status.value} to {new_status.value}. Reason: {req.reason_code.value}. Notes: {req.notes or ''}",
            balance_before=account.outstanding_balance,
            balance_after=account.outstanding_balance
        )
        
        db.commit()
        db.refresh(account)
        return account, old_status

    @staticmethod
    def freeze(db: Session, account_id: UUID, req: AccountFreezeRequest):
        account = CreditAccountAdminService.get_account(db, account_id)
        old_status = account.status
        
        if req.freeze:
            if old_status == CCMAccountStatus.FROZEN:
                return account, "FROZEN"
            new_status = CCMAccountStatus.FROZEN
        else:
            if old_status != CCMAccountStatus.FROZEN:
                return account, old_status.value  # Return actual current status
            new_status = CCMAccountStatus.ACTIVE
            
        return CreditAccountAdminService.update_status(
            db, account_id, AccountStatusUpdateRequest(
                status=new_status,
                reason_code=req.reason_code,
                notes=req.notes
            )
        )

    @staticmethod
    def update_billing_cycle(db: Session, account_id: UUID, req: BillingCycleUpdateRequest):
        account = CreditAccountAdminService.get_account(db, account_id)
        old_billing_cycle_day = account.billing_cycle_day
        old_payment_due_days = account.payment_due_days
        
        account.billing_cycle_day = req.billing_cycle_day
        account.payment_due_days = req.grace_period
        db.commit()
        db.refresh(account)
        return account, old_billing_cycle_day, old_payment_due_days

    @staticmethod
    def update_risk_flag(db: Session, account_id: UUID, req: RiskFlagUpdateRequest):
        account = CreditAccountAdminService.get_account(db, account_id)
        old_risk_flag = account.risk_flag
        
        account.risk_flag = req.risk_flag
        db.commit()
        db.refresh(account)
        return account, old_risk_flag

    @staticmethod
    def update_interest(db: Session, account_id: UUID, req: InterestUpdateRequest):
        account = CreditAccountAdminService.get_account(db, account_id)
        old_purchase_apr = account.purchase_apr
        old_cash_apr = account.cash_apr
        old_penalty_apr = account.penalty_apr
        
        account.purchase_apr = req.purchase_apr
        account.cash_apr = req.cash_apr
        account.penalty_apr = req.penalty_apr
        db.commit()
        db.refresh(account)
        return account, old_purchase_apr, old_cash_apr, old_penalty_apr

    @staticmethod
    def update_overlimit(db: Session, account_id: UUID, req: OverlimitConfigRequest):
        account = CreditAccountAdminService.get_account(db, account_id)
        old_overlimit_enabled = account.overlimit_enabled
        old_overlimit_buffer = account.overlimit_buffer
        old_overlimit_fee = account.overlimit_fee
        
        account.overlimit_enabled = req.overlimit_enabled
        account.overlimit_buffer = req.overlimit_buffer
        account.overlimit_fee = req.overlimit_fee
        db.commit()
        db.refresh(account)
        return account, old_overlimit_enabled, old_overlimit_buffer, old_overlimit_fee
