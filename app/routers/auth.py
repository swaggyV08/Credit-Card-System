from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from datetime import datetime, timezone, timedelta
from uuid import UUID
import uuid

from app.db.session import get_db
from app.models.auth import User, AuthCredential
from app.models.customer import OTPCode, OTPPurpose, CustomerProfile
from app.models.admin import Admin
from app.schemas.auth import (
    CreateRegistrationRequest,
    VerifyRegistrationRequest,
    CreatePasswordResetRequest,
    VerifyPasswordResetRequest,
    LoginEmailRequest,
    OTPDispatcherRequest,
)
from app.schemas.admin import AdminCreate, AdminEmailLogin
from app.core.security import hash_value, verify_value, validate_password_rules
from app.core.jwt import create_access_token
from app.core.otp import generate_otp, hash_otp, verify_otp, get_expiry_time
from app.core.rbac import require, AuthenticatedPrincipal
from app.core.roles import Role
from app.schemas.base import envelope_success

# Use two routers for prefix logic
router = APIRouter(prefix="/auth", tags=["Authentication"])
admin_router = APIRouter(prefix="/admin/auth", tags=["Admin: Authentication"])


# ===================================================================
# STEP 1 — CREATE REGISTRATION (public, no auth required)
# ===================================================================
@router.post(
    "/registrations",
    status_code=status.HTTP_201_CREATED,
    summary="Step 1: Create user registration",
    description="""
Step 1 of 2 in the registration flow.
Creates a new user record with UNVERIFIED status.

The user must request and verify an OTP using:
  POST /auth/otp/{user_id}?command=generate with purpose=REGISTRATION
  POST /auth/otp/{user_id}?command=verify with purpose=REGISTRATION
""",
)
def create_registration(
    data: CreateRegistrationRequest,
    db: Session = Depends(get_db),
):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail={"code": "PASSWORD_MISMATCH", "message": "Passwords do not match"})
        
    try:
        validate_password_rules(data.password)
    except ValueError as e:
        # Extract the specialized error code if present
        err_str = str(e)
        if ":" in err_str:
            code, message = err_str.split(":", 1)
            raise HTTPException(status_code=422, detail={"code": code.strip(), "message": message.strip()})
        raise HTTPException(status_code=422, detail={"code": "INVALID_PASSWORD", "message": err_str})

    existing_user = db.execute(select(User).where(User.email == data.email)).scalar_one_or_none()
    
    if existing_user:
        if existing_user.status == "ACTIVE":
            raise HTTPException(status_code=409, detail={"code": "ALREADY_REGISTERED", "message": "Email already registered. Please login."})
        else:
            user = existing_user
            user.full_name = data.full_name
            user.country_code = data.contact.country_code
            user.phone_number = data.contact.phone_number
            
            profile = db.execute(select(CustomerProfile).where(CustomerProfile.user_id == user.id)).scalar_one_or_none()
            if profile:
                profile.date_of_birth = data.date_of_birth
            else:
                profile = CustomerProfile(user_id=user.id, date_of_birth=data.date_of_birth)
                db.add(profile)
                
            credentials = db.execute(select(AuthCredential).where(AuthCredential.user_id == user.id)).scalar_one_or_none()
            if credentials:
                credentials.password_hash = hash_value(data.password)
            else:
                credentials = AuthCredential(user_id=user.id, password_hash=hash_value(data.password))
                db.add(credentials)
            db.flush()
    else:
        user_id_str = str(uuid.uuid4())[:20]
        user = User(
            id=user_id_str,
            email=data.email,
            full_name=data.full_name,
            country_code=data.contact.country_code,
            phone_number=data.contact.phone_number,
            status="UNVERIFIED",
            is_cif_completed=False,
            is_kyc_completed=False,
        )
        db.add(user)
        db.flush()
        
        profile = CustomerProfile(
            user_id=user.id,
            date_of_birth=data.date_of_birth,
        )
        db.add(profile)
        
        credentials = AuthCredential(
            user_id=user.id,
            password_hash=hash_value(data.password),
        )
        db.add(credentials)
        db.flush()

    db.commit()
    
    return envelope_success({
        "user_id": user.id,
        "message": "Verify with OTP"
    })


