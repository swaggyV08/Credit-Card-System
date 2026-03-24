from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, Query
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timezone, date, timedelta
import os
import shutil
from uuid import UUID
from app.core.jwt import decode_access_token
from app.api.deps import get_db, get_current_authenticated_user
from app.models.auth import User
from app.schemas.auth import (
    PersonalDetailsSchema,
    ResidentialDetailsSchema,
    FinancialDetailsSchema,
    EmploymentDetailsSchema,
    FATCADetailsSchema,
    CIFSummaryResponse,
    CifSummaryBasicProfile,
    CifSummaryContactSummary,
    CifSummaryAddressSummary,
    CifSummaryRegulatory,
    UserProfileResponse
)
from app.admin.schemas.card_issuance import (
    CreditAccountResponse, CardResponse, CustomerCardResponse, CardActivationRequest, SetPinRequest
)
from app.core.identity_helper import update_user_identity
from app.core.otp import generate_otp, hash_otp, verify_otp, get_expiry_time
from app.models.customer import (
    CustomerProfile,
    CustomerAddress,
    EmploymentDetail,
    FinancialInformation,
    KYCDocumentSubmission,
    KYCOTPVerification,
    FATCADeclaration
)
from app.admin.models.card_issuance import CreditAccount, Card
from app.admin.models.card_product import CardProductCore
from app.models.enums import KYCState,Country, PrimaryJurisdiction, DocumentCategory, KYCVerificationStatus, CardStatus
from app.core.security import hash_value
from app.core.compliance import BLACKLISTED_COUNTRIES
from app.admin.models.card_product import CardBillingConfiguration
from app.admin.schemas.card_issuance import CustomerCreditAccountResponse
from app.services.card_management_service import CardManagementService
from typing import Optional

router = APIRouter(prefix="/customers", tags=["Customer CIF"])
# HELPER — GET CURRENT USER
def get_current_user(db: Session, user_id):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# HELPER — AGE CHECK
def calculate_age(dob: date):
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

# GENERATE USER ID
def generate_user_id(db: Session):
    last_user = db.query(User)\
        .filter(User.id.like("ZBNQ%"))\
        .order_by(User.id.desc())\
        .first()

    if not last_user:
        return "ZBNQ00000001"

    last_number = int(last_user.id.replace("ZBNQ", ""))
    new_number = last_number + 1

    return f"ZBNQ{new_number:08d}"


from app.schemas.auth import UnifiedCIFRequest

