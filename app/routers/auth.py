from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from datetime import datetime, timezone
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
from app.schemas.base import envelope_success, envelope_error, ErrorDetail

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
Creates a new user record with UNVERIFIED status and dispatches a
one-time password (OTP) to the user's registered mobile/email.

The OTP value is NEVER returned in the API response.
Registration is only considered complete after the OTP is verified
via POST /auth/otp/{user_id}?command=verify with purpose=REGISTRATION.

On successful OTP verification, the response will contain:
  "message": "REGISTRATION COMPLETE"
""",
)
def create_registration(
    data: CreateRegistrationRequest,
    db: Session = Depends(get_db),
):
    try:
        validate_password_rules(data.password)
    except ValueError as e:
        return envelope_error([ErrorDetail(code="VAL_ERROR", message=str(e), field="password")])

    existing_user = db.execute(select(User).where(User.email == data.email)).scalar_one_or_none()
    
    if existing_user:
        if existing_user.status == "ACTIVE":
            return envelope_error([ErrorDetail(code="ALREADY_REGISTERED", message="Email already registered. Please login.", field="email")])
        else:
            user = existing_user
            user.country_code = data.contact.country_code
            user.phone_number = data.contact.phone_number
            
            profile = db.execute(select(CustomerProfile).where(CustomerProfile.user_id == user.id)).scalar_one_or_none()
            if profile:
                profile.first_name = data.name.first_name
                profile.last_name = data.name.last_name
            else:
                profile = CustomerProfile(user_id=user.id, first_name=data.name.first_name, last_name=data.name.last_name)
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
            first_name=data.name.first_name,
            last_name=data.name.last_name,
        )
        db.add(profile)
        
        credentials = AuthCredential(
            user_id=user.id,
            password_hash=hash_value(data.password),
        )
        db.add(credentials)
        db.flush()

    # OTP Generation and Dispatch
    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at = get_expiry_time()

    # Clear old unused REGISTRATION OTPs
    stmt = update(OTPCode).where(OTPCode.user_id == user.id, OTPCode.purpose == OTPPurpose.REGISTRATION, OTPCode.is_used == False).values(is_used=True)
    db.execute(stmt)

    otp_entry = OTPCode(
        otp_hash=otp_hash,
        purpose=OTPPurpose.REGISTRATION,
        expires_at=expires_at,
        user_id=user.id,
        email=user.email,
    )
    db.add(otp_entry)
    db.commit()
    
    # Internal dispatch log - simulate out of band dispatch
    print(f"\n[DISPATCH] Registration OTP for {data.email}: {otp}\n")

    return envelope_success({
        "user_id": user.id,
        "message": "Verify OTP sent"
    })


# ===================================================================
# LOGIN (EMAIL) — public, no auth required
# ===================================================================
@router.post(
    "/sessions/email",
    summary="Login via email",
    description="Authenticates a user via email/password and returns a JWT access token.",
)
def login_email(data: LoginEmailRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == data.email)).scalar_one_or_none()
    if not user or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Invalid email or password"})

    credentials = db.execute(select(AuthCredential).where(AuthCredential.user_id == user.id)).scalar_one_or_none()

    if not credentials or not verify_value(data.password, credentials.password_hash):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Invalid password"})

    token = create_access_token({
        "sub": str(user.id),
        "type": "USER",
        "role": "USER",
    })

    name = f"{user.customer_profile.first_name} {user.customer_profile.last_name}" if user.customer_profile else "User"

    return envelope_success({
        "access_token": token,
        "message": f"Welcome to Zbanque {name}".strip(),
        "is_cif_completed": user.is_cif_completed,
        "is_kyc_completed": user.is_kyc_completed,
        "login_timestamp": datetime.now(timezone.utc).isoformat(),
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
        return envelope_error([ErrorDetail(code="BAD_REQUEST", message="Password mismatch")])

    try:
        validate_password_rules(data.new_password)
    except ValueError as e:
        return envelope_error([ErrorDetail(code="VAL_ERROR", message=str(e), field="password")])

    user = db.execute(select(User).where(User.country_code == country_code, User.phone_number == phone_number)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found"})

    otp_entry = db.execute(
        select(OTPCode)
        .where(
            OTPCode.user_id == user.id,
            OTPCode.purpose == OTPPurpose.PASSWORD_RESET,
            OTPCode.is_verified == True,
            OTPCode.is_used == False,
        )
        .order_by(OTPCode.created_at.desc())
    ).scalar_one_or_none()

    if not otp_entry:
        return envelope_error([ErrorDetail(code="OTP_ERROR", message="OTP not verified or already used")])

    credentials = db.execute(select(AuthCredential).where(AuthCredential.user_id == user.id)).scalar_one_or_none()
    credentials.password_hash = hash_value(data.new_password)
    otp_entry.is_used = True
    db.commit()

    return envelope_success({"message": "Password updated successfully"})


# ===================================================================
# GENERIC OTP DISPATCHER — handles generate + verify for all purposes
# ===================================================================
@router.post(
    "/otp/{user_id}",
    summary="OTP dispatcher",
    description="Unified dispatcher for OTP operations.",
)
async def generic_otp_dispatcher(
    user_id: str,
    data: OTPDispatcherRequest,
    command: Literal["generate", "verify"] = Query(..., description="Action to perform: 'generate' or 'verify'"),
    db: Session = Depends(get_db),
):
    command = command.lower().strip()
    user = None
    
    try:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            user = db.execute(select(User).where((User.email == user_id) | (User.phone_number == user_id))).scalar_one_or_none()
    except Exception:
        pass
        
    if not user:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found"})

    if command == "generate":
        otp = generate_otp()
        otp_hash = hash_otp(otp)
        expires_at = get_expiry_time()

        stmt = update(OTPCode).where(OTPCode.purpose == data.purpose, OTPCode.is_used == False, OTPCode.user_id == user.id).values(is_used=True)
        db.execute(stmt)

        otp_entry = OTPCode(
            otp_hash=otp_hash,
            purpose=data.purpose,
            expires_at=expires_at,
            user_id=user.id,
            email=user.email,
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
            OTPCode.user_id == user.id
        ).order_by(OTPCode.created_at.desc())

        otp_entry = db.execute(stmt).scalar_one_or_none()

        if not otp_entry:
            raise HTTPException(status_code=422, detail={"code": "UNPROCESSABLE", "message": "Invalid or expired OTP"})
            
        if otp_entry.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail={"code": "UNPROCESSABLE", "message": "OTP has expired, please request a new one"})
            
        if not verify_otp(data.otp, otp_entry.otp_hash):
            raise HTTPException(status_code=422, detail={"code": "UNPROCESSABLE", "message": "Invalid or expired OTP"})

        otp_entry.is_verified = True

        if data.purpose == OTPPurpose.REGISTRATION:
            user.status = "ACTIVE"
            otp_entry.is_used = True
            db.commit()
            return envelope_success({
                "message": "REGISTRATION COMPLETE",
                "user_id": user.id
            })

        db.commit()
        return envelope_success({"message": f"the {data.purpose.value.lower().replace('_', ' ')} otp is verified"})

    else:
        raise HTTPException(status_code=400, detail={"code": "BAD_REQUEST", "message": "Invalid command"})


# ===================================================================
# ADMIN LOGIN (EMAIL)
# ===================================================================
@admin_router.post(
    "/login/email",
    summary="Admin login via email",
    description="Authenticates an admin user and returns a JWT access token.",
)
def login_admin_email(data: AdminEmailLogin, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.email == data.email).first()
    if not admin or not verify_value(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Invalid email or password"})

    role_value = admin.role.value if hasattr(admin.role, "value") else str(admin.role)
    access_token = create_access_token({
        "sub": str(admin.id),
        "type": "ADMIN",
        "role": role_value,
    })
    
    return envelope_success({
        "access_token": access_token,
        "token_type": "bearer",
        "message": f"Welcome Admin: {admin.full_name}",
        "login_timestamp": datetime.now(timezone.utc).isoformat(),
    })


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
        return envelope_error([ErrorDetail(code="VAL_ERROR", message=str(e), field="password")])

    existing_admin = db.query(Admin).filter(Admin.email == data.email).first()
    if existing_admin:
        return envelope_error([ErrorDetail(code="DUPLICATE", message="Admin with this email already exists")])

    if data.role == Role.USER:
        return envelope_error([ErrorDetail(code="INVALID_ROLE", message="Cannot assign USER role to an Admin")])

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

    return envelope_success({
        "admin": f"{new_admin.full_name} added successfully",
        "created_at": new_admin.created_at or datetime.now(timezone.utc),
        "created_by": principal.user_id,
    })
