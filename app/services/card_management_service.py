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
    ActorType, CCMCommand, CCMReissueReason, CCMReissueType,
    CardStatus, CardType
)
from app.admin.models.card_issuance import Card, CreditAccount
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
        db.flush() # Get card ID

        # Mirror to Administrative Card table (Dual-Insert)
        admin_account = db.query(CreditAccount).filter(CreditAccount.id == account.id).first()
        if admin_account:
            admin_card = Card(
                id=new_card.id, # Keep IDs in sync
                credit_account_id=admin_account.id,
                card_product_id=admin_account.card_product_id,
                card_type=CardType.PRIMARY,
                pan_encrypted="---SYNC-ENCRYPTED---",
                pan_masked=card_number[-4:].rjust(16, '*'),
                expiry_date=expiry_date,
                expiry_date_masked="**/**",
                cvv_encrypted="---SYNC-ENCRYPTED---",
                cvv_masked="***",
                card_status=CardStatus.INACTIVE, # Core ISSUED matches Admin INACTIVE
                issued_at=new_card.issued_at
            )
            db.add(admin_card)

        db.commit()
        db.refresh(new_card)

        last_4 = card_number[-4:]
        return {
            "message": "Card issued successfully",
            "card_id": str(new_card.id),
            "pan_masked": f"XXXX-XXXX-XXXX-{last_4}",
            "card_status": "ISSUED",
            "expiry_date": expiry_date,
            "card_network": new_card.card_network.value if new_card.card_network else "VISA",
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
            "old_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "activation_id": str(activation_id),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
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
        otp_record.is_used = True
        
        # Mirror to Admin Card
        admin_card = db.query(Card).filter(Card.id == card.id).first()
        if admin_card:
            admin_card.card_status = CardStatus.ACTIVE
            admin_card.activation_date = card.activated_at
            admin_card.pin_hashed = card.pin_hash
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.ACTIVE
            
        db.commit()

        return {
            "message": "Card Activated & PIN Set Successfully",
            "old_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "activation_id": str(request.activation_id),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
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
        
        # Mirror to Admin Card
        admin_card = db.query(Card).filter(Card.id == card.id).first()
        if admin_card:
            admin_card.card_status = CardStatus.BLOCKED

        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.FROZEN
            
        db.commit()

        return {
            "message": "Card Blocked",
            "old_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
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

        # Generate a unique unblock_id as linkage and persist it as a pre-verified intent
        unblock_id = uuid.uuid4()
        
        # Link to OTPCode table to persist the valid unblock session (marking as pre-verified)
        new_otp = OTPCode(
            user_id=card.user_id,
            otp_hash="DUMMY", # No real OTP needed for this flow
            purpose=OTPPurpose.LOGIN, # Dummy purpose
            linkage_id=unblock_id,
            is_verified=True, # Pre-verified as per requirement
            is_used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
        )
        db.add(new_otp)
        db.commit()

        return {
            "message": "Unblock process initiated. Use the provided unblock_id to confirm.",
            "old_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "unblock_id": str(unblock_id),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
        }

    # -------------------------------------------------
    # 4. UNBLOCK — Confirm (unblock)
    # -------------------------------------------------
    @staticmethod
    def confirm_unblock(db: Session, card_id: uuid.UUID, request: CCMCardUnblockRequest, actor: ActorType = ActorType.USER) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status not in [CCMCardStatus.BLOCKED_USER, CCMCardStatus.BLOCKED_TEMP, CCMCardStatus.BLOCKED_FRAUD]:
            raise AppError(
                code="INVALID_STATUS",
                message=f"Card is not blocked. Current status: {card.status.value}.",
                http_status=400
            )

        # Admin-block restriction
        if card.status == CCMCardStatus.BLOCKED_FRAUD and actor == ActorType.USER:
            raise AppError(
                code="INSUFFICIENT_PERMISSIONS",
                message="This card was blocked by an administrator for security reasons. Only an admin can unblock this card.",
                http_status=403
            )

        if not request.unblock_id:
            raise AppError(
                code="MISSING_FIELD",
                message="unblock_id is required.",
                http_status=400
            )

        try:
            unblock_uuid = uuid.UUID(request.unblock_id)
        except ValueError:
            raise AppError(
                code="INVALID_FORMAT",
                message="unblock_id must be a valid UUID.",
                http_status=400
            )

        # Check for a valid initiation record for this unblock_uuid
        otp_record = db.query(OTPCode).filter(
            OTPCode.linkage_id == unblock_uuid,
            OTPCode.is_used == False
        ).order_by(OTPCode.created_at.desc()).first()

        if not otp_record:
            raise AppError(
                code="INVALID_SESSION",
                message="No unblock session found for this unblock_id. Please use the unblock_ini command first.",
                http_status=400
            )

        old_status = card.status
        card.status = CCMCardStatus.ACTIVE
        card.blocked_reason = None
        card.blocked_by_actor = None
        
        # Mirror to Admin Card
        admin_card = db.query(Card).filter(Card.id == card.id).first()
        if admin_card:
            admin_card.card_status = CardStatus.ACTIVE

        otp_record.is_used = True
        
        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.ACTIVE
            
        db.commit()

        return {
            "message": "Card Active Again",
            "old_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
        }

    # -------------------------------------------------
    # 5. REPLACE CARD
    # -------------------------------------------------
    @staticmethod
    def replace_card(db: Session, card_id: uuid.UUID, request: CCMCardReplaceRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status in [CCMCardStatus.TERMINATED, CCMCardStatus.REPLACED]:
            raise AppError(
                code="INVALID_STATUS",
                message=f"Card cannot be replaced. Current status: {card.status.value}.",
                http_status=400
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
        db.flush() # Get ID

        # Mirror the retired card
        old_card_status = card.status
        card.status = CCMCardStatus.REPLACED
        admin_card_old = db.query(Card).filter(Card.id == card.id).first()
        if admin_card_old:
            admin_card_old.card_status = CardStatus.EXPIRED

        # Mirror the new card (Dual-Insert)
        admin_account = db.query(CreditAccount).filter(CreditAccount.id == account.id).first()
        if admin_account:
            admin_card_new = Card(
                id=new_card.id,
                credit_account_id=admin_account.id,
                card_product_id=admin_account.card_product_id,
                card_type=CardType.PRIMARY,
                pan_encrypted="---SYNC-ENCRYPTED---",
                pan_masked=new_card_number[-4:].rjust(16, '*'),
                expiry_date=new_expiry,
                expiry_date_masked="**/**",
                cvv_encrypted="---SYNC-ENCRYPTED---",
                cvv_masked="***",
                card_status=CardStatus.INACTIVE,
                issued_at=new_card.issued_at
            )
            db.add(admin_card_new)

        db.commit()
        db.refresh(new_card)

        return {
            "message": "Replacement Card Ordered",
            "old_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "card_id": str(new_card.id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
        }

    # -------------------------------------------------
    # 6. TERMINATE CARD
    # -------------------------------------------------
    @staticmethod
    def terminate_card(db: Session, card_id: uuid.UUID, request: CCMCardTerminateRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status == CCMCardStatus.TERMINATED:
            raise AppError(
                code="ALREADY_TERMINATED",
                message="Card is already terminated.",
                http_status=400
            )

        # Check outstanding balance
        outstanding = Decimal("0")
        if card.credit_account:
            outstanding = card.credit_account.outstanding_balance or Decimal("0")

        if outstanding > 0:
            raise AppError(
                code="OUTSTANDING_BALANCE",
                message=f"Cannot terminate card with outstanding balance: ₹{outstanding}.",
                http_status=400
            )

        old_status = card.status
        card.status = CCMCardStatus.TERMINATED
        
        # Mirror to Admin Card
        admin_card = db.query(Card).filter(Card.id == card.id).first()
        if admin_card:
            admin_card.card_status = CardStatus.BLOCKED # Using BLOCKED as Terminal state proxy

        if card.credit_account:
            card.credit_account.status = CCMAccountStatus.CLOSED
            
        db.commit()

        return {
            "message": "Card Closed Successfully",
            "old_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
        }

    # -------------------------------------------------
    # 7. RENEW CARD (Expiry Replacement)
    # -------------------------------------------------
    @staticmethod
    def renew_card(db: Session, card_id: uuid.UUID, request: CCMCardRenewRequest) -> dict:
        card = _get_card_or_404(db, card_id)

        if card.status == CCMCardStatus.TERMINATED:
            raise AppError(
                code="INVALID_STATUS",
                message="Terminated cards cannot be renewed. Please apply for a new card.",
                http_status=400
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
        
        # Mirror to Admin Card
        admin_card = db.query(Card).filter(Card.id == card.id).first()
        if admin_card:
            admin_card.card_status = CardStatus.BLOCKED

        db.commit()
        return {
            "message": "Card Frozen Successfully",
            "old_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
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
        
        # Mirror to Admin Card
        admin_card = db.query(Card).filter(Card.id == card.id).first()
        if admin_card:
            admin_card.card_status = CardStatus.ACTIVE

        db.commit()
        return {
            "message": "Card Unfrozen Successfully",
            "old_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
            "new_status": card.status.value if hasattr(card.status, 'value') else str(card.status),
            "card_id": str(card_id),
            "card_status": card.status.value if hasattr(card.status, 'value') else str(card.status)
        }

    # -------------------------------------------------
    # UTILITY: Get Card Transactions
    # -------------------------------------------------
    @staticmethod
    def get_card_transactions(db: Session, card_id: uuid.UUID) -> List[CCMCardTransaction]:
        card = _get_card_or_404(db, card_id)
        return db.query(CCMCardTransaction).filter(CCMCardTransaction.card_id == card_id).all()
