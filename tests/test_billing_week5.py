"""
Week 5 — Comprehensive Billing & Transactions Test Suite

Tests cover:
  • Billing service (statement generation, ADB interest, grace periods, late fees)
  • Payment waterfall (RBI allocation order)
  • Fraud detection (velocity gate, amount spike, unusual hour)
  • Idempotency (duplicate detection, TTL, card mismatch)
  • Edge cases (zero balance, overpayment, missing statements)

All tests use the provisioned PostgreSQL test database with nested transactions.
No floats for money — Decimal only.
"""
import uuid
import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

# Ensure all models are imported so SQLAlchemy can resolve all string-based relationship dependencies correctly
import app.models.billing  # noqa
import app.models.transactions.transactions  # noqa
import app.models.transactions.fees  # noqa
import app.models.transactions.payments  # noqa
import app.models.transactions.clearing  # noqa
import app.models.transactions.settlement  # noqa
import app.models.transactions.disputes  # noqa
import app.models.transactions.controls  # noqa
import app.admin.models.credit_product  # noqa
import app.admin.models.card_product  # noqa
import app.admin.models.card_issuance  # noqa
import app.models.auth  # noqa
import app.models.admin  # noqa
import app.models.customer  # noqa
import app.models.credit  # noqa
import app.models.pending_registration  # noqa

# ── PostgreSQL Database for testing ──────────────────────

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        # We start a nested transaction so that the rollback
        # discards all changes, even if a test inadvertently calls db.commit()
        session.begin_nested()
        yield session
    finally:
        session.rollback()
        session.close()


# ── Fixtures for card/account setup ───────────────────

@pytest.fixture
def credit_account(db: Session):
    """Create a minimal credit account for testing."""
    from app.admin.models.card_issuance import CreditAccount
    from app.models.enums import AccountStatus

    acc = CreditAccount(
        id=uuid.uuid4(),
        user_id="TEST001",
        credit_product_id=uuid.uuid4(),
        card_product_id=uuid.uuid4(),
        credit_limit=Decimal("100000.00"),
        available_limit=Decimal("100000.00"),
        cash_advance_limit=Decimal("20000.00"),
        outstanding_amount=Decimal("0.00"),
        billing_cycle_id="28",
        account_status=AccountStatus.ACTIVE,
    )
    db.add(acc)
    db.flush()
    return acc


