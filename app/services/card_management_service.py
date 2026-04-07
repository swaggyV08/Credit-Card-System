import uuid
import random
import hashlib
from typing import List
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, joinedload
from app.core.app_error import AppError

from app.models.card_management import CCMCreditCard, CCMCreditAccount, CCMCardTransaction
from app.models.customer import OTPCode, OTPPurpose
from app.models.enums import (
    CCMCardStatus, CCMAccountStatus, CardNetwork, CardVariant, CCMFraudBlockReason, 
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
        raise AppError(
            code="NOT_FOUND",
            message=f"Card not found. No card exists with ID: {card_id}",
            http_status=404
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
            raise AppError(
                code="NOT_FOUND",
                message=f"Credit account not found. No account exists with ID: {credit_account_id}",
                http_status=404
            )

        # Validate request credit_account_id matches path
        if request.credit_account_id != credit_account_id:
            raise AppError(
                code="INVALID_PAYLOAD",
                message="credit_account_id in request body does not match the path parameter.",
                http_status=400
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
            raise AppError(
                code="ALREADY_ACTIVE",
                message="Card is already active. No activation needed.",
                http_status=400
            )

        if card.status not in [CCMCardStatus.ISSUED, CCMCardStatus.INACTIVE]:
            raise AppError(
                code="INVALID_STATUS",
                message=f"Card cannot be activated in its current state: {card.status.value}. Card must be in ISSUED or INACTIVE status.",
                http_status=400
            )

        # Generate a unique activation_id
        activation_id = uuid.uuid4()

        return {
            "message": "Activation initiated",
            "old_status": card.status,
            "new_status": card.status,
            "activation_id": activation_id,
            "card_id": card_id
        }

    # -------------------------------------------------
    # 2. ACTIVATION — Stage 3: Set PIN and activate
    # -------------------------------------------------
    @staticmethod
    def handle_activation_final(db: Session, card_id: uuid.UUID, request: CCMCardActivationRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status == CCMCardStatus.ACTIVE:
            raise AppError(code="ALREADY_ACTIVE", message="Card is already active.", http_status=400)

        if card.status not in [CCMCardStatus.ISSUED, CCMCardStatus.INACTIVE]:
            raise AppError(code="INVALID_STATUS", message=f"Card cannot be activated in its current state: {card.status.value}.", http_status=400)

        # Verify that OTP was verified for this activation_id (linkage_id)
        # We rely solely on the cryptographic uniqueness of activation_id (uuid4)
        # to cross-verify, preventing issues if the frontend sends the wrong 'purpose' Enum.
        otp_record = db.query(OTPCode).filter(
            OTPCode.linkage_id == request.activation_id,
            OTPCode.is_used == False
        ).order_by(OTPCode.created_at.desc()).first()

        if not otp_record:
            raise AppError(
                code="OTP_REQUIRED",
                message="No OTP verification found for this activation_id. Please complete OTP verification first.",
                http_status=400
            )

        if not getattr(otp_record, 'is_verified', False):
            raise AppError(
                code="OTP_NOT_VERIFIED",
                message="OTP has not been verified yet. Please verify the OTP first.",
                http_status=400
            )

        # Activate card and set PIN
        old_status = card.status
        card.status = CCMCardStatus.ACTIVE
        card.activated_at = datetime.now(timezone.utc)
        card.pin_hash = hash_pin(request.pin)
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.ACTIVE
            
        otp_record.is_used = True
        db.commit()

        return {
            "message": "Card Activated & PIN Set Successfully",
            "old_status": old_status,
            "new_status": card.status,
            "activation_id": request.activation_id,
            "card_id": card_id
        }

    # -------------------------------------------------
    # 3. BLOCK CARD
    # -------------------------------------------------
    @staticmethod
    def block_card(db: Session, card_id: uuid.UUID, request: CCMCardBlockRequest, actor: ActorType = ActorType.USER) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status in [CCMCardStatus.TERMINATED, CCMCardStatus.REPLACED, CCMCardStatus.EXPIRED]:
            raise AppError(
                code="INVALID_STATUS",
                message=f"Card cannot be blocked. Current status: {card.status.value}.",
                http_status=400
            )

        if card.status in [CCMCardStatus.BLOCKED_USER, CCMCardStatus.BLOCKED_FRAUD, CCMCardStatus.BLOCKED_TEMP]:
            raise AppError(
                code="ALREADY_BLOCKED",
                message=f"Card is already blocked. Current status: {card.status.value}.",
                http_status=400
            )

        old_status = card.status
        card.status = CCMCardStatus.BLOCKED_USER if actor == ActorType.USER else CCMCardStatus.BLOCKED_FRAUD
        card.blocked_reason = request.reason
        card.blocked_by_actor = actor
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.FROZEN
            
        db.commit()

        return {
            "message": "Card Blocked",
            "old_status": old_status,
            "new_status": card.status
        }

    # -------------------------------------------------
    # 4. UNBLOCK — Initiate (unblock_otp)
    # -------------------------------------------------
    @staticmethod
    def initiate_unblock(db: Session, card_id: uuid.UUID, request: CCMCardUnblockRequest, actor: ActorType = ActorType.USER) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status not in [CCMCardStatus.BLOCKED_USER, CCMCardStatus.BLOCKED_TEMP, CCMCardStatus.BLOCKED_FRAUD, CCMCardStatus.BLOCKED_FRAUD]:
            raise AppError(
                code="INVALID_STATUS",
                message=f"Card is not blocked. Current status: {card.status.value}.",
                http_status=400
            )

        # Admin-block restriction
        if card.status == CCMCardStatus.BLOCKED_FRAUD and actor == ActorType.USER:
            raise AppError(
                code="INSUFFICIENT_PERMISSIONS",
                message="This card was blocked by an administrator for security reasons.",
                http_status=403
            )

        # Generate a unique unblock_id as linkage
        unblock_id = uuid.uuid4()

        return {
            "message": "Unblock process initiated. Authenticate with OTP.",
            "old_status": card.status,
            "new_status": card.status,  # Status hasn't changed yet
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

        if not request.unblock_id:
            raise HTTPException(
                status_code=400,
                detail="unblock_id is required."
            )

        try:
            unblock_uuid = uuid.UUID(request.unblock_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="unblock_id must be a valid UUID."
            )

        # Check the most recent OTP was verified for this unblock_uuid
        # Cross-verifying strictly by linkage_id to handle cases where 
        # the client used a different purpose (e.g. default "LOGIN" from Swagger)
        otp_record = db.query(OTPCode).filter(
            OTPCode.linkage_id == unblock_uuid,
            OTPCode.is_used == False
        ).order_by(OTPCode.created_at.desc()).first()

        if not otp_record or not getattr(otp_record, 'is_verified', False):
            raise HTTPException(
                status_code=400,
                detail="OTP verification required before unblocking. "
                       "Please use the unblock_otp command first to initiate the process and verify OTP."
            )

        old_status = card.status
        card.status = CCMCardStatus.ACTIVE
        card.blocked_reason = None
        card.blocked_by_actor = None
        otp_record.is_used = True
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.ACTIVE
            
        db.commit()

        return {
            "message": "Card Active Again",
            "old_status": old_status,
            "new_status": card.status
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
        old_status = card.status
        card.status = CCMCardStatus.REPLACED
        db.commit()
        db.refresh(new_card)

        return {
            "message": "Replacement Card Ordered",
            "old_status": old_status,
            "new_status": card.status,
            "card_id": str(new_card.id)
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

        old_status = card.status
        card.status = CCMCardStatus.TERMINATED
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.CLOSED
            
        db.commit()

        return {
            "message": "Card Closed Successfully",
            "old_status": old_status,
            "new_status": card.status
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
        result["message"] = "Card Renewal Ordered"
        return result

    # -------------------------------------------------
    # 8. FREEZE CARD
    # -------------------------------------------------
    @staticmethod
    def freeze_card(db: Session, card_id: uuid.UUID) -> dict:
        card = _get_card_or_404(db, card_id)
        if card.status != CCMCardStatus.ACTIVE:
            raise AppError(code="INVALID_STATUS", message=f"Only ACTIVE cards can be frozen. Current status: {card.status.value}.", http_status=400)
        
        old_status = card.status
        card.status = CCMCardStatus.BLOCKED_TEMP
        db.commit()
        return {
            "message": "Card Frozen Successfully",
            "old_status": old_status,
            "new_status": card.status,
            "card_id": str(card_id)
        }

    # -------------------------------------------------
    # 9. UNFREEZE CARD
    # -------------------------------------------------
    @staticmethod
    def unfreeze_card(db: Session, card_id: uuid.UUID) -> dict:
        card = _get_card_or_404(db, card_id)
        if card.status != CCMCardStatus.BLOCKED_TEMP:
            raise AppError(code="INVALID_STATUS", message=f"Only frozen cards can be unfrozen. Current status: {card.status.value}.", http_status=400)
        
        old_status = card.status
        card.status = CCMCardStatus.ACTIVE
        db.commit()
        return {
            "message": "Card Unfrozen Successfully",
            "old_status": old_status,
            "new_status": card.status,
            "card_id": str(card_id)
        }

    # -------------------------------------------------
    # UTILITY: Get Card Transactions
    # -------------------------------------------------
    @staticmethod
    def get_card_transactions(db: Session, card_id: uuid.UUID) -> List[CCMCardTransaction]:
        card = _get_card_or_404(db, card_id)
        return db.query(CCMCardTransaction).filter(CCMCardTransaction.card_id == card_id).all()
