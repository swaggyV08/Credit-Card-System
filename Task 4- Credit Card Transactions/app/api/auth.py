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


# ... registrations endpoints refactored ...


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


# ... password reset requests moved to generic dispatcher ...

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

    # Verification has already been done at the generic OTP dispatcher
    otp_entry = (
        db.query(OTPCode)
        .filter(
            OTPCode.user_id == user.id,
            OTPCode.purpose == OTPPurpose.PASSWORD_RESET,
            OTPCode.is_verified == True,
            OTPCode.is_used == False
        )
        .order_by(OTPCode.created_at.desc())
        .first()
    )

    if not otp_entry:
        raise HTTPException(status_code=400, detail="OTP not verified or already used.")

    credentials = db.query(AuthCredential).filter(
        AuthCredential.user_id == user.id
    ).first()

    credentials.password_hash = hash_value(data.new_password)
    otp_entry.is_used = True

    db.commit()

    return {"message": "Password updated successfully"}

# GENERIC OTP DISPATCHER
from app.schemas.auth import OTPDispatcherRequest
from fastapi import Query, Request


from typing import Union

@router.post("/otp/{user_id}")
async def generic_otp_dispatcher(
    user_id: str,
    data: OTPDispatcherRequest,
    command: str = Query(..., description="Action to perform: 'generate' or 'verify'"),
    db: Session = Depends(get_db)
):
    """
    Unified dispatcher for OTP operations.
    - `command=generate`: Creates a new OTP code and prints it to the terminal.
    - `command=verify`: Validates the provided OTP code.
    """
    command = command.lower().strip()
    
    # Resolve user context
    user = None
    registration = None
    
    if data.purpose == OTPPurpose.REGISTRATION:
        try:
            reg_uuid = UUID(user_id)
            registration = db.query(PendingRegistration).filter(PendingRegistration.id == reg_uuid).first()
        except:
             registration = db.query(PendingRegistration).filter(PendingRegistration.email == user_id).first()
             
        if not registration:
             raise HTTPException(status_code=404, detail="Registration session not found")
    else:
        try:
            target_uuid = UUID(user_id)
            user = db.query(User).filter(User.id == target_uuid).first()
        except:
            user = db.query(User).filter(
                (User.email == user_id) | (User.phone_number == user_id)
            ).first()
            
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    if command == "generate":
        otp = generate_otp()
        otp_hash = hash_otp(otp)
        expires_at = get_expiry_time()

        # Clear old unused OTPs
        filter_criteria = {
            "purpose": data.purpose,
            "is_used": False
        }
        if user:
            filter_criteria["user_id"] = user.id
        else:
            filter_criteria["email"] = registration.email

        db.query(OTPCode).filter_by(**filter_criteria).update({"is_used": True})

        otp_entry = OTPCode(
            otp_hash=otp_hash,
            purpose=data.purpose,
            expires_at=expires_at,
            user_id=user.id if user else None,
            email=registration.email if registration else None
        )
        db.add(otp_entry)
        db.commit()

        print("\n" + "="*50)
        print(f"TERMINAL OTP GENERATED")
        print(f"Identifier: {user_id}")
        print(f"Purpose:    {data.purpose.value}")
        print(f"OTP CODE:   {otp}")
        print("="*50 + "\n")
        
        return {
            "message": f"{data.purpose.value.replace('_', ' ').capitalize()} OTP is generated successfully.",
            "expires_at": expires_at.isoformat()
        }

    elif command == "verify":
        if not data.otp:
            raise HTTPException(status_code=422, detail="Field 'otp' is mandatory for 'verify'")
            
        filter_criteria = {
            "purpose": data.purpose,
            "is_used": False
        }
        if user:
            filter_criteria["user_id"] = user.id
        else:
            filter_criteria["email"] = registration.email

        otp_entry = db.query(OTPCode).filter_by(**filter_criteria).filter(
            OTPCode.expires_at > datetime.now(timezone.utc)
        ).order_by(OTPCode.created_at.desc()).first()

        if not otp_entry or not verify_otp(data.otp, otp_entry.otp_hash):
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")

        otp_entry.is_verified = True
        
        # Purpose-specific side effects
        if data.purpose == OTPPurpose.REGISTRATION:
            new_user = User(
                email=registration.email,
                country_code=registration.country_code,
                phone_number=registration.phone_number,
                is_active=True,
                is_cif_completed=False,
                is_kyc_completed=False
            )
            db.add(new_user)
            db.flush()
            
            profile = CustomerProfile(
                user_id=new_user.id,
                first_name=registration.first_name,
                last_name=registration.last_name
            )
            db.add(profile)
            
            credentials = AuthCredential(
                user_id=new_user.id,
                password_hash=hash_value(registration.password)
            )
            db.add(credentials)
            db.delete(registration)
            otp_entry.is_used = True
            db.commit()
            return {"message": "Registration successful and verified"}

        elif data.purpose == OTPPurpose.UNBLOCK:
            # Here we just mark as verified, the actual unblock happens at the cards endpoint
            # but the user said "make sure the unblock is verified"
            db.commit()
            return {"message": "the unblock otp is verified"}

        db.commit()
        return {"message": f"the {data.purpose.value.lower().replace('_', ' ')} otp is verified"}
    
    else:
        raise HTTPException(status_code=400, detail="Invalid command")
