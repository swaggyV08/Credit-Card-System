import uuid
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.api.deps import get_db
from app.schemas.card_management import (
    CCMCardIssueRequest, CCMCreditCardResponse, CCMCardActivationRequest,
    CCMCardBlockRequest, CCMCardTransactionResponse, CCMCardUnblockRequest,
    CCMCardReplaceRequest, CCMCardTerminateRequest, CCMCardRenewRequest,
    CardIssuanceResponse, CardActivationResponse, CardActionResponse
)
from app.services.card_management_service import CardManagementService
from app.models.enums import CCMCommand

router = APIRouter()
issue_router = APIRouter()

# =====================================================
# 1. ISSUE CARD: POST /{credit_account_id}/card
# =====================================================
@issue_router.post("/{credit_account_id}/card", status_code=status.HTTP_201_CREATED,
             response_model=CardIssuanceResponse)
def issue_card_endpoint(
    credit_account_id: uuid.UUID,
    request: CCMCardIssueRequest,
    db: Session = Depends(get_db)
):
    """Issues a new credit card for the specified credit account.

    **Required fields:**
    - `credit_account_id` (UUID): The credit account to link.
    - `card_product_id` (UUID): Card product template.
    - `card_type` (str): PHYSICAL or VIRTUAL.
    - `embossed_name` (str): Name printed on card (letters and spaces only).
    - `delivery_address` (str): Shipping destination (min 5 chars).
    """
    try:
        return CardManagementService.issue_card(db, credit_account_id, request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to issue card: {str(e)}"
        )


# =====================================================
# 2. ACTIVATE CARD: POST /cards/{card_id}/activate
# =====================================================
@router.post("/{card_id}/activate", response_model=CardActivationResponse)
async def activate_card_dispatcher(
    card_id: uuid.UUID,
    body: CCMCardActivationRequest,
    command: str = Query(..., description="Stage: 'generate' (Stage 1 — creates activation_id and triggers OTP) or 'activate' (Stage 3 — sets PIN and activates card)"),
    db: Session = Depends(get_db)
):
    """Handles card activation in two stages:

    **Stage 1** — `command=generate`:
    - No request body required.
    - Returns a unique `activation_id`. Use this as `linkage_id` in the generic OTP generate endpoint (`POST /auth/otp/generate`).
    - Then verify the OTP via the generic OTP verify endpoint (`POST /auth/otp/verify`) using the same `linkage_id`.

    **Stage 2** — (Handled externally via `POST /auth/otp/verify`)

    **Stage 3** — `command=activate`:
    - **Required fields:**
      - `pin` (str): 4-digit numeric PIN.
      - `activation_id` (UUID): The activation_id from Stage 1.
    - The system checks that OTP was verified for this `activation_id` before activating.
    """
    try:
        if command == CCMCommand.GENERATE.value:
            return CardManagementService.handle_activation_generate(db, card_id)
        elif command == CCMCommand.ACTIVATE.value:
            schema = body
            if not schema.pin:
                raise HTTPException(
                    status_code=400,
                    detail="PIN is required for activation. Please provide a 4-digit numeric PIN."
                )
            if not schema.activation_id:
                raise HTTPException(
                    status_code=400,
                    detail="activation_id is required. Please use the activation_id returned from Stage 1 (command=generate)."
                )
            return CardManagementService.handle_activation_final(db, card_id, schema)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid activation command: '{command}'. Valid commands: 'generate', 'activate'."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Activation failed: {str(e)}"
        )


# =====================================================
# 3-7. CARD LIFECYCLE DISPATCHER: POST /cards/{card_id}
# =====================================================
@router.post("/{card_id}", response_model=CardActionResponse)
async def card_lifecycle_dispatcher(
    card_id: uuid.UUID,
    data: Union[
        CCMCardBlockRequest, CCMCardUnblockRequest, CCMCardReplaceRequest, 
        CCMCardTerminateRequest, CCMCardRenewRequest
    ],
    command: str = Query(..., description="Action to perform on the card: block, unblock_otp, unblock, replace, terminate, renew"),
    db: Session = Depends(get_db)
):
    """
    Dispatches card lifecycle actions via the `command` query parameter.
    
    **Exactly why we are implementing this**:
    To provide a single API interface for all card management operations. This pattern 
    simplifies the frontend integration and ensures that state transitions (e.g., blocking 
    due to loss) are handled using consistent validation and auditing rules.
    
    **Request Bodies by command:**
    - `block`: `{ "reason": "LOST/STOLEN/..." }`
    - `unblock_otp`: `{ "reason": "..." }`
    - `unblock`: `{ "reason": "..." }`
    - `replace`: `{ "reason": "...", "reissue_type": "...", "Delivery Address": "..." }`
    - `terminate`: `{ "reason": "..." }`
    - `renew`: `{ "reissue_type": "...", "delivery_address": "..." }`
    """
    command = command.lower().strip()
    # Convert Pydantic object back to dict for manual command-based re-validation
    # This avoids polymorphic ambiguity in the Union.
    raw_data = data.model_dump() if hasattr(data, "model_dump") else data
    
    try:
        if command == CCMCommand.BLOCK.value.lower():
            validated_data = CCMCardBlockRequest.model_validate(raw_data)
            return CardManagementService.block_card(db, card_id, validated_data)

        elif command == CCMCommand.UNBLOCK_OTP.value.lower():
            validated_data = CCMCardUnblockRequest.model_validate(raw_data)
            return CardManagementService.initiate_unblock(db, card_id, validated_data)

        elif command == CCMCommand.UNBLOCK.value.lower():
            validated_data = CCMCardUnblockRequest.model_validate(raw_data)
            return CardManagementService.confirm_unblock(db, card_id, validated_data)

        elif command == CCMCommand.REPLACE.value.lower():
            validated_data = CCMCardReplaceRequest.model_validate(raw_data)
            return CardManagementService.replace_card(db, card_id, validated_data)

        elif command == CCMCommand.TERMINATE.value.lower():
            validated_data = CCMCardTerminateRequest.model_validate(raw_data)
            return CardManagementService.terminate_card(db, card_id, validated_data)

        elif command == CCMCommand.RENEW.value.lower():
            validated_data = CCMCardRenewRequest.model_validate(raw_data)
            return CardManagementService.renew_card(db, card_id, validated_data)

        else:
            valid_commands = ", ".join([c.value for c in CCMCommand])
            raise HTTPException(
                status_code=400,
                detail=f"Invalid command: '{command}'. Valid commands: {valid_commands}"
            )
    except HTTPException:
        raise
    except (ValueError, ValidationError) as e:
        raise HTTPException(
            status_code=422,
            detail=f"Validation error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Command '{command}' failed: {str(e)}"
        )


# =====================================================
# UTILITY ENDPOINTS
# =====================================================

@router.get("/{card_id}/transactions", response_model=List[CCMCardTransactionResponse])
def get_card_transactions(card_id: uuid.UUID, db: Session = Depends(get_db)):
    """Retrieves the transaction history for a card."""
    return CardManagementService.get_card_transactions(db, card_id)


@router.get("/{card_id}", response_model=CCMCreditCardResponse)
def get_card_details(card_id: uuid.UUID, db: Session = Depends(get_db)):
    """Retrieves full card details including status, PAN, expiry, linked credit account, and feature flags."""
    from app.models.card_management import CCMCreditCard
    from sqlalchemy.orm import joinedload
    card = db.query(CCMCreditCard).options(
        joinedload(CCMCreditCard.credit_account)
    ).filter(CCMCreditCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found. Please check the card_id.")
    return card