@router.post(
    "/login",
    summary="Unified Login for Users and Admins",
    description="Validates email and password, returning JWT token. Requires command=USER or command=ADMIN.",
)
def unified_login(
    data: LoginEmailRequest,
    command: Literal["USER", "ADMIN"] = Query(..., description="Login context"),
    db: Session = Depends(get_db)
):
    command = command.upper().strip()

    if command == "ADMIN":
        admin = db.query(Admin).filter(Admin.email == data.email).first()
        if not admin:
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"})
            
        if not verify_value(data.password, admin.password_hash):
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"})
            
        role_value = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
        token = create_access_token({
            "sub": str(admin.id),
            "token_type": "ADMIN",
            "role": role_value,
            "email": admin.email
        })
        return envelope_success({
            "access_token": token,
            "token_type": "bearer",
            "role": role_value,
            "message": f"Welcome {role_value}: {admin.full_name}",
        })
        
    elif command == "USER":
        user = db.query(User).filter(User.email == data.email).first()
        if not user:
            # Check if this email belongs to an Admin trying to login as USER
            admin_check = db.query(Admin).filter(Admin.email == data.email).first()
            if admin_check:
                raise HTTPException(status_code=400, detail={"code": "WRONG_COMMAND_FOR_ROLE", "message": "Admins must login with command=ADMIN"})
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"})

        if user.status != "ACTIVE":
            if user.status == "UNVERIFIED":
                raise HTTPException(status_code=403, detail={"code": "ACCOUNT_NOT_VERIFIED", "message": "Account must be verified with OTP before login"})
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Account is not active"})

        credentials = db.execute(select(AuthCredential).where(AuthCredential.user_id == user.id)).scalar_one_or_none()
        if not credentials or not verify_value(data.password, credentials.password_hash):
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"})

        token = create_access_token({
            "sub": str(user.id),
            "token_type": "USER",
            "role": "USER",
            "email": user.email
        })
        
        name = f"{user.customer_profile.first_name} {user.customer_profile.last_name}" if user.customer_profile else "User"

        return envelope_success({
            "access_token": token,
            "token_type": "bearer",
            "role": "USER",
            "message": f"Welcome {name}".strip(),
        })



# ===================================================================
# PASSWORD RESET — requires pre-verified OTP
# ===================================================================
@router.patch(
    "/passwords/{country_code}/{phone_number}",
    summary="Reset password",
)
def verify_password_reset(
    country_code: str,
    phone_number: str,
    data: VerifyPasswordResetRequest,
    db: Session = Depends(get_db),
):
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail={"code": "PASSWORD_MISMATCH", "message": "Password mismatch"})

    try:
        validate_password_rules(data.new_password)
    except ValueError as e:
        err_str = str(e)
        if ":" in err_str:
            code, message = err_str.split(":", 1)
            raise HTTPException(status_code=422, detail={"code": code.strip(), "message": message.strip()})
        raise HTTPException(status_code=422, detail={"code": "INVALID_PASSWORD", "message": err_str})

    from app.core.jwt import decode_access_token
    payload = decode_access_token(data.password_reset_token)
    if payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Invalid reset token"})
        
    token_sub = payload.get("sub")
    is_admin = payload.get("is_admin", False)
    
    if is_admin:
        admin = db.query(Admin).filter(Admin.id == token_sub, Admin.country_code == country_code, Admin.phone_number == phone_number).first()
        if not admin:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Admin not found"})
        admin.password_hash = hash_value(data.new_password)
    else:
        user = db.execute(select(User).where(User.id == token_sub, User.country_code == country_code, User.phone_number == phone_number)).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found"})
            
        credentials = db.execute(select(AuthCredential).where(AuthCredential.user_id == user.id)).scalar_one_or_none()
        credentials.password_hash = hash_value(data.new_password)

    db.commit()
    return envelope_success({"message": "Password updated successfully"})


