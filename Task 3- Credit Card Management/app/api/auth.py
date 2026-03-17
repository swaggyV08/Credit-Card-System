from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime,timezone
from uuid import UUID

from app.db.session import get_db
from app.models.auth import User, AuthCredential
from app.models.pending_registration import PendingRegistration
from app.models.customer import OTPCode, OTPPurpose, CustomerProfile
from app.schemas.auth import (
    CreateRegistrationRequest,
    VerifyRegistrationRequest,
    CreatePasswordResetRequest,
    VerifyPasswordResetRequest,
    LoginEmailRequest,
    AuthResponse
)
from app.core.security import (
    hash_value,
    verify_value,
    validate_password_rules
)
from app.core.jwt import create_access_token
from app.core.otp import generate_otp, hash_otp, verify_otp, get_expiry_time

router = APIRouter(prefix="/auth", tags=["Authentication"])


# CREATE REGISTRATION
@router.post("/registrations", status_code=201)
def create_registration(
    data: CreateRegistrationRequest,
    db: Session = Depends(get_db)
):

    try:
        validate_password_rules(data.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        return {
            "registration_id": "ALREADY_REGISTERED",
            "message": "Email already registered. Please login.",
        }

    # IDEMPOTENCY: Check for existing pending registration
    registration = db.query(PendingRegistration).filter(PendingRegistration.email == data.email).first()
    
    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at = get_expiry_time()

    if registration:
        # Update existing registration (idempotent retry)
        registration.first_name = data.name.first_name
        registration.last_name = data.name.last_name
        registration.phone_number = data.contact.phone_number
        registration.password = data.password
        registration.otp_hash = otp_hash
        registration.expires_at = expires_at
    else:
        registration = PendingRegistration(
            first_name=data.name.first_name,
            last_name=data.name.last_name,
            suffix=data.name.suffix.value if data.name.suffix else None,
            email=data.email,
            country_code=data.contact.country_code,
            phone_number=data.contact.phone_number,
            password=data.password,
            otp_hash=otp_hash,
            expires_at=expires_at,
        )
        db.add(registration)
    db.commit()
    db.refresh(registration)

    print(f"Registration OTP for {data.email}: {otp}")

    return {
        "registration_id": str(registration.id),
        "message": "OTP sent",
    }


# VERIFY REGISTRATION
@router.patch("/registrations")
def verify_registration(
    data: VerifyRegistrationRequest,
    command: str,
    db: Session = Depends(get_db)
):
    if command != "verify":
        raise HTTPException(status_code=400, detail="Invalid command")

    # IDEMPOTENCY: Check if user already exists (maybe verified by another request)
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        return {"message": "Registration successful"}

    registration = (
        db.query(PendingRegistration)
        .filter(PendingRegistration.email == data.email)
        .first()
    )

    if not registration:
        raise HTTPException(status_code=404, detail="Invalid registration session")

    from datetime import timezone

    if registration.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")

    if not verify_otp(data.otp, registration.otp_hash):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    user = User(
        email=registration.email,
        country_code=registration.country_code,
        phone_number=registration.phone_number,
        is_active=True,
        is_cif_completed=False,
        is_kyc_completed=False
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Initialize CustomerProfile with names so they are not lost
    profile = CustomerProfile(
        user_id=user.id,
        first_name=registration.first_name,
        last_name=registration.last_name,
        suffix=registration.suffix
    )
    db.add(profile)

    credentials = AuthCredential(
        user_id=user.id,
        password_hash=hash_value(registration.password)
    )

    db.add(credentials)
    db.delete(registration)
    db.commit()

    return {"message": "Registration successful"}


# LOGIN (EMAIL)
@router.post("/sessions/email", response_model=AuthResponse)
def login_email(data: LoginEmailRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    credentials = db.query(AuthCredential).filter(
        AuthCredential.user_id == user.id
    ).first()

    if not verify_value(data.password, credentials.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_access_token({"sub": str(user.id)})

    name = f"{user.customer_profile.first_name} {user.customer_profile.last_name}" if user.customer_profile else "User"

    is_kyc_completed = user.is_kyc_completed if user.is_kyc_completed is not None else False

    from app.admin.models.card_issuance import CreditCardApplication
    app = db.query(CreditCardApplication).filter(CreditCardApplication.user_id == user.id).first()
    app_status = getattr(app.application_status, 'value', app.application_status) if app and app.application_status else None

    return {
        "access_token": token,
        "message": f"Welcome to Zbanque {name}".strip(),
        "is_cif_completed": user.is_cif_completed,
        "is_kyc_completed": is_kyc_completed,
        "application_status": app_status,
        "login_timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/password-reset-requests")
def create_password_reset(
    data: CreatePasswordResetRequest,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(
            User.country_code == data.contact.country_code,
            User.phone_number == data.contact.phone_number
        )
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # IDEMPOTENCY: Check for active unused OTP
    existing_otp = db.query(OTPCode).filter(
        OTPCode.user_id == user.id,
        OTPCode.purpose == OTPPurpose.PASSWORD_RESET,
        OTPCode.is_used == False,
        OTPCode.expires_at > datetime.now(timezone.utc)
    ).first()

    if existing_otp:
        # Re-send/Return existing
        return {"message": "OTP already sent. Please check your messages."}

    otp = generate_otp()

    otp_entry = OTPCode(
        user_id=user.id,
        otp_hash=hash_otp(otp),
        purpose=OTPPurpose.PASSWORD_RESET,
        expires_at=get_expiry_time()
    )

    db.add(otp_entry)
    db.commit()

    print("Password Reset OTP:", otp)

    return {"message": "OTP sent"}

@router.patch("/passwords/{country_code}/{phone_number}")
def verify_password_reset(
    country_code: str,
    phone_number: str,
    data: VerifyPasswordResetRequest,
    db: Session = Depends(get_db)
):

    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Password mismatch")

    validate_password_rules(data.new_password)

    user = (
        db.query(User)
        .filter(
            User.country_code == country_code,
            User.phone_number == phone_number
        )
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp_entry = (
        db.query(OTPCode)
        .filter(
            OTPCode.user_id == user.id,
            OTPCode.purpose == OTPPurpose.PASSWORD_RESET,
            OTPCode.is_used == False
        )
        .order_by(OTPCode.created_at.desc())
        .first()
    )

    if not otp_entry:
        raise HTTPException(status_code=400, detail="OTP not found")

    if otp_entry.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")

    if not verify_otp(data.otp, otp_entry.otp_hash):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    credentials = db.query(AuthCredential).filter(
        AuthCredential.user_id == user.id
    ).first()

    credentials.password_hash = hash_value(data.new_password)
    otp_entry.is_used = True

    db.commit()

    return {"message": "Password updated successfully"}

# GENERIC OTP DISPATCHER
from app.schemas.auth import OTPGenerateRequest, OTPVerifyRequest
from fastapi import Query, Request


@router.post("/otp/generate/{linkage_id}")
async def create_otp(
    linkage_id: UUID,
    data: OTPGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Creates a new OTP code tied to a linkage_id and prints it to the terminal.
    """
    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at = get_expiry_time()

    # Clear old unused OTPs for the same purpose and linkage_id
    db.query(OTPCode).filter(
        OTPCode.purpose == data.purpose,
        OTPCode.linkage_id == linkage_id,
        OTPCode.is_used == False
    ).update({"is_used": True})

    otp_entry = OTPCode(
        otp_hash=otp_hash,
        purpose=data.purpose,
        linkage_id=linkage_id,
        expires_at=expires_at,
        user_id=None,
        email=None,
        phone_number=None
    )
    db.add(otp_entry)
    db.commit()

    # PRINT TO TERMINAL
    print("\n" + "="*50)
    print(f"TERMINAL OTP GENERATED")
    print(f"Linkage ID: {linkage_id}")
    print(f"Purpose:    {data.purpose.value}")
    print(f"OTP CODE:   {otp}")
    print("="*50 + "\n")
    
    purpose_msg = data.purpose.value.lower().replace("_", " ")
    return {
        "message": f"{purpose_msg.capitalize()} OTP is generated successfully.",
        "linkage_id": linkage_id,
        "expires_at": expires_at.isoformat()
    }


@router.post("/otp/verify/{linkage_id}")
async def verify_otp_endpoint(
    linkage_id: UUID,
    data: OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    """
    Validates the provided OTP code against the active linkage session.
    """
    otp_entry = db.query(OTPCode).filter(
        OTPCode.purpose == data.purpose,
        OTPCode.linkage_id == linkage_id,
        OTPCode.is_used == False,
        OTPCode.expires_at > datetime.now(timezone.utc)
    ).order_by(OTPCode.created_at.desc()).first()

    if not otp_entry or not verify_otp(data.otp, otp_entry.otp_hash):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP (Linkage Mismatch or Wrong Code)")

    otp_entry.is_verified = True 
    db.commit()

    purpose_msg = data.purpose.value.lower().replace("_", " ")
    return {
        "message": f"the {purpose_msg} otp is verified", 
        "linkage_id": linkage_id
    }
