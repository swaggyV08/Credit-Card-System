from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.api.deps import get_db
from app.models.admin import Admin
from app.schemas.admin import AdminCreate, AdminEmailLogin, TokenResponse, AdminCreationResponse
from app.core.security import hash_value, verify_value, validate_password_rules
from app.core.jwt import create_access_token
from app.core.roles import Role
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

router = APIRouter(prefix="/auth", tags=["Admin: Authentication"])


@router.post(
    "/login/email",
    response_model=TokenResponse,
    summary="Admin login via email",
    description="""
Authenticates an admin user and returns a JWT access token.

The token contains: sub (admin_id), role, jti, exp, iat, token_type=ADMIN.

Accessible by: ADMIN, MANAGER, SALES
""",
)
def login_admin_email(data: AdminEmailLogin, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.email == data.email).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_value(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    role_value = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    access_token = create_access_token({
        "sub": str(admin.id),
        "type": "ADMIN",
        "role": role_value,
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "message": f"Welcome Admin: {admin.full_name}",
        "login_timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post(
    "/login/swagger",
    response_model=TokenResponse,
    include_in_schema=False,
)
def login_admin_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Swagger UI 'Authorize' button endpoint (sends form data)."""
    admin = db.query(Admin).filter(Admin.email == form_data.username).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_value(form_data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    role_value = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    access_token = create_access_token({
        "sub": str(admin.id),
        "type": "ADMIN",
        "role": role_value,
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "message": f"Welcome Admin: {admin.full_name}",
        "login_timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post(
    "/admins",
    response_model=AdminCreationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create admin account",
    description="""
Creates a new admin user. Only ADMIN role can create other admins.

**Request body:**
- email: valid email address
- password: minimum 12 characters, bcrypt hashed
- full_name: admin's full name
- role: ADMIN | MANAGER | SALES (never USER)
- department: optional
- employee_id: optional

Accessible by: ADMIN only
""",
)
def add_admin(
    data: AdminCreate,
    principal: AuthenticatedPrincipal = Depends(require("admin:create")),
    db: Session = Depends(get_db),
):
    try:
        validate_password_rules(data.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing_admin = db.query(Admin).filter(Admin.email == data.email).first()
    if existing_admin:
        raise HTTPException(status_code=400, detail="Admin with this email already exists")

    if data.role == Role.USER:
        raise HTTPException(status_code=400, detail="Cannot assign USER role to an Admin")

    hashed_password = hash_value(data.password)

    new_admin = Admin(
        full_name=data.full_name,
        email=data.email,
        role=data.role,
        department=data.department,
        employee_id=data.employee_id,
        password_hash=hashed_password,
    )

    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    return {
        "admin": f"{new_admin.full_name} added successfully",
        "created_at": new_admin.created_at or datetime.now(timezone.utc),
        "created_by": principal.user_id,
    }
