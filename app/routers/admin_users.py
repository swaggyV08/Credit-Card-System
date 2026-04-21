"""
Admin: User Management endpoints.

Provides admin-facing endpoints to list and view detailed user data,
including CIF/KYC status, application status, credit accounts, and cards.
"""
from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.orm import Session
from typing import Optional, Literal

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.core.validators import validate_enum_case_strict
from app.schemas.base import envelope_success, build_pagination
from app.core.app_error import AppError
from app.models.auth import User
from app.models.customer import CustomerProfile
from app.admin.models.card_issuance import CreditCardApplication, CreditAccount, Card
from app.admin.schemas.user_mgmt import (
    AdminUserDetailsResponse, CreditAccountDetail, CardDetail
)
from app.schemas.responses import UserGetResponse

router = APIRouter(prefix="/users", tags=["Admin: User Management"])


@router.get(
    "/",
    summary="Get Users",
    description="""
**Unified endpoint to retrieve users.**

### Commands
- `command=all` — Returns a paginated list of all users with enriched admin-relevant data.
- `command=by_id` — Returns comprehensive detail for a single user (requires `user_id` header).

### Query Parameters
- `role`: Filter users by role (full UPPER or lower only)
- `cif_completed`: Filter by CIF completion status
- `page`, `page_size`: Pagination controls

### Example Success Response (command=all)
```json
{
  "status": "success",
  "data": {
    "items": [
      {
        "user_id": "ZNBNQ000001",
        "name": "Vishnu Prasad",
        "email": "vishnu@example.com",
        "is_cif_completed": true,
        "is_kyc_completed": true,
        "kyc_status": "COMPLETED",
        "cif_status": "COMPLETED",
        "application_status": "APPROVED",
        "credit_account_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "created_at": "2026-04-08T10:30:00+00:00",
        "updated_at": null
      }
    ],
    "pagination": {
      "total": 1,
      "page": 1,
      "page_size": 20,
      "total_pages": 1
    }
  },
  "meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-08T10:30:00.000000+00:00",
    "api_version": "1.0.0"
  },
  "errors": []
}
```

### Example Success Response (command=by_id)
```json
{
  "status": "success",
  "data": {
    "user_id": "ZNBNQ000001",
    "email": "vishnu@example.com",
    "phone_number": "+919876543210",
    "name": "Vishnu Prasad",
    "is_cif_completed": true,
    "is_kyc_completed": true,
    "kyc_status": "COMPLETED",
    "cif_status": "COMPLETED",
    "application_status": "ACCOUNT_CREATED",
    "credit_account_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "total_credit_accounts": 1,
    "total_cards": 2,
    "credit_accounts": [
      {
        "credit_account_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "readable_id": "ACC-000001",
        "account_status": "ACTIVE",
        "cards": [
          {
            "card_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "card_readable_id": "CRD-000001",
            "card_status": "ACTIVE",
            "pan_masked": "XXXX-XXXX-XXXX-1234"
          }
        ]
      }
    ],
    "created_at": "2026-04-08T10:30:00+00:00",
    "updated_at": null
  },
  "meta": { ... },
  "errors": []
}
```

**Roles:** `user:list`, `user:detail` (Admin / Manager / SuperAdmin)
""",
    dependencies=[Depends(require("user:list"))],
    response_model=UserGetResponse
)
def get_users(
    command: Literal["all", "by_id"] = Query(..., description="Action to perform"),
    user_id: Optional[str] = Header(None, description="Required for command=by_id"),
    role: Optional[str] = Query(None, description="Filter by role (full UPPER or lower only)"),
    cif_completed: Optional[bool] = Query(None, description="Filter by CIF completion"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("user:list")),
):
    if command == "by_id":
        if not user_id:
            raise AppError(code="MISSING_USER_ID", message="user_id header is required for command=by_id", http_status=422)
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise AppError(code="NOT_FOUND", message="User not found", http_status=404)

        profile = db.query(CustomerProfile).filter(
            CustomerProfile.user_id == user.id
        ).first()

        name = None
        kyc_status = "NOT_STARTED"
        cif_status = "NOT_STARTED"

        if profile:
            name = (
                f"{profile.first_name} {profile.last_name}".strip()
                if profile.first_name
                else user.full_name
            )
            kyc_status = profile.kyc_state.value if profile.kyc_state else "NOT_STARTED"
            cif_status = profile.customer_status or "IN_PROGRESS"
        else:
            name = user.full_name

        latest_app = (
            db.query(CreditCardApplication)
            .filter(CreditCardApplication.user_id == user.id)
            .order_by(CreditCardApplication.submitted_at.desc())
            .first()
        )
        app_status = "NOT_APPLIED"
        if latest_app and latest_app.application_status:
            app_status = getattr(
                latest_app.application_status, "value",
                latest_app.application_status
            )

        accounts = (
            db.query(CreditAccount).filter(CreditAccount.user_id == user.id).all()
            if profile else []
        )

        account_details = []
        total_cards = 0

        for acc in accounts:
            cards = db.query(Card).filter(Card.credit_account_id == acc.id).all()
            card_list = [
                CardDetail(
                    card_id=c.id,
                    card_readable_id=c.readable_id,
                    card_status=c.card_status,
                    pan_masked=c.pan_masked
                ) for c in cards
            ]
            total_cards += len(card_list)

            account_details.append(
                CreditAccountDetail(
                    credit_account_id=acc.id,
                    readable_id=acc.readable_id,
                    account_status=acc.account_status,
                    cards=card_list
                )
            )

        credit_account_id = str(accounts[0].id) if accounts else None

        response_data = {
            "user_id": user.id,
            "email": user.email,
            "phone_number": user.phone_number,
            "name": name,
            "is_cif_completed": user.is_cif_completed,
            "is_kyc_completed": getattr(user, "is_kyc_completed", False),
            "kyc_status": kyc_status,
            "cif_status": cif_status,
            "application_status": app_status,
            "credit_account_id": credit_account_id,
            "total_credit_accounts": len(accounts),
            "total_cards": total_cards,
            "credit_accounts": [a.model_dump(mode="json") for a in account_details],
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": getattr(user, "updated_at", None),
        }

        return envelope_success(response_data)

    elif command == "all":
        if role is not None:
            role = validate_enum_case_strict(role, "role")

        query = db.query(User)

        if cif_completed is not None:
            query = query.filter(User.is_cif_completed == cif_completed)

        total = query.count()
        users = (
            query.order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        data = []
        for user in users:
            profile = db.query(CustomerProfile).filter(
                CustomerProfile.user_id == user.id
            ).first()

            name = None
            kyc_status = "NOT_STARTED"
            cif_status = "NOT_STARTED"

            if profile:
                name = (
                    f"{profile.first_name} {profile.last_name}".strip()
                    if profile.first_name
                    else user.full_name
                )
                kyc_status = profile.kyc_state.value if profile.kyc_state else "NOT_STARTED"
                cif_status = profile.customer_status or "IN_PROGRESS"
            else:
                name = user.full_name

            latest_app = (
                db.query(CreditCardApplication)
                .filter(CreditCardApplication.user_id == user.id)
                .order_by(CreditCardApplication.submitted_at.desc())
                .first()
            )
            app_status = "NOT_APPLIED"
            if latest_app and latest_app.application_status:
                app_status = getattr(
                    latest_app.application_status, "value",
                    latest_app.application_status
                )

            credit_account = db.query(CreditAccount).filter(
                CreditAccount.user_id == user.id
            ).first()
            credit_account_id = str(credit_account.id) if credit_account else None

            data.append({
                "user_id": user.id,
                "name": name,
                "email": user.email,
                "is_cif_completed": user.is_cif_completed,
                "is_kyc_completed": getattr(user, "is_kyc_completed", False),
                "kyc_status": kyc_status,
                "cif_status": cif_status,
                "application_status": app_status,
                "credit_account_id": credit_account_id,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": getattr(user, "updated_at", None),
            })

        return envelope_success({
            "items": data,
            "pagination": build_pagination(total, page, page_size),
        })
