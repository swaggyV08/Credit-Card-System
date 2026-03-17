import uuid
import random
import hashlib
from typing import List
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.models.card_management import CCMCreditCard, CCMCreditAccount, CCMCardTransaction
from app.models.customer import OTPCode, OTPPurpose
from app.models.enums import (
    CCMCardStatus, CardNetwork, CardVariant, CCMFraudBlockReason, 
    ActorType, CCMCommand, CCMReissueReason, CCMReissueType
)
from app.schemas.card_management import (
    CCMCardIssueRequest, CCMCardActivationRequest,
    CCMCardBlockRequest, CCMCardUnblockRequest,
    CCMCardReplaceRequest, CCMCardTerminateRequest,
    CCMCardRenewRequest
)
from app.core import otp as otp_util
from app.core.security import hash_value


# =====================================================
# UTILITY FUNCTIONS
# =====================================================

def generate_card_number() -> str:
    return "4" + "".join([str(random.randint(0, 9)) for _ in range(15)])

def generate_cvv() -> str:
    return str(random.randint(100, 999))

def hash_cvv(cvv: str) -> str:
    return hashlib.sha256(cvv.encode()).hexdigest()

def generate_expiry() -> str:
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=365*3)
    return expiry.strftime("%m/%y")

def hash_pin(pin: str) -> str:
    return hash_value(pin)

def _get_card_or_404(db: Session, card_id: uuid.UUID) -> CCMCreditCard:
    """Fetch a card by ID or raise 404 with a clear message."""
    card = db.query(CCMCreditCard).filter(CCMCreditCard.id == card_id).first()
    if not card:
        raise HTTPException(
            status_code=404,
            detail=f"Card not found. No card exists with ID: {card_id}"
        )
    return card


# =====================================================
# CARD MANAGEMENT SERVICE
# =====================================================

