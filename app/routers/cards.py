import uuid
from typing import Union, List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.schemas.responses import CardIssueResponse, CardLifecycleResponse
from app.schemas.card_management import (
    CCMCardIssueRequest, CCMCardActivationRequest,
    CCMCardBlockRequest, CCMCardUnblockRequest,
    CCMCardReplaceRequest, CCMCardTerminateRequest, CCMCardRenewRequest
)
from app.services.card_management_service import CardManagementService
from app.models.enums import CCMCommand, ActorType
from app.core.app_error import AppError
from app.models.card_management import CCMCreditCard
from app.core.roles import Role

router = APIRouter(prefix="/cards", tags=["Cards"])
issue_router = APIRouter(prefix="/credit-account", tags=["Card Issuance"])

def _assert_card_ownership(db: Session, card_id: uuid.UUID, principal: AuthenticatedPrincipal):
    if principal.role in [Role.ADMIN, Role.SUPERADMIN]:
        return
    card = db.query(CCMCreditCard).filter(CCMCreditCard.id == card_id).first()
    if not card or str(card.user_id) != principal.user_id:
         raise AppError(code="ACCESS_DENIED", message="Access Denied: You do not own this card.", http_status=403)

@issue_router.post("/{credit_account_id}/card", status_code=status.HTTP_201_CREATED, response_model=CardIssueResponse)
def issue_card_endpoint(
    credit_account_id: uuid.UUID,
    request: CCMCardIssueRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card:issue"))
):
    """
    Issues a new credit card for the specified credit account.

    **What it does:**
    Creates a new physical or virtual credit card linked to an existing credit account.
    Generates a masked PAN, CVV hash, expiry date, and sets initial card status to `CREATED`.

    **Request Body (`CCMCardIssueRequest`):**
    - `card_network`: `VISA` | `MASTERCARD` | `RUPAY` | `AMEX`
    - `card_variant`: `CLASSIC` | `GOLD` | `PLATINUM` | `SIGNATURE` | `INFINITE`
    - `is_virtual`: Boolean flag for virtual card issuance

    **Roles:** `card:issue` (Admin / Super Admin only)

    **Response:** Issued card details including `card_id`, `pan_masked`, `card_status`, `expiry_date`.
    """
    try:
        result = CardManagementService.issue_card(db, credit_account_id, request)
        return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)
    except AppError:
        raise
    except Exception as e:
        raise AppError(code="INTERNAL_ERROR", message=f"Failed to issue card: {str(e)}", http_status=500)

@router.post("/{card_id}/activate")
async def activate_card_dispatcher(
    card_id: uuid.UUID,
    body: CCMCardActivationRequest,
    command: str = Query(..., description="Stage: 'generate' or 'activate'"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card:activate"))
):
    """
    Handles card activation in two stages.

    **What it does:**
    Stage 1 (`command=generate`): Generates an OTP for activation verification.
    Stage 2 (`command=activate`): Validates the OTP, sets the user's PIN, and
    transitions card status from `INACTIVE` → `ACTIVE`.

    **Query Parameter `command`:**
    - `generate` — Sends activation OTP to the registered mobile number.
    - `activate` — Completes activation with PIN and OTP verification.

    **Request Body (`CCMCardActivationRequest`):**
    - `pin`: 4-digit card PIN (required for `activate` stage)
    - `activation_id`: UUID returned from the `generate` stage

    **Roles:** `card:activate` (User / Admin) — Ownership enforced for Users.

    **Response:** `{ card_id, card_status, activated_at }` on success.
    """
    try:
        _assert_card_ownership(db, card_id, principal)
        if command == CCMCommand.GENERATE.value:
            result = CardManagementService.handle_activation_generate(db, card_id)
        elif command == CCMCommand.ACTIVATE.value:
            schema = body
            if not schema.pin:
                raise AppError(code="MISSING_FIELD", message="PIN is required for activation.", http_status=400)
            if not schema.activation_id:
                raise AppError(code="MISSING_FIELD", message="activation_id is required.", http_status=400)
            result = CardManagementService.handle_activation_final(db, card_id, schema)
        else:
            raise AppError(code="INVALID_COMMAND", message=f"Invalid activation command: '{command}'", http_status=400)
        
        return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)
    except AppError:
        raise
    except Exception as e:
        raise AppError(code="INTERNAL_ERROR", message=f"Activation failed: {str(e)}", http_status=500)

