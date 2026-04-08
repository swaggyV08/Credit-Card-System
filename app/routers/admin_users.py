"""
Admin: User Management endpoints.

Provides admin-facing endpoints to list and view detailed user data,
including CIF/KYC status, application status, credit accounts, and cards.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

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

router = APIRouter(prefix="/users", tags=["Admin: User Management"])


@router.get(
    "/",
    summary="List Users (Paginated)",
    description="""
Paginated list of all users with enriched admin-relevant data.

**Query Parameters:**
- `role`: Filter users by role. Must be full uppercase or full lowercase (e.g. 'USER' or 'user'). Mixed case is rejected.
- `cif_completed`: Filter by CIF completion status.
- `page`, `page_size`: Pagination controls.

**Response fields per user:**
`user_id`, `name`, `email`, `is_cif_completed`, `is_kyc_completed`, `application_status`, `credit_account_id`, `created_at`
""",
    dependencies=[Depends(require("user:list"))],
)
def list_users(
    role: Optional[str] = Query(None, description="Filter by role (full UPPER or lower only)"),
    cif_completed: Optional[bool] = Query(None, description="Filter by CIF completion"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("user:list")),
):
    """Paginated list of users with status data."""
    # Validate role case if provided
    if role is not None:
        role = validate_enum_case_strict(role, "role")

    query = db.query(User)

    # Apply filters
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
        # Get profile for name
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

        # Derive application_status from latest application
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

        # Get credit account ID (if exists)
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


@router.get(
    "/{user_id}",
    summary="Get User Detail",
    description="""
Retrieves comprehensive admin view of a single user.

Returns the full user profile including all linked credit accounts and
cards nested underneath. Provides a 360-degree operational view for
admin support and compliance review.

**Response fields:**
`user_id`, `email`, `phone_number`, `name`, `is_cif_completed`, `is_kyc_completed`,
`kyc_status`, `cif_status`, `application_status`, `credit_account_id`,
`total_credit_accounts`, `total_cards`, `credit_accounts`, `created_at`, `updated_at`
""",
    dependencies=[Depends(require("user:detail"))],
)
def get_user_detail(
    user_id: str,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("user:detail")),
):
    """Comprehensive admin view of a single user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppError(code="NOT_FOUND", message="User not found", http_status=404)

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.user_id == user.id
    ).first()

    # Resolve name
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

    # Application status
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

    # Credit accounts + cards
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