# ==========================================
# UNIFIED CIF ENDPOINT
# ==========================================
@router.put("/cif")
def save_cif_unified(
    request: UnifiedCIFRequest,
    command: str = Query(
        ..., 
        description=(
            "Action to perform on the CIF profile.\n"
            "- 'personal_details': Updates personal data. Requires Personal_details block.\n"
            "- 'resedential_details': Updates residential data. Requires Resedential_details block.\n"
            "- 'employment_details': Updates employment data. Requires Employment_details block.\n"
            "- 'financial_details': Updates financial data. Requires Financial_details block.\n"
            "- 'fatca_details': Updates FATCA data. Requires Fatca_details block."
        )
    ),
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    A unified endpoint for capturing Customer Information File (CIF) data in precise, sequential stages.
    
    ### How it Works
    You must use the `command` query parameter to declare which lifecycle stage you are updating.
    The payload must strictly contain only the object associated with the command. If other data is sent,
    validation blocks the request.
    
    ### Required Chronological Order
    1. `personal_details`
    2. `resedential_details`
    3. `employment_details`
    4. `financial_details`
    5. `fatca_details`
    """
    if user.is_cif_completed:
        raise HTTPException(status_code=403, detail="cif already completed")

    cmd = command.lower().strip()
    valid_commands = [
        "personal_details",
        "resedential_details",
        "employment_details",
        "financial_details",
        "fatca_details"
    ]

    if cmd not in valid_commands:
        raise HTTPException(status_code=400, detail="Invalid command")

    has_personal = request.Personal_details is not None
    has_residential = request.Resedential_details is not None
    has_employment = request.Employment_details is not None
    has_financial = request.Financial_details is not None
    has_fatca = request.Fatca_details is not None

    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()

    if cmd == "personal_details":
        if has_residential or has_employment or has_financial or has_fatca:
            raise HTTPException(status_code=422, detail="only personal details needs to be entered ")
        if not has_personal:
            raise HTTPException(status_code=422, detail="Personal_details is required")

        if profile and profile.nationality:
            raise HTTPException(status_code=400, detail="already entered")
        
        if not profile:
            profile = CustomerProfile(user_id=user.id)
            db.add(profile)

        data = request.Personal_details
        dob = data.date_of_birth.to_date()
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        if age < 18:
            raise HTTPException(status_code=403, detail="Customer must be at least 18 years old")
        if age > 100:
            raise HTTPException(status_code=400, detail="Invalid age provided")
            
        if data.country_of_residence == Country.PAKISTAN or data.nationality == Country.PAKISTAN:
            raise HTTPException(
                status_code=403,
                detail="You country residents arent allowed to create a account in my bank"
            )

        if data.country_of_residence.value in BLACKLISTED_COUNTRIES:
            raise HTTPException(status_code=403, detail="Country not eligible")

        profile.nationality = data.nationality
        profile.dual_citizenship = data.dual_citizenship
        profile.country_of_residence = data.country_of_residence
        profile.date_of_birth = dob
        profile.gender = data.gender
        profile.marital_status = data.marital_status
        profile.preferred_language = data.preferred_language
        
        if data.nationality == Country.USA or data.country_of_residence == Country.USA:
            profile.fatca_required = True
        else:
            profile.fatca_required = False

        db.commit()
        return {"message": "Personal details saved"}

    elif cmd == "resedential_details":
        if has_personal or has_employment or has_financial or has_fatca:
            raise HTTPException(status_code=422, detail="only resedential details needs to be entered ")
        if not has_residential:
            raise HTTPException(status_code=422, detail="Resedential_details is required")

        if not profile:
            raise HTTPException(status_code=400, detail="enter personal details first")

        addr_exists = db.query(CustomerAddress).filter(CustomerAddress.customer_profile_id == profile.id).first()
        if addr_exists:
            raise HTTPException(status_code=400, detail="already entered")

        data = request.Resedential_details
        for addr in data.addresses:
            new_address = CustomerAddress(
                customer_profile_id=profile.id,
                address_type=addr.type,
                residence_type=addr.residence_type,
                years_at_address=addr.years_at_address,
                address_line_1=addr.line1,
                address_line_2=addr.line2,
                city=addr.city,
                state=addr.state,
                postal_code=addr.pincode,
                country=addr.country,
                is_kyc_verified=addr.is_kyc_verified,
                same_as_current=addr.same_as_current,
            )
            db.add(new_address)
        db.commit()
        return {"message": "Resedential details saved"}

    elif cmd == "employment_details":
        if has_personal or has_residential or has_financial or has_fatca:
            raise HTTPException(status_code=422, detail="only employment details needs to be entered ")
        if not has_employment:
            raise HTTPException(status_code=422, detail="Employment_details is required")

        if not profile:
            raise HTTPException(status_code=400, detail="enter personal details first")

        addr_exists = db.query(CustomerAddress).filter(CustomerAddress.customer_profile_id == profile.id).first()
        if not addr_exists:
            raise HTTPException(status_code=400, detail="enter residential details first")

        employment = db.query(EmploymentDetail).filter(EmploymentDetail.customer_profile_id == profile.id).first()
        if employment:
            raise HTTPException(status_code=400, detail="already entered")

        employment = EmploymentDetail(customer_profile_id=profile.id)
        db.add(employment)

        data = request.Employment_details
        employment.employment_type = data.employment_type
        if data.organisation_name is not None:
            employment.organisation_name = data.organisation_name
        if data.designation is not None:
            employment.designation = data.designation
        employment.annual_income = data.annual_income

        db.commit()
        return {"message": "Employment details saved"}

    elif cmd == "financial_details":
        if has_personal or has_residential or has_employment or has_fatca:
            raise HTTPException(status_code=422, detail="only financial details needs to be entered ")
        if not has_financial:
            raise HTTPException(status_code=422, detail="Financial_details is required")

        if not profile:
            raise HTTPException(status_code=400, detail="enter personal details first")

        emp_exists = db.query(EmploymentDetail).filter(EmploymentDetail.customer_profile_id == profile.id).first()
        if not emp_exists:
            raise HTTPException(status_code=400, detail="enter employment details first")

        financial = db.query(FinancialInformation).filter(FinancialInformation.customer_profile_id == profile.id).first()
        if financial:
            raise HTTPException(status_code=400, detail="already entered")

        financial = FinancialInformation(customer_profile_id=profile.id)
        db.add(financial)

        data = request.Financial_details
        financial.net_annual_income = data.net_annual_income
        financial.monthly_income = data.monthly_income
        financial.other_income = data.other_income
        financial.housing_payment = data.housing_payment
        financial.other_obligations = data.other_obligations

        db.commit()
        return {"message": "Financial details saved"}

    elif cmd == "fatca_details":
        if has_personal or has_residential or has_employment or has_financial:
            raise HTTPException(status_code=422, detail="only fatca details needs to be entered ")
        if not has_fatca:
            raise HTTPException(status_code=422, detail="Fatca_details is required")

        if not profile:
            raise HTTPException(status_code=400, detail="enter personal details first")

        fin_exists = db.query(FinancialInformation).filter(FinancialInformation.customer_profile_id == profile.id).first()
        if not fin_exists:
            raise HTTPException(status_code=400, detail="enter financial details first")

        fatca = db.query(FATCADeclaration).filter(FATCADeclaration.customer_profile_id == profile.id).first()
        if fatca:
             raise HTTPException(status_code=400, detail="already entered")

        fatca = FATCADeclaration(customer_profile_id=profile.id)
        db.add(fatca)

        data = request.Fatca_details
        fatca.us_citizen = data.us_citizen
        fatca.us_tax_resident = data.us_tax_resident
        fatca.us_tin = data.us_tin

        db.commit()
        return {"message": "FATCA details saved"}


# STAGE 1.5 - CIF SUMMARY
@router.get("/cif/summary", response_model=CIFSummaryResponse)
def get_cif_summary(
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Personal details missing")

    addresses = db.query(CustomerAddress).filter(CustomerAddress.customer_profile_id == profile.id).all()
    employment = db.query(EmploymentDetail).filter(EmploymentDetail.customer_profile_id == profile.id).first()
    financial = db.query(FinancialInformation).filter(FinancialInformation.customer_profile_id == profile.id).first()
    fatca = db.query(FATCADeclaration).filter(FATCADeclaration.customer_profile_id == profile.id).first()
    kyc_records = db.query(KYCDocumentSubmission).filter(KYCDocumentSubmission.kyc_profile_id == profile.id).all()

    pan_last4, aadhaar_last4, ssn_last4 = None, None, None
    for kyc in kyc_records:
        if kyc.document_type == "PAN":
            pan_last4 = "****"
        elif kyc.document_type == "AADHAAR":
            aadhaar_last4 = "****"
        elif kyc.document_type == "SSN":
            ssn_last4 = "****"

    personal_data = CifSummaryBasicProfile(
        full_name=f"{profile.first_name} {profile.last_name}".strip() if profile.first_name else None,
        date_of_birth=profile.date_of_birth,
        gender=profile.gender.value if profile.gender else None,
        nationality=profile.nationality.value if profile.nationality else None
    )

    email_masked = f"{user.email[:2]}****@{user.email.split('@')[-1]}" if "@" in user.email else "****"
    mobile_last4 = user.phone_number[-4:] if user.phone_number and len(user.phone_number) >= 4 else "****"

    contact = CifSummaryContactSummary(
        mobile=f"XXXX{mobile_last4}",
        email=email_masked
    )

    address_summary = None
    current_address = next((addr for addr in addresses if (hasattr(addr.address_type, 'value') and addr.address_type.value == "CURRENT") or getattr(addr, 'address_type', None) == "CURRENT"), None)
    if current_address:
        address_summary = CifSummaryAddressSummary(
            current_city=current_address.city,
            country=current_address.country.value if hasattr(current_address.country, 'value') else getattr(current_address, 'country', None),
            kyc_verified=current_address.is_kyc_verified
        )

    fatcas = "US_PERSON" if fatca and (fatca.us_citizen or fatca.us_tax_resident) else "NON_US_PERSON"

    regulatory = CifSummaryRegulatory(
        fatca_status=fatcas,
        us_citizen=fatca.us_citizen if fatca else None,
        us_tax_resident=fatca.us_tax_resident if fatca else None,
        us_tin=fatca.us_tin if fatca else None
    )

    return CIFSummaryResponse(
        user_id=user.id or "PENDING_SUBMIT",
        customer_type="INDIVIDUAL",
        customer_status=profile.customer_status,
        kyc_status=profile.kyc_state.value if profile.kyc_state else "NOT_STARTED",
        risk_category="HIGH" if profile.high_risk_flag else "LOW",
        basic_profile=personal_data,
        contact_summary=contact,
        address_summary=address_summary,
        employment_details=employment,
        financial_information=financial,
        regulatory_flags=regulatory
    )

@router.post("/cif")
def submit_cif(
    command: str,
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    if command != "submit":
        raise HTTPException(status_code=400, detail="Invalid command")

    if user.is_cif_completed:
        raise HTTPException(status_code=403, detail="cif already completed")


    profile = db.query(CustomerProfile).filter(
        CustomerProfile.user_id == user.id
    ).first()

    if not profile:
        raise HTTPException(status_code=400, detail="Personal details missing")

    employment = db.query(EmploymentDetail).filter(
        EmploymentDetail.customer_profile_id == profile.id
    ).first()

    financial = db.query(FinancialInformation).filter(
        FinancialInformation.customer_profile_id == profile.id
    ).first()

    fatca = db.query(FATCADeclaration).filter(
        FATCADeclaration.customer_profile_id == profile.id
    ).first()

    if not employment or not financial or not fatca:
        raise HTTPException(status_code=400, detail="Complete all CIF sections")

    # Generate NEW User ID in ZBNQ format
    old_user_id = user.id
    new_user_id = generate_user_id(db)

    # Mark CIF completed
    user.is_cif_completed = True
    profile.customer_status = "ACTIVE"
    
    # Update all table references to use the new identity
    update_user_identity(db, old_user_id, new_user_id)

    db.commit()

    return {
        "message": "CIF Submitted Successfully",
        "user_id": new_user_id
    }



@router.post("/kyc")
def conduct_kyc(
    command: str,
    document_type: str = Depends(lambda document_type: document_type),
    document_number: str = Depends(lambda document_number: document_number),
    file: UploadFile = File(...),
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    if not user.is_cif_completed:
        raise HTTPException(
            status_code=403,
            detail="Complete CIF before starting KYC"
        )
    if user.is_kyc_completed:
        raise HTTPException(
            status_code=403,
            detail="kyc already completed"
        )
    
    if command != "upload":
        raise HTTPException(status_code=400, detail="Invalid command. Use 'upload' to start KYC.")

    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not found. Complete personal details first.")

    valid_doc_types = ["PAN", "AADHAAR", "PASSPORT", "VOTER_ID", "DRIVING_LICENSE"]
    doc_type_upper = document_type.upper()
    if doc_type_upper not in valid_doc_types:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Allowed: {valid_doc_types}")

    # IDEMPOTENCY: Check for existing submission for this document
    hashed_number = hash_value(document_number)
    existing_sub = db.query(KYCDocumentSubmission).filter(
        KYCDocumentSubmission.kyc_profile_id == profile.id,
        KYCDocumentSubmission.document_reference_token == hashed_number
    ).first()

    if existing_sub:
        # Check if it's already verified or pending verification
        if existing_sub.verification_status == KYCVerificationStatus.VERIFIED or user.is_kyc_completed:
             return {
                "submission_id": str(existing_sub.id),
                "status": "ALREADY_COMPLETED",
                "message": "This document has already been verified."
            }
        
        # If pending OTP, return existing
        existing_otp = db.query(KYCOTPVerification).filter(
            KYCOTPVerification.document_submission_id == existing_sub.id,
            KYCOTPVerification.is_verified == False,
            KYCOTPVerification.expires_at > datetime.now(timezone.utc)
        ).first()

        if existing_otp:
             return {
                "submission_id": str(existing_sub.id),
                "status": "OTP_REQUIRED",
                "message": "An active verification is already in progress for this document."
            }

    # Validate file size (limit 5MB)
    file_size_limit = 5 * 1024 * 1024
    file.file.seek(0, 2)
    if file.file.tell() > file_size_limit:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")
    file.file.seek(0)
    
    valid_extensions = ["jpg", "jpeg", "png", "pdf"]
    ext = file.filename.split(".")[-1].lower()
    if ext not in valid_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {valid_extensions}")

    # Process File
    upload_dir = os.path.join(os.getcwd(), "uploads", "kyc", str(user.id))
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    hashed_number = hash_value(document_number)
    masked_number = f"XXXX-XXXX-{document_number[-4:]}" if len(document_number) >= 4 else "XXXX"

    submission = KYCDocumentSubmission(
        kyc_profile_id=profile.id,
        document_category=DocumentCategory.IDENTITY_PROOF,
        document_type=document_type.upper(),
        document_reference_masked=masked_number,
        document_reference_token=hashed_number,
        s3_file_locator=file_path
    )
    db.add(submission)
    db.flush()

    # ... (file processing logic remains) ...
    
    # Mark KYC completed immediately as per new requirement
    user.is_kyc_completed = True
    profile.kyc_state = KYCState.COMPLETED

    # Auto-transition credit card applications
    from app.admin.models.card_issuance import CreditCardApplication
    from app.models.enums import ApplicationStatus
    
    submitted_apps = db.query(CreditCardApplication).filter(
        CreditCardApplication.user_id == user.id,
        CreditCardApplication.application_status == ApplicationStatus.SUBMITTED
    ).all()
    
    for app in submitted_apps:
        app.application_status = ApplicationStatus.KYC_REVIEW

    db.commit()

    return {
        "message": "KYC SUBMITTED"
    }

# ... KYC refactored ...

# ... verify_kyc_document removed ...

# STAGE 5 — CONSOLIDATED CUSTOMER DATA
from typing import Union, List

@router.get("/{credit_account_id}", response_model=Union[UserProfileResponse, List[CustomerCardResponse], CustomerCreditAccountResponse])
def get_customer_data(
    credit_account_id: UUID,
    command: str = Query(..., description="commands: credit_account, credit_card, profile"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """
    Consolidated GET endpoint to retrieve customer data.
    """
    # 1. Verify account ownership
    account = db.query(CreditAccount).filter(
        CreditAccount.id == credit_account_id,
        CreditAccount.user_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=403, 
            detail="Access Denied: This credit account does not belong to you or does not exist."
        )

    if command == "profile":
        profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == current_user.id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Customer Profile not found.")
        
        return UserProfileResponse(
            user_id=current_user.id,
            email=current_user.email,
            phone_number=current_user.phone_number,
            is_cif_completed=current_user.is_cif_completed,
            is_kyc_completed=current_user.is_kyc_completed,
            first_name=profile.first_name,
            last_name=profile.last_name,
            date_of_birth=profile.date_of_birth,
            kyc_state=profile.kyc_state
        )

    elif command == "credit_card":
        # ALL cards belonging to the user
        cards = db.query(Card).join(CreditAccount).filter(CreditAccount.user_id == current_user.id).all()
        return [
            CustomerCardResponse(
                id=c.id,
                card_readable_id=c.readable_id,
                card_type=c.card_type,
                pan_masked=c.pan_masked,
                expiry_date_masked=c.expiry_date_masked,
                cvv_masked=c.cvv_masked,
                card_status=c.card_status,
                issued_at=c.issued_at,
                international_usage_enabled=c.international_usage_enabled,
                ecommerce_enabled=c.ecommerce_enabled,
                atm_enabled=c.atm_enabled
            ) for c in cards
        ]

    elif command == "credit_account":
        # Details for the specific credit account in the path
        return CustomerCreditAccountResponse(
            credit_account_id=account.id,
            user_id=account.user_id,
            credit_limit=account.credit_limit,
            available_limit=account.available_limit,
            outstanding_amount=account.outstanding_amount,
            account_status=account.account_status,
            opened_at=account.opened_at
        )

    else:
        raise HTTPException(
            status_code=400, 
            detail="Invalid Command: Supported are 'profile', 'credit_card', 'credit_account'."
        )


# ... card activation removed ...

@router.post("/cards/{card_id}/set-pin")
def set_card_pin(
    card_id: UUID,
    request: SetPinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_authenticated_user)
):
    """
    Set or update the PIN for an active card.
    """
    from app.admin.services.issuance_svc import CardIssuanceService
    return CardIssuanceService.set_card_pin(db, card_id, request)