@router.post("/{card_id}")
async def card_lifecycle_dispatcher(
    card_id: uuid.UUID,
    data: Union[
        CCMCardBlockRequest, CCMCardUnblockRequest, CCMCardReplaceRequest, 
        CCMCardTerminateRequest, CCMCardRenewRequest
    ],
    command: str = Query(..., description="Action to perform on the card"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card:lifecycle"))
):
    """
    Dispatches card lifecycle actions via the `command` query parameter.

    **What it does:**
    A unified state machine for all post-activation card operations. Each command
    transitions the card through its lifecycle and enforces ownership for non-admin callers.

    **Query Parameter `command` (enum `CCMCommand`):**
    - `block` — Temporarily blocks the card. Body: `CCMCardBlockRequest` with `block_reason`.
      - `block_reason` enum: `SUSPICIOUS_ACTIVITY` | `GEO_MISMATCH` | `VELOCITY_CHECK` |
        `USER_REQUEST` | `FRAUD` | `LOST` | `STOLEN` | `TEMPORARY_BLOCK`
    - `unblock_otp` — Initiates unblock by sending OTP. Body: `CCMCardUnblockRequest`.
    - `unblock` — Confirms unblock with OTP. Body: `CCMCardUnblockRequest`.
    - `replace` — Reissues the card (damaged/lost/upgrade). Body: `CCMCardReplaceRequest`.
      - `reissue_reason` enum: `DAMAGED` | `LOST` | `UPGRADE` | `EXPIRY`
    - `terminate` — Permanently closes the card. Body: `CCMCardTerminateRequest`.
    - `renew` — Renews an expiring card. Body: `CCMCardRenewRequest`.
    - `freeze` / `unfreeze` — Temporary soft-lock toggle (no body required).

    **Roles:** `card:lifecycle` (User / Admin) — Ownership enforced for Users.

    **Response:** Updated card details including new `card_status`.
    """
    command = command.lower().strip()
    raw_data = data.model_dump() if hasattr(data, "model_dump") else data
    
    try:
        _assert_card_ownership(db, card_id, principal)
        actor = ActorType.ADMIN if principal.role in [Role.ADMIN, Role.SUPERADMIN] else ActorType.USER
        
        if command == CCMCommand.BLOCK.value.lower():
            validated_data = CCMCardBlockRequest.model_validate(raw_data)
            result = CardManagementService.block_card(db, card_id, validated_data, actor=actor)
        elif command == CCMCommand.UNBLOCK_OTP.value.lower():
            validated_data = CCMCardUnblockRequest.model_validate(raw_data)
            result = CardManagementService.initiate_unblock(db, card_id, validated_data, actor=actor)
        elif command == CCMCommand.UNBLOCK.value.lower():
            validated_data = CCMCardUnblockRequest.model_validate(raw_data)
            result = CardManagementService.confirm_unblock(db, card_id, validated_data, actor=actor)
        elif command == CCMCommand.REPLACE.value.lower():
            validated_data = CCMCardReplaceRequest.model_validate(raw_data)
            result = CardManagementService.replace_card(db, card_id, validated_data)
        elif command == CCMCommand.TERMINATE.value.lower():
            validated_data = CCMCardTerminateRequest.model_validate(raw_data)
            result = CardManagementService.terminate_card(db, card_id, validated_data)
        elif command == CCMCommand.RENEW.value.lower():
            validated_data = CCMCardRenewRequest.model_validate(raw_data)
            result = CardManagementService.renew_card(db, card_id, validated_data)
        elif command == CCMCommand.FREEZE.value.lower():
            result = CardManagementService.freeze_card(db, card_id)
        elif command == CCMCommand.UNFREEZE.value.lower():
            result = CardManagementService.unfreeze_card(db, card_id)
        else:
            valid_commands = ", ".join([c.value for c in CCMCommand])
            raise AppError(code="INVALID_COMMAND", message=f"Invalid command: '{command}'. Valid commands: {valid_commands}", http_status=400)
            
        return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)
    except AppError:
        raise
    except (ValueError, ValidationError) as e:
        raise AppError(code="INVALID_PAYLOAD", message=f"Validation error: {str(e)}", http_status=422)
    except Exception as e:
        raise AppError(code="INTERNAL_ERROR", message=f"Command '{command}' failed: {str(e)}", http_status=500)

@router.get("/{card_id}")
def get_card_details(
    card_id: uuid.UUID, 
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card:read"))
):
    """
    Retrieves full card details including status, PAN, expiry, and feature flags.

    **What it does:**
    Returns the complete card record with linked credit account information.
    Includes all feature toggles (contactless, international, online, ATM, domestic)
    and spending limits.

    **Roles:** `card:read` (User / Admin) — Ownership enforced for Users.

    **Response:** `CCMCreditCardResponse` with `{ id, card_number, card_network, card_variant,
    status, is_virtual, is_contactless_enabled, is_international_enabled, daily_spend_limit, ... }`
    """
    _assert_card_ownership(db, card_id, principal)
    from app.models.card_management import CCMCreditCard
    from sqlalchemy.orm import joinedload
    card = db.query(CCMCreditCard).options(
        joinedload(CCMCreditCard.credit_account)
    ).filter(CCMCreditCard.id == card_id).first()
    if not card:
        raise AppError(code="NOT_FOUND", message="Card not found. Please check the card_id.", http_status=404)
    
    # Needs to handle sqlalchemy object directly since envelope_success expects dict or Pydantic model dump
    from app.schemas.card_management import CCMCreditCardResponse
    card_schema = CCMCreditCardResponse.model_validate(card)
    return envelope_success(card_schema.model_dump(mode='json'))