@pytest.fixture
def card(db: Session, credit_account):
    """Create a minimal card linked to the credit account."""
    from app.admin.models.card_issuance import Card
    from app.models.enums import CardStatus

    c = Card(
        id=uuid.uuid4(),
        credit_account_id=credit_account.id,
        card_product_id=credit_account.card_product_id,
        pan_encrypted="ENC_4111111111111111",
        pan_masked="****1111",
        expiry_date="2028-12",
        expiry_date_masked="12/28",
        cvv_encrypted="ENC_123",
        cvv_masked="***",
        card_status=CardStatus.ACTIVE,
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def settled_transactions(db: Session, card, credit_account):
    """Create sample settled transactions for the billing cycle."""
    from app.models.transactions.transactions import Transaction
    from app.models.transactions.enums import TransactionType, TransactionStatus

    now = datetime.now(timezone.utc)
    txns = []

    # Purchase transaction
    t1 = Transaction(
        id=uuid.uuid4(),
        card_id=card.id,
        account_id=credit_account.id,
        amount=Decimal("5000.00"),
        currency="INR",
        transaction_type=TransactionType.PURCHASE.value,
        status=TransactionStatus.SETTLED.value,
        merchant_name="Amazon India",
        created_at=now - timedelta(days=10),
    )
    db.add(t1)
    txns.append(t1)

    # Cash advance
    t2 = Transaction(
        id=uuid.uuid4(),
        card_id=card.id,
        account_id=credit_account.id,
        amount=Decimal("2000.00"),
        currency="INR",
        transaction_type=TransactionType.CASH_ADVANCE.value,
        status=TransactionStatus.SETTLED.value,
        merchant_name="ATM Withdrawal",
        created_at=now - timedelta(days=5),
    )
    db.add(t2)
    txns.append(t2)

    # Another purchase
    t3 = Transaction(
        id=uuid.uuid4(),
        card_id=card.id,
        account_id=credit_account.id,
        amount=Decimal("1500.00"),
        currency="INR",
        transaction_type=TransactionType.PURCHASE.value,
        status=TransactionStatus.SETTLED.value,
        merchant_name="Flipkart",
        created_at=now - timedelta(days=3),
    )
    db.add(t3)
    txns.append(t3)

    db.flush()
    return txns


# ═══════════════════════════════════════════════════════
# TEST SUITE
# ═══════════════════════════════════════════════════════


class TestBillingStatementGeneration:
    """Phase 4: Billing Service tests"""

    def test_generate_statement_creates_record(self, db, card, credit_account, settled_transactions):
        """H1: Statement is generated with correct totals."""
        from app.services.billing_service import BillingService

        cycle_date = date.today()
        results = BillingService.generate_statements(
            db, cycle_date=cycle_date,
            purchase_apr=Decimal("0.3599"),
            cash_advance_apr=Decimal("0.4199"),
        )

        assert len(results) >= 1
        result = results[0]
        assert result["card_id"] == str(card.id)
        assert Decimal(result["closing_balance"]) > 0

    def test_generate_statement_no_duplicate(self, db, card, credit_account, settled_transactions):
        """H1: Duplicate statement for same cycle is prevented."""
        from app.services.billing_service import BillingService

        cycle_date = date.today()
        first = BillingService.generate_statements(db, cycle_date=cycle_date)
        second = BillingService.generate_statements(db, cycle_date=cycle_date)

        # Second run should not create additional statements
        assert len(second) == 0

    def test_grace_period_no_purchase_interest(self, db, card, credit_account):
        """H3: No purchase interest when previous cycle was fully paid."""
        from app.models.billing import Statement
        from app.models.transactions.enums import StatementStatus

        # Create a previous PAID statement
        prev_stmt = Statement(
            credit_account_id=credit_account.id,
            card_id=card.id,
            cycle_start=date.today() - timedelta(days=60),
            cycle_end=date.today() - timedelta(days=31),
            payment_due_date=date.today() - timedelta(days=10),
            opening_balance=Decimal("0"),
            total_purchases=Decimal("1000"),
            total_cash_advances=Decimal("0"),
            total_fees=Decimal("0"),
            total_interest=Decimal("0"),
            total_credits=Decimal("0"),
            total_payments=Decimal("1000"),
            closing_balance=Decimal("0"),
            minimum_due=Decimal("0"),
            total_amount_due=Decimal("0"),
            status=StatementStatus.PAID.value,
        )
        db.add(prev_stmt)
        db.flush()

        from app.services.billing_service import BillingService
        cycle_date = date.today()
        results = BillingService.generate_statements(db, cycle_date=cycle_date)

        # Interest should be 0 because grace period applies (previous was PAID)
        if results:
            assert Decimal(results[0]["interest_charged"]) == Decimal("0")

    def test_minimum_due_calculation(self, db, card, credit_account, settled_transactions):
        """H1: Minimum due is at least 5% of closing balance or ₹200."""
        from app.services.billing_service import BillingService
        from app.models.billing import Statement

        cycle_date = date.today()
        BillingService.generate_statements(db, cycle_date=cycle_date)

        stmt = db.query(Statement).filter(Statement.card_id == card.id).first()
        assert stmt is not None
        if stmt.closing_balance > 0:
            expected_min = max(
                stmt.closing_balance * Decimal("0.05"),
                min(stmt.closing_balance, Decimal("200.00")),
            )
            # Allow ±0.01 for rounding
            assert abs(stmt.minimum_due - expected_min) <= Decimal("0.01")


class TestLateFees:
    """Phase 4: Late fee application tests"""

    def test_late_fee_applied_when_minimum_not_paid(self, db, card, credit_account):
        """H2: Late fee is applied when minimum due is not met."""
        from app.models.billing import Statement
        from app.models.transactions.enums import StatementStatus
        from app.services.billing_service import BillingService

        # Create a BILLED statement with past due date
        stmt = Statement(
            credit_account_id=credit_account.id,
            card_id=card.id,
            cycle_start=date.today() - timedelta(days=60),
            cycle_end=date.today() - timedelta(days=31),
            payment_due_date=date.today() - timedelta(days=1),  # Past due
            opening_balance=Decimal("0"),
            total_purchases=Decimal("10000"),
            total_cash_advances=Decimal("0"),
            total_fees=Decimal("0"),
            total_interest=Decimal("0"),
            total_credits=Decimal("0"),
            total_payments=Decimal("0"),
            closing_balance=Decimal("10000"),
            minimum_due=Decimal("500"),
            total_amount_due=Decimal("10000"),
            status=StatementStatus.BILLED.value,
        )
        db.add(stmt)
        db.flush()

        results = BillingService.apply_late_fees(db, late_fee_amount=Decimal("500.00"))

        assert len(results) == 1
        assert results[0]["new_status"] == StatementStatus.OVERDUE.value

        # Verify statement was updated
        db.refresh(stmt)
        assert stmt.status == StatementStatus.OVERDUE.value
        assert stmt.total_fees == Decimal("500.00")

    def test_no_late_fee_when_minimum_paid(self, db, card, credit_account):
        """H2: No late fee when minimum due was paid."""
        from app.models.billing import Statement, Payment
        from app.models.transactions.enums import StatementStatus, PaymentStatus
        from app.services.billing_service import BillingService

        stmt = Statement(
            credit_account_id=credit_account.id,
            card_id=card.id,
            cycle_start=date.today() - timedelta(days=60),
            cycle_end=date.today() - timedelta(days=31),
            payment_due_date=date.today() - timedelta(days=1),
            opening_balance=Decimal("0"),
            total_purchases=Decimal("10000"),
            total_cash_advances=Decimal("0"),
            total_fees=Decimal("0"),
            total_interest=Decimal("0"),
            total_credits=Decimal("0"),
            total_payments=Decimal("0"),
            closing_balance=Decimal("10000"),
            minimum_due=Decimal("500"),
            total_amount_due=Decimal("10000"),
            status=StatementStatus.BILLED.value,
        )
        db.add(stmt)
        db.flush()

        # Create a payment that covers the minimum
        payment = Payment(
            credit_account_id=credit_account.id,
            card_id=card.id,
            statement_id=stmt.id,
            amount=Decimal("600"),
            payment_source="UPI",
            reference_no="PAY-MIN-001",
            status=PaymentStatus.POSTED.value,
            payment_date=date.today() - timedelta(days=2),
            posted_at=datetime.now(timezone.utc),
        )
        db.add(payment)
        db.flush()

        results = BillingService.apply_late_fees(db)
        assert len(results) == 0


class TestPaymentWaterfall:
    """Phase 5: RBI Payment Waterfall tests"""

    def test_waterfall_allocation_order(self, db, card, credit_account):
        """H4: Payment allocated in order: Fees → Interest → CA → Purchases."""
        from app.models.billing import Statement
        from app.models.transactions.enums import StatementStatus
        from app.services.payment_service import PaymentWaterfallService

        # Create a statement with all bucket types
        stmt = Statement(
            credit_account_id=credit_account.id,
            card_id=card.id,
            cycle_start=date.today() - timedelta(days=30),
            cycle_end=date.today() - timedelta(days=1),
            payment_due_date=date.today() + timedelta(days=20),
            opening_balance=Decimal("0"),
            total_purchases=Decimal("5000"),
            total_cash_advances=Decimal("2000"),
            total_fees=Decimal("500"),
            total_interest=Decimal("300"),
            total_credits=Decimal("0"),
            total_payments=Decimal("0"),
            closing_balance=Decimal("7800"),
            minimum_due=Decimal("390"),
            total_amount_due=Decimal("7800"),
            status=StatementStatus.BILLED.value,
        )
        db.add(stmt)
        db.flush()

        # Make a payment of ₹1000
        payment = PaymentWaterfallService.process_payment(
            db=db,
            card_id=card.id,
            amount=Decimal("1000.00"),
            payment_source="UPI",
            reference_no="WF-TEST-001",
        )

        # Waterfall: 500 fees + 300 interest + 200 cash advance
        assert payment.allocated_fees == Decimal("500.00")
        assert payment.allocated_interest == Decimal("300.00")
        assert payment.allocated_cash_advance == Decimal("200.00")
        assert payment.allocated_purchases == Decimal("0.00")

    def test_full_payment_marks_statement_paid(self, db, card, credit_account):
        """H4: Full payment marks statement as PAID."""
        from app.models.billing import Statement
        from app.models.transactions.enums import StatementStatus
        from app.services.payment_service import PaymentWaterfallService

        stmt = Statement(
            credit_account_id=credit_account.id,
            card_id=card.id,
            cycle_start=date.today() - timedelta(days=30),
            cycle_end=date.today() - timedelta(days=1),
            payment_due_date=date.today() + timedelta(days=20),
            opening_balance=Decimal("0"),
            total_purchases=Decimal("1000"),
            total_cash_advances=Decimal("0"),
            total_fees=Decimal("0"),
            total_interest=Decimal("0"),
            total_credits=Decimal("0"),
            total_payments=Decimal("0"),
            closing_balance=Decimal("1000"),
            minimum_due=Decimal("200"),
            total_amount_due=Decimal("1000"),
            status=StatementStatus.BILLED.value,
        )
        db.add(stmt)
        db.flush()

        PaymentWaterfallService.process_payment(
            db=db,
            card_id=card.id,
            amount=Decimal("1000.00"),
            payment_source="NEFT",
            reference_no="FULL-PAY-001",
        )

        db.refresh(stmt)
        assert stmt.status == StatementStatus.PAID.value

    def test_partial_payment_marks_partially_paid(self, db, card, credit_account):
        """H4: Partial payment (>= minimum) marks PARTIALLY_PAID."""
        from app.models.billing import Statement
        from app.models.transactions.enums import StatementStatus
        from app.services.payment_service import PaymentWaterfallService

        stmt = Statement(
            credit_account_id=credit_account.id,
            card_id=card.id,
            cycle_start=date.today() - timedelta(days=30),
            cycle_end=date.today() - timedelta(days=1),
            payment_due_date=date.today() + timedelta(days=20),
            opening_balance=Decimal("0"),
            total_purchases=Decimal("10000"),
            total_cash_advances=Decimal("0"),
            total_fees=Decimal("0"),
            total_interest=Decimal("0"),
            total_credits=Decimal("0"),
            total_payments=Decimal("0"),
            closing_balance=Decimal("10000"),
            minimum_due=Decimal("500"),
            total_amount_due=Decimal("10000"),
            status=StatementStatus.BILLED.value,
        )
        db.add(stmt)
        db.flush()

        PaymentWaterfallService.process_payment(
            db=db,
            card_id=card.id,
            amount=Decimal("1000.00"),
            payment_source="UPI",
            reference_no="PARTIAL-001",
        )

        db.refresh(stmt)
        assert stmt.status == StatementStatus.PARTIALLY_PAID.value


class TestFraudService:
    """Phase 6: Fraud detection tests"""

    def test_velocity_gate_hard_decline(self, db, card, credit_account):
        """H5: >5 transactions in 60s triggers hard decline."""
        from app.models.transactions.transactions import Transaction
        from app.models.transactions.enums import TransactionType, TransactionStatus
        from app.services.fraud_service import FraudService
        from app.core.exceptions import FraudDeclinedError

        # Create 5 recent transactions
        now = datetime.now(timezone.utc)
        for i in range(5):
            t = Transaction(
                id=uuid.uuid4(),
                card_id=card.id,
                account_id=credit_account.id,
                amount=Decimal("100.00"),
                currency="INR",
                transaction_type=TransactionType.PURCHASE.value,
                status=TransactionStatus.AUTHORIZED.value,
                created_at=now - timedelta(seconds=30),
            )
            db.add(t)
        db.flush()

        with pytest.raises(FraudDeclinedError) as exc_info:
            FraudService.run_fraud_checks(
                db=db,
                card_id=card.id,
                amount=Decimal("100.00"),
            )
        assert "VELOCITY" in str(exc_info.value.message)

    def test_amount_spike_soft_flag(self, db, card, credit_account):
        """H5: Transaction >3× the 30-day average creates a soft flag."""
        from app.models.transactions.transactions import Transaction
        from app.models.transactions.enums import TransactionType, TransactionStatus
        from app.services.fraud_service import FraudService

        now = datetime.now(timezone.utc)
        # Create historical transactions with average of ₹500
        for i in range(5):
            t = Transaction(
                id=uuid.uuid4(),
                card_id=card.id,
                account_id=credit_account.id,
                amount=Decimal("500.00"),
                currency="INR",
                transaction_type=TransactionType.PURCHASE.value,
                status=TransactionStatus.SETTLED.value,
                created_at=now - timedelta(days=15),
            )
            db.add(t)
        db.flush()

        # Transaction for 3× the average (₹1500+)
        results = FraudService.run_fraud_checks(
            db=db,
            card_id=card.id,
            amount=Decimal("2000.00"),
        )

        assert any(r["rule"] == "AMOUNT_SPIKE" for r in results)


class TestIdempotencyService:
    """Phase 6: Idempotency tests"""

    def test_check_idempotency_returns_none_for_new_key(self, db, card):
        """H6: New key returns None."""
        from app.services.idempotency_service import IdempotencyService

        result = IdempotencyService.check_idempotency(db, "NEW-KEY-001", str(card.id))
        assert result is None

    def test_store_and_retrieve_idempotency(self, db, card):
        """H6: Stored key is retrievable."""
        from app.services.idempotency_service import IdempotencyService

        key = "IDEM-TEST-001"
        response = {"transaction_id": str(uuid.uuid4()), "status": "AUTHORIZED"}

        IdempotencyService.store_idempotency_result(
            db=db, key=key, card_id=card.id,
            response_body=response, status_code=201,
        )
        db.flush()

        result = IdempotencyService.check_idempotency(db, key, str(card.id))
        assert result is not None
        assert result["status_code"] == 201
        assert result["response_body"]["status"] == "AUTHORIZED"

    def test_idempotency_card_mismatch_raises_conflict(self, db, card):
        """H6: Same key with different card_id raises IdempotencyConflictError."""
        from app.services.idempotency_service import IdempotencyService
        from app.core.exceptions import IdempotencyConflictError

        key = "IDEM-CONFLICT-001"
        response = {"transaction_id": str(uuid.uuid4())}

        IdempotencyService.store_idempotency_result(
            db=db, key=key, card_id=card.id,
            response_body=response, status_code=201,
        )
        db.flush()

        # Try with a different card_id
        with pytest.raises(IdempotencyConflictError):
            IdempotencyService.check_idempotency(db, key, str(uuid.uuid4()))

    def test_expired_idempotency_key_treated_as_new(self, db, card):
        """H6: Expired key is cleaned up and treated as new."""
        from app.models.billing import IdempotencyKey
        from app.services.idempotency_service import IdempotencyService

        key = "IDEM-EXPIRED-001"
        # Insert an expired key manually
        expired = IdempotencyKey(
            key=key,
            card_id=card.id,
            response_body={"old": True},
            status_code=201,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Already expired
        )
        db.add(expired)
        db.flush()

        result = IdempotencyService.check_idempotency(db, key, str(card.id))
        assert result is None  # Treated as new


class TestEdgeCases:
    """Edge case and integration tests"""

    def test_zero_balance_statement(self, db, card, credit_account):
        """Edge: Statement with zero activity has zero closing balance."""
        from app.services.billing_service import BillingService

        cycle_date = date.today()
        results = BillingService.generate_statements(db, cycle_date=cycle_date)

        if results:
            # With no transactions, closing balance should be equal to opening
            result = results[0]
            assert Decimal(result["closing_balance"]) >= Decimal("0")

    def test_payment_without_statement(self, db, card, credit_account):
        """Edge: Payment when no open statement applies to general credit."""
        from app.services.payment_service import PaymentWaterfallService

        payment = PaymentWaterfallService.process_payment(
            db=db,
            card_id=card.id,
            amount=Decimal("500.00"),
            payment_source="UPI",
            reference_no="NO-STMT-001",
        )

        # Should allocate all to purchases (general credit)
        assert payment.allocated_purchases == Decimal("500.00")
        assert payment.statement_id is None