# ===================================================================
# GENERIC OTP DISPATCHER — handles generate + verify for all purposes
# ===================================================================
@router.post(
    "/otp/{user_id}",
    summary="OTP dispatcher — generate or verify",
    description="""
**Unified OTP endpoint for all OTP operations.**

Supports two commands via `?command=` query parameter:

### `command=generate`
- Dispatches a new 6-digit OTP to the user (via SMS/email).
- Invalidates any previous unused OTPs for the same purpose.
- The OTP value is **never** returned in the response.
- Supported purposes: `REGISTRATION`, `PASSWORD_RESET`, `CARD_ACTIVATION`, `KYC_VERIFICATION`.

### `command=verify`
- Verifies an OTP that was previously dispatched.
- Requires `otp` field in the request body.
- For `purpose=REGISTRATION`: on success, returns `"message": "REGISTRATION COMPLETE"` and transitions user from UNVERIFIED → ACTIVE.
- For `purpose=PASSWORD_RESET`: marks OTP as verified; use PATCH `/auth/passwords/{country_code}/{phone_number}` to set new password.

**Error Codes:**
- `422 UNPROCESSABLE` — OTP field missing, expired, or invalid.
- `404 NOT_FOUND` — User not found.

**Accessible by:** Public (no auth required).
""",
)
async def generic_otp_dispatcher(
    user_id: str,
    data: OTPDispatcherRequest,
    command: Literal["generate", "verify"] = Query(..., description="Action to perform: 'generate' or 'verify'"),
    db: Session = Depends(get_db),
):
    command = command.lower().strip()
    user = None
    admin = None
    
    try:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            user = db.execute(select(User).where((User.email == user_id) | (User.phone_number == user_id))).scalar_one_or_none()
            
        if not user:
            try:
                admin_uuid = UUID(user_id)
                admin = db.execute(select(Admin).where(Admin.id == admin_uuid)).scalar_one_or_none()
            except ValueError:
                admin = db.execute(select(Admin).where(Admin.email == user_id)).scalar_one_or_none()
    except Exception:
        pass
        
    target_entity = user or admin
    if not target_entity:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found"})
        
    is_admin = admin is not None
    target_id_str = str(target_entity.id)

    if command == "generate":
        otp = generate_otp()
        otp_hash = hash_otp(otp)
        expires_at = get_expiry_time()

        stmt = update(OTPCode).where(OTPCode.purpose == data.purpose, OTPCode.is_used == False, OTPCode.user_id == target_id_str).values(is_used=True)
        db.execute(stmt)

        otp_entry = OTPCode(
            otp_hash=otp_hash,
            purpose=data.purpose,
            expires_at=expires_at,
            user_id=target_id_str,
            email=target_entity.email,
        )
        db.add(otp_entry)
        db.commit()

        print(f"\n[DISPATCH] {data.purpose.value} OTP for {user_id}: {otp}\n")
        return envelope_success({"message": "OTP dispatched"})

    elif command == "verify":
        if not data.otp:
            raise HTTPException(status_code=422, detail={"code": "UNPROCESSABLE", "message": "Field 'otp' is mandatory for 'verify'"})

        stmt = select(OTPCode).where(
            OTPCode.purpose == data.purpose,
            OTPCode.is_used == False,
            OTPCode.user_id == target_id_str
        ).order_by(OTPCode.created_at.desc())

        otp_entry = db.execute(stmt).scalar_one_or_none()

        if not otp_entry:
            raise HTTPException(status_code=422, detail={"code": "INVALID_OTP", "message": "Invalid or expired OTP"})
            
        if otp_entry.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail={"code": "OTP_EXPIRED", "message": "OTP has expired, please request a new one"})
            
        if not verify_otp(data.otp, otp_entry.otp_hash):
            raise HTTPException(status_code=422, detail={"code": "INVALID_OTP", "message": "Invalid or expired OTP"})

        otp_entry.is_verified = True

        if data.purpose == OTPPurpose.REGISTRATION and not is_admin:
            target_entity.status = "ACTIVE"
            otp_entry.is_used = True
            db.commit()
            return envelope_success({
                "message": "REGISTRATION COMPLETE",
                "user_id": target_id_str
            })

        if data.purpose == OTPPurpose.PASSWORD_RESET:
            # Generate a 15-minute token
            reset_token = create_access_token({"sub": target_id_str, "purpose": "password_reset", "is_admin": is_admin}, expires_delta=timedelta(minutes=15))
            otp_entry.is_used = True
            db.commit()
            return envelope_success({
                "message": "OTP verified successfully",
                "password_reset_token": reset_token
            })

        db.commit()
        return envelope_success({"message": f"the {data.purpose.value.lower().replace('_', ' ')} otp is verified"})

    else:
        raise HTTPException(status_code=400, detail={"code": "BAD_REQUEST", "message": "Invalid command"})





# ===================================================================
# ADD ADMIN (CREATE)
# ===================================================================
@admin_router.post(
    "/admins",
    status_code=status.HTTP_201_CREATED,
    summary="Create admin account",
    dependencies=[Depends(require("admin:create"))]
)
def add_admin(
    data: AdminCreate,
    principal: AuthenticatedPrincipal = Depends(require("admin:create")),
    db: Session = Depends(get_db),
):
    try:
        validate_password_rules(data.password)
    except ValueError as e:
        err_str = str(e)
        if ":" in err_str:
            code, message = err_str.split(":", 1)
            raise HTTPException(status_code=422, detail={"code": code.strip(), "message": message.strip()})
        raise HTTPException(status_code=422, detail={"code": "INVALID_PASSWORD", "message": err_str})

    existing_admin = db.query(Admin).filter(Admin.email == data.email).first()
    if existing_admin:
        raise HTTPException(status_code=409, detail={"code": "ALREADY_REGISTERED", "message": "Admin with this email already exists"})

    if data.role == Role.USER:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ROLE", "message": "Cannot assign USER role to an Admin"})

    hashed_password = hash_value(data.password)

    new_admin = Admin(
        full_name=data.full_name,
        email=data.email,
        role=data.role,
        department=data.department,
        employee_id=data.employee_id,
        country_code=data.country_code,
        phone_number=data.phone_number,
        password_hash=hashed_password,
    )

    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    return envelope_success({
        "admin_id": str(new_admin.id),
        "admin": f"{new_admin.full_name} added successfully",
        "created_at": new_admin.created_at or datetime.now(timezone.utc),
        "created_by": principal.user_id,
    })