class CardManagementService:

    # -------------------------------------------------
    # 1. ISSUE CARD
    # -------------------------------------------------
    @staticmethod
    def issue_card(db: Session, credit_account_id: uuid.UUID, request: CCMCardIssueRequest) -> dict:
        account = db.query(CCMCreditAccount).filter(CCMCreditAccount.id == credit_account_id).first()
        if not account:
            raise HTTPException(
                status_code=404,
                detail=f"Credit account not found. No account exists with ID: {credit_account_id}"
            )

        # Validate request credit_account_id matches path
        if request.credit_account_id != credit_account_id:
            raise HTTPException(
                status_code=400,
                detail="credit_account_id in request body does not match the path parameter."
            )

        card_number = generate_card_number()
        cvv = generate_cvv()
        expiry_date = generate_expiry()

        new_card = CCMCreditCard(
            user_id=account.user_id,
            card_number=card_number,
            card_network=CardNetwork.VISA,
            card_variant=CardVariant.CLASSIC,
            expiry_date=expiry_date,
            cvv_hash=hash_cvv(cvv),
            status=CCMCardStatus.ISSUED,
            issued_at=datetime.now(timezone.utc),
            credit_account=account,
            is_virtual=(request.card_type == CCMReissueType.VIRTUAL)
        )
        db.add(new_card)
        db.commit()
        db.refresh(new_card)

        last_4 = card_number[-4:]
        return {
            "message": "Card issued successfully",
            "card_id": new_card.id,
            "last_4_digits": f"**** {last_4}",
            "expiry": expiry_date,
            "status": "ISSUED",
            "delivery": "In progress"
        }

    # -------------------------------------------------
    # 2. ACTIVATION — Stage 1: Generate activation_id
    # -------------------------------------------------
    @staticmethod
    def handle_activation_generate(db: Session, card_id: uuid.UUID) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status == CCMCardStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Card is already active. No activation needed."
            )

        if card.status not in [CCMCardStatus.ISSUED, CCMCardStatus.INACTIVE]:
            raise HTTPException(
                status_code=400,
                detail=f"Card cannot be activated in its current state: {card.status.value}. "
                       "Card must be in ISSUED or INACTIVE status."
            )

        # Generate a unique activation_id
        activation_id = uuid.uuid4()

        return {
            "message": "🔐 Activation initiated. Use this activation_id as linkage_id in the generic OTP endpoints.",
            "detail": (
                "Step 1: Call POST /auth/otp/generate with purpose=ACTIVATION and linkage_id=<activation_id>.\n"
                "Step 2: Call POST /auth/otp/verify with purpose=ACTIVATION, linkage_id=<activation_id>, and otp=<code>.\n"
                "Step 3: Call POST /cards/{card_id}/activate?command=activate with pin and activation_id."
            ),
            "activation_id": str(activation_id),
            "card_id": str(card_id)
        }

    # -------------------------------------------------
    # 2. ACTIVATION — Stage 3: Set PIN and activate
    # -------------------------------------------------
    @staticmethod
    def handle_activation_final(db: Session, card_id: uuid.UUID, request: CCMCardActivationRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status == CCMCardStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Card is already active."
            )

        if card.status not in [CCMCardStatus.ISSUED, CCMCardStatus.INACTIVE]:
            raise HTTPException(
                status_code=400,
                detail=f"Card cannot be activated in its current state: {card.status.value}."
            )

        # Verify that OTP was verified for this activation_id (linkage_id)
        otp_record = db.query(OTPCode).filter(
            OTPCode.linkage_id == request.activation_id,
            OTPCode.purpose == OTPPurpose.ACTIVATION,
            OTPCode.is_used == False
        ).order_by(OTPCode.created_at.desc()).first()

        if not otp_record:
            raise HTTPException(
                status_code=400,
                detail="No OTP verification found for this activation_id. "
                       "Please complete OTP verification first via POST /auth/otp/generate and POST /auth/otp/verify."
            )

        if not getattr(otp_record, 'is_verified', False):
            raise HTTPException(
                status_code=400,
                detail="OTP has not been verified yet. "
                       "Please verify the OTP first via POST /auth/otp/verify with this activation_id as linkage_id."
            )

        # Activate card and set PIN
        card.status = CCMCardStatus.ACTIVE
        card.activated_at = datetime.now(timezone.utc)
        card.pin_hash = hash_pin(request.pin)
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.ACTIVE
            
        otp_record.is_used = True
        db.commit()

        return {
            "message": "🎉 Card Activated & PIN Set Successfully",
            "detail": "Your card is now ready for use."
        }

    # -------------------------------------------------
    # 3. BLOCK CARD
    # -------------------------------------------------
    @staticmethod
    def block_card(db: Session, card_id: uuid.UUID, request: CCMCardBlockRequest, actor: ActorType = ActorType.USER) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status in [CCMCardStatus.TERMINATED, CCMCardStatus.REPLACED, CCMCardStatus.EXPIRED]:
            raise HTTPException(
                status_code=400,
                detail=f"Card cannot be blocked. Current status: {card.status.value}. "
                       "Only ACTIVE or INACTIVE cards can be blocked."
            )

        if card.status in [CCMCardStatus.BLOCKED_USER, CCMCardStatus.BLOCKED_FRAUD, CCMCardStatus.BLOCKED_TEMP]:
            raise HTTPException(
                status_code=400,
                detail=f"Card is already blocked. Current status: {card.status.value}."
            )

        card.status = CCMCardStatus.BLOCKED_USER if actor == ActorType.USER else CCMCardStatus.BLOCKED_FRAUD
        card.blocked_reason = request.reason
        card.blocked_by_actor = actor
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.FROZEN
            
        db.commit()

        return {
            "message": "⚠ Card Blocked",
            "details": [
                "Transactions are now disabled.",
                "You can unblock anytime using the unblock command.",
                "Use generic OTP API for unblocking."
            ]
        }

    # -------------------------------------------------
    # 4. UNBLOCK — Initiate (unblock_otp)
    # -------------------------------------------------
    @staticmethod
    def initiate_unblock(db: Session, card_id: uuid.UUID, request: CCMCardUnblockRequest, actor: ActorType = ActorType.USER) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status not in [CCMCardStatus.BLOCKED_USER, CCMCardStatus.BLOCKED_TEMP, CCMCardStatus.BLOCKED_FRAUD]:
            raise HTTPException(
                status_code=400,
                detail=f"Card is not blocked. Current status: {card.status.value}. "
                       "Only blocked cards can be unblocked."
            )

        # Admin-block restriction
        if card.status == CCMCardStatus.BLOCKED_FRAUD and actor == ActorType.USER:
            raise HTTPException(
                status_code=403,
                detail="This card was blocked by an administrator for security reasons. "
                       "Only an admin can unblock this card. Please contact customer support."
            )

        # Generate a unique unblock_id as linkage
        unblock_id = uuid.uuid4()

        return {
            "message": "🔓 Authenticate with OTP to unblock the card",
            "detail": (
                f"Use unblock_id as linkage_id in the generic OTP endpoints.\n"
                f"Step 1: POST /auth/otp/generate with purpose=UNBLOCK and linkage_id={unblock_id}\n"
                f"Step 2: POST /auth/otp/verify with the OTP and linkage_id={unblock_id}\n"
                f"Step 3: POST /cards/{card_id}?command=unblock"
            ),
            "unblock_id": str(unblock_id)
        }

    # -------------------------------------------------
    # 4. UNBLOCK — Confirm (unblock)
    # -------------------------------------------------
    @staticmethod
    def confirm_unblock(db: Session, card_id: uuid.UUID, request: CCMCardUnblockRequest, actor: ActorType = ActorType.USER) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status not in [CCMCardStatus.BLOCKED_USER, CCMCardStatus.BLOCKED_TEMP, CCMCardStatus.BLOCKED_FRAUD]:
            raise HTTPException(
                status_code=400,
                detail=f"Card is not blocked. Current status: {card.status.value}."
            )

        # Admin-block restriction
        if card.status == CCMCardStatus.BLOCKED_FRAUD and actor == ActorType.USER:
            raise HTTPException(
                status_code=403,
                detail="This card was blocked by an administrator for security reasons. "
                       "Only an admin can unblock this card. Please contact customer support."
            )

        # Check the most recent UNBLOCK OTP was verified
        otp_record = db.query(OTPCode).filter(
            OTPCode.user_id == card.user_id,
            OTPCode.purpose == OTPPurpose.UNBLOCK,
            OTPCode.is_used == False
        ).order_by(OTPCode.created_at.desc()).first()

        if not otp_record or not getattr(otp_record, 'is_verified', False):
            raise HTTPException(
                status_code=400,
                detail="OTP verification required before unblocking. "
                       "Please use the unblock_otp command first to initiate the process."
            )

        card.status = CCMCardStatus.ACTIVE
        card.blocked_reason = None
        card.blocked_by_actor = None
        otp_record.is_used = True
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.ACTIVE
            
        db.commit()

        return {
            "message": "✔ Card Active Again",
            "details": [
                "You can now use your card.",
                "All transactions are re-enabled."
            ]
        }

    # -------------------------------------------------
    # 5. REPLACE CARD
    # -------------------------------------------------
    @staticmethod
    def replace_card(db: Session, card_id: uuid.UUID, request: CCMCardReplaceRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status in [CCMCardStatus.TERMINATED, CCMCardStatus.REPLACED]:
            raise HTTPException(
                status_code=400,
                detail=f"Card cannot be replaced. Current status: {card.status.value}."
            )

        old_card_id = card.id
        account = card.credit_account

        new_card_number = generate_card_number()
        new_expiry = generate_expiry()

        new_card = CCMCreditCard(
            user_id=card.user_id,
            card_number=new_card_number,
            card_network=card.card_network,
            card_variant=card.card_variant,
            expiry_date=new_expiry,
            cvv_hash=hash_cvv(generate_cvv()),
            status=CCMCardStatus.ISSUED,
            issued_at=datetime.now(timezone.utc),
            reissue_reference=old_card_id,
            credit_account=account,
            is_virtual=(request.reissue_type == CCMReissueType.VIRTUAL)
        )
        db.add(new_card)
        card.status = CCMCardStatus.REPLACED
        db.commit()
        db.refresh(new_card)

        return {
            "message": "✔ Replacement Card Ordered",
            "details": [
                f"Old Card ({old_card_id}): Blocked",
                f"New Card ({new_card.id}): Issued",
                f"Last 4 Digits: **** {new_card_number[-4:]}",
                f"Expiry: {new_expiry}",
                "Delivery ETA: 5 days"
            ]
        }

    # -------------------------------------------------
    # 6. TERMINATE CARD
    # -------------------------------------------------
    @staticmethod
    def terminate_card(db: Session, card_id: uuid.UUID, request: CCMCardTerminateRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status == CCMCardStatus.TERMINATED:
            raise HTTPException(
                status_code=400,
                detail="Card is already terminated."
            )

        # Check outstanding balance
        outstanding = Decimal("0")
        if card.credit_account:
            outstanding = card.credit_account.outstanding_balance or Decimal("0")

        if outstanding > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot terminate card with outstanding balance: ₹{outstanding}. "
                       "Please clear the balance first."
            )

        card.status = CCMCardStatus.TERMINATED
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.CLOSED
            
        db.commit()

        return {
            "message": "🔒 Card Closed Successfully",
            "details": [
                f"Outstanding Balance: ₹{outstanding}",
                f"Reason: {request.reason}",
                "This action is permanent and cannot be undone."
            ]
        }

    # -------------------------------------------------
    # 7. RENEW CARD (Expiry Replacement)
    # -------------------------------------------------
    @staticmethod
    def renew_card(db: Session, card_id: uuid.UUID, request: CCMCardRenewRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status == CCMCardStatus.TERMINATED:
            raise HTTPException(
                status_code=400,
                detail="Terminated cards cannot be renewed. Please apply for a new card."
            )

        # Create a replace request from the renew request
        replace_req = CCMCardReplaceRequest(
            reason=CCMReissueReason.EXPIRY,
            reissue_type=request.reissue_type,
            **{"Delivery Address": request.delivery_address}
        )
        result = CardManagementService.replace_card(db, card_id, replace_req)
        result["message"] = "🔄 Card Renewal Ordered"
        return result

    # -------------------------------------------------
    # UTILITY: Get Card Transactions
    # -------------------------------------------------
    @staticmethod
    def get_card_transactions(db: Session, card_id: uuid.UUID) -> List[CCMCardTransaction]:
        card = _get_card_or_404(db, card_id)
        return db.query(CCMCardTransaction).filter(CCMCardTransaction.card_id == card_id).all()
