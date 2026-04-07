import uuid
from typing import Union, List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
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
issue_router = APIRouter(prefix="/card_product", tags=["Card Issuance"])

def _assert_card_ownership(db: Session, card_id: uuid.UUID, principal: AuthenticatedPrincipal):
    if principal.role in [Role.ADMIN, Role.SUPERADMIN]:
        return
    card = db.query(CCMCreditCard).filter(CCMCreditCard.id == card_id).first()
    if not card or str(card.user_id) != principal.user_id:
         raise AppError(code="ACCESS_DENIED", message="Access Denied: You do not own this card.", http_status=403)

@issue_router.post("/{credit_account_id}/card", status_code=status.HTTP_201_CREATED)
def issue_card_endpoint(
    credit_account_id: uuid.UUID,
    request: CCMCardIssueRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("card:issue"))
):
    """Issues a new credit card for the specified credit account."""
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
    """Handles card activation in two stages ('generate' and 'activate')"""
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
    """Dispatches card lifecycle actions via the `command` query parameter."""
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
    """Retrieves full card details including status, PAN, expiry, linked credit account, and feature flags."""
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
