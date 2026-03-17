from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
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

# GENERATE CIF NUMBER
def generate_cif_number(db: Session):
    last_profile = db.query(CustomerProfile)\
        .filter(CustomerProfile.cif_number != None)\
        .order_by(CustomerProfile.cif_number.desc())\
        .first()

    if not last_profile:
        return "ZBNQ00000001"

    last_number = int(last_profile.cif_number.replace("ZBNQ", ""))
    new_number = last_number + 1

    return f"ZBNQ{new_number:08d}"

# STAGE 1 — PERSONAL DETAILS
@router.put("/cif/personal-details")
def save_personal_details(
    request: PersonalDetailsSchema,
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    if user.is_cif_completed:
        raise HTTPException(
            status_code=403,
            detail="cif already completed"
        )

    # Age calculation from structured DOB
    dob = request.date_of_birth.to_date()

# Age calculation
    today = date.today()
    age = today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )

    if age < 18:
        raise HTTPException(
        status_code=403,
        detail="Customer must be at least 18 years old"
    )

    if age > 100:
        raise HTTPException(
        status_code=400,
        detail="Invalid age provided"
    )

    if calculate_age(dob) < 18:
        raise HTTPException(status_code=403, detail="Applicant must be 18+")

    if request.country_of_residence == Country.PAKISTAN or request.nationality == Country.PAKISTAN:
        raise HTTPException(
            status_code=403,
            detail="You country residents arent allowed to create a account in my bank"
        )

    if request.country_of_residence.value in BLACKLISTED_COUNTRIES:
        raise HTTPException(status_code=403, detail="Country not eligible")

    profile = db.query(CustomerProfile).filter(
        CustomerProfile.user_id == user.id
    ).first()

    if not profile:
        profile = CustomerProfile(user_id=user.id)
        db.add(profile)

    if not profile.cif_number:
        profile.cif_number = generate_cif_number(db)

    profile.nationality = request.nationality
    profile.dual_citizenship = request.dual_citizenship
    profile.country_of_residence = request.country_of_residence
    profile.date_of_birth = dob
    profile.gender = request.gender
    profile.marital_status = request.marital_status
    profile.preferred_language = request.preferred_language
    
    # FATCA AUTO TRIGGER LOGIC
    if (
        request.nationality == Country.USA
        or request.country_of_residence == Country.USA
    ):
        profile.fatca_required = True
    else:
        profile.fatca_required = False

    db.commit()

    return {"message": "Personal details saved"}

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
        cif_id=profile.cif_number or "PENDING_SUBMIT",
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

# STAGE 2 — RESIDENTIAL DETAILS
@router.put("/cif/residential-details")
def save_residential_details(
    request: ResidentialDetailsSchema,
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    if user.is_cif_completed:
        raise HTTPException(
            status_code=403,
            detail="cif already completed"
        )

    # Step 1: Get customer profile using user_id
    profile = db.query(CustomerProfile).filter(
        CustomerProfile.user_id == user.id
    ).first()

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="enter personal details first"
        )

    # Step 2: Delete existing addresses using customer_profile_id
    db.query(CustomerAddress).filter(
        CustomerAddress.customer_profile_id == profile.id
    ).delete()

    # Step 3: Iterate and add multiple addresses
    for addr in request.addresses:
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

# STAGE 3 — EMPLOYMENT DETAILS
@router.put("/cif/employment-details")
def save_employment_details(
    request: EmploymentDetailsSchema,
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    if user.is_cif_completed:
        raise HTTPException(
            status_code=403,
            detail="cif already completed"
        )

    # Step 1: Get profile using user_id
    profile = db.query(CustomerProfile).filter(
        CustomerProfile.user_id == user.id
    ).first()

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="enter personal details first"
        )
    
    # Chronological check: Check if residential details exist
    addr_exists = db.query(CustomerAddress).filter(CustomerAddress.customer_profile_id == profile.id).first()
    if not addr_exists:
        raise HTTPException(
            status_code=400,
            detail="enter residential details first"
        )

    # Step 2: Get employment using customer_profile_id
    employment = db.query(EmploymentDetail).filter(
        EmploymentDetail.customer_profile_id == profile.id
    ).first()

    # Step 3: Create if not exists
    if not employment:
        employment = EmploymentDetail(
            customer_profile_id=profile.id
        )
        db.add(employment)

    # Step 4: Update fields
    employment.employment_type = request.employment_type
    if request.organisation_name is not None:
        employment.organisation_name = request.organisation_name
    if request.designation is not None:
        employment.designation = request.designation
    employment.annual_income = request.annual_income

    db.commit()

    return {"message": "Employment details saved"}
# STAGE 4 — FINANCIAL DETAILS
@router.put("/cif/financial-details")
def save_financial_details(
    request: FinancialDetailsSchema,
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    if user.is_cif_completed:
        raise HTTPException(
            status_code=403,
            detail="cif already completed"
        )

    # Step 1: Get profile using user_id
    profile = db.query(CustomerProfile).filter(
        CustomerProfile.user_id == user.id
    ).first()

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="enter personal details first"
        )
    
    # Chronological check: Check if employment details exist
    emp_exists = db.query(EmploymentDetail).filter(EmploymentDetail.customer_profile_id == profile.id).first()
    if not emp_exists:
        raise HTTPException(
            status_code=400,
            detail="enter employment details first"
        )

    # Step 2: Get financial record using profile.id
    financial = db.query(FinancialInformation).filter(
        FinancialInformation.customer_profile_id == profile.id
    ).first()

    # Step 3: Create if not exists
    if not financial:
        financial = FinancialInformation(
            customer_profile_id=profile.id
        )
        db.add(financial)

    # Step 4: Update fields
    financial.net_annual_income = request.net_annual_income
    financial.monthly_income = request.monthly_income
    financial.other_income = request.other_income
    financial.housing_payment = request.housing_payment
    financial.other_obligations = request.other_obligations

    db.commit()

    return {"message": "Financial details saved"}
# STAGE 5 — FATCA DECLARATION
@router.put("/cif/fatca-details")
def save_fatca_details(
    request: FATCADetailsSchema,
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    if user.is_cif_completed:
        raise HTTPException(
            status_code=403,
            detail="cif already completed"
        )

    # Step 1: Fetch customer profile
    profile = db.query(CustomerProfile).filter(
        CustomerProfile.user_id == user.id
    ).first()

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="enter personal details first"
        )
    
    # Chronological check: Check if financial details exist
    fin_exists = db.query(FinancialInformation).filter(FinancialInformation.customer_profile_id == profile.id).first()
    if not fin_exists:
        raise HTTPException(
            status_code=400,
            detail="enter financial details first"
        )

    # Step 2: Fetch existing FATCA record
    fatca = db.query(FATCADeclaration).filter(
        FATCADeclaration.customer_profile_id == profile.id
    ).first()

    # Step 3: Create if not exists
    if not fatca:
        fatca = FATCADeclaration(
            customer_profile_id=profile.id
        )
        db.add(fatca)

    # Step 4: Update fields
    fatca.us_citizen = request.us_citizen
    fatca.us_tax_resident = request.us_tax_resident
    fatca.us_tin = request.us_tin

    db.commit()

    return {"message": "FATCA details saved"}

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

    # Generate CIF if not already generated
    if not profile.cif_number:
        profile.cif_number = generate_cif_number(db)

    # Mark CIF completed
    user.is_cif_completed = True
    profile.customer_status = "ACTIVE"

    db.commit()

    return {
        "message": "CIF Submitted Successfully",
        "cif_number": profile.cif_number
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

    # Create OTP Gate
    otp = generate_otp()
    otp_hash = hash_otp(otp)
    otp_record = KYCOTPVerification(
        document_submission_id=submission.id,
        phone_number_masked=f"XXXXX{user.phone_number[-4:]}" if user.phone_number else "XXXX",
        otp_hash=otp_hash,
        expires_at=get_expiry_time()
    )
    db.add(otp_record)
    
    profile.kyc_state = KYCState.IN_PROGRESS

    db.commit()
    print(f"KYC Document OTP generated: {otp}")

    return {
        "submission_id": str(submission.id),
        "status": "OTP_REQUIRED",
        "message": f"Upload initiated. OTP sent to registered mobile XXXX-XXXX."
    }

from pydantic import BaseModel
class KYCVerifyRequest(BaseModel):
    otp: str

@router.post("/kyc/{submission_id}")
def verify_kyc_document(
    submission_id: str,
    data: KYCVerifyRequest,
    command: str,
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    # IDEMPOTENCY: If KYC already completed, return success for this user
    if user.is_kyc_completed:
        return {
            "submission_id": submission_id,
            "status": "SUBMITTED",
            "message": "KYC already completed."
        }
        
    if command != "verify":
        raise HTTPException(status_code=400, detail="Invalid command")
    from sqlalchemy.dialects.postgresql import UUID
    import uuid
    try:
        sub_uuid = uuid.UUID(submission_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid submission ID")

    otp_record = db.query(KYCOTPVerification).filter(
        KYCOTPVerification.document_submission_id == sub_uuid,
        KYCOTPVerification.is_verified == False
    ).order_by(KYCOTPVerification.created_at.desc()).first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="OTP request not found or already verified.")

    if otp_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired.")

    if not verify_otp(data.otp, otp_record.otp_hash):
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    otp_record.is_verified = True
    
    submission = db.query(KYCDocumentSubmission).filter(KYCDocumentSubmission.id == sub_uuid).first()
    if submission:
        submission.verification_status = KYCVerificationStatus.PENDING

    # Mark KYC completed
    user.is_kyc_completed = True
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if profile:
        profile.kyc_state = KYCState.COMPLETED
        
        # Auto-transition credit card applications from SUBMITTED to KYC_REVIEW
        from app.admin.models.card_issuance import CreditCardApplication
        from app.models.enums import ApplicationStatus
        
        submitted_apps = db.query(CreditCardApplication).filter(
            CreditCardApplication.user_id == user.id,
            CreditCardApplication.application_status == ApplicationStatus.SUBMITTED
        ).all()
        
        for app in submitted_apps:
            app.application_status = ApplicationStatus.KYC_REVIEW
            # We can also add an audit log here if desired, but keeping it simple as per request
            
    db.commit()

    return {
        "submission_id": submission_id,
        "status": "SUBMITTED",
        "document_type": submission.document_type if submission else "UNKNOWN",
        "verification_status": "PENDING"
    }

# STAGE 5 — CREDIT ACCOUNT & CARDS
@router.get("/{credit_account_id}", response_model=CustomerCreditAccountResponse)
def get_credit_account_details(
    credit_account_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_authenticated_user)
):
    """
    Fetch specific credit account details including enhanced billing and limit information.
    """
    # Verify the account exists and belongs to the user
    # First get the customer profile for the current user
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    # Fetch account with joined data
    account_data = db.query(CreditAccount, CardProductCore, CardBillingConfiguration)\
        .join(CardProductCore, CreditAccount.card_product_id == CardProductCore.id)\
        .join(CardBillingConfiguration, CardProductCore.id == CardBillingConfiguration.card_product_id)\
        .filter(CreditAccount.id == credit_account_id, CreditAccount.cif_id == profile.id)\
        .first()
    
    if not account_data:
        raise HTTPException(status_code=404, detail="Credit account not found for this user")
    
    account, product, billing = account_data
    
    # Dynamic Billing Calculations
    today = date.today()
    try:
        stmt_date = date(today.year, today.month, billing.billing_cycle_day)
    except ValueError:
        stmt_date = date(today.year, today.month, 28)
        
    due_date = stmt_date + timedelta(days=billing.payment_due_days)
    
    outstanding = float(account.outstanding_amount)
    min_due = round(outstanding * 0.05, 2) if outstanding > 0 else 0.0
    
    return {
        "readable_id": account.readable_id,
        "customer_id": profile.cif_number or str(profile.id),
        "card_product_name": product.card_branding_code,
        "account_status": account.account_status,
        "opened_at": account.opened_at,
        "account_currency": account.account_currency,
        "billing_details": {
            "billing_cycle_day": billing.billing_cycle_day,
            "statement_date": stmt_date,
            "payment_due_date": due_date,
            "minimum_payment_due": min_due,
            "statement_summary": {
                "opening_balance": 0.0,
                "payment_credits": 0.0,
                "purchase_debits": outstanding,
                "finance_charges": 0.0,
                "total_dues": outstanding
            },
            "credit_summary": {
                "total_credit_limit": float(account.credit_limit),
                "available_credit": float(account.available_limit),
                "cash_advance_limit": float(account.cash_advance_limit),
                "used_credit": outstanding
            }
        }
    }

@router.get("/credit-cards", response_model=list[CustomerCardResponse])
def get_credit_cards(
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Fetch the user's active credit cards with bank-grade details securely.
    """
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Customer profile not found")
        
    full_name = f"{profile.first_name} {profile.last_name}"
    
    # Query cards with joins to accounts and card products
    cards_data = db.query(Card, CreditAccount, CardProductCore)\
        .join(CreditAccount, Card.credit_account_id == CreditAccount.id)\
        .join(CardProductCore, CreditAccount.card_product_id == CardProductCore.id)\
        .filter(CreditAccount.cif_id == profile.id)\
        .all()
    
    response = []
    for card, account, product in cards_data:
        response.append({
            "id": card.id,
            "readable_id": card.readable_id,
            "credit_account_id": card.credit_account_id,
            "card_product_name": product.card_branding_code,
            "card_type": card.card_type,
            "pan_masked": card.pan_masked,
            "expiry_date_masked": card.expiry_date_masked,
            "cvv_masked": card.cvv_masked,
            "card_status": card.card_status,
            "issued_at": card.issued_at,
            "activation_date": card.activation_date if card.card_status == CardStatus.ACTIVE else None,
            
            "card_holder_name": full_name,
            "card_network": product.card_network.value if hasattr(product.card_network, 'value') else str(product.card_network),
            "card_variant": product.card_variant.value if hasattr(product.card_variant, 'value') else str(product.card_variant),
            "account_currency": account.account_currency
        })
        
    return response

@router.get("/profile", response_model=UserProfileResponse)
def get_user_profile(
    user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
):
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    return {
        "user_id": str(user.id),
        "email": user.email,
        "phone_number": user.phone_number,
        "is_cif_completed": user.is_cif_completed,
        "is_kyc_completed": getattr(user, "is_kyc_completed", False),
        "first_name": profile.first_name if profile else None,
        "last_name": profile.last_name if profile else None,
        "date_of_birth": profile.date_of_birth if profile else None,
        "cif_number": profile.cif_number if profile else None,
        "kyc_state": profile.kyc_state.value if profile and profile.kyc_state else "NOT_STARTED"
    }

@router.post("/cards/{card_id}/activate")
def card_activation_handler(
    card_id: UUID,
    command: str,
    request: Optional[CardActivationRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_authenticated_user)
):
    """
    Unified activation endpoint:
    - command=activate: Generate activation token.
    - command=verify: Verify OTP and activate card.
    """
    from app.admin.services.issuance_svc import CardIssuanceService
    
    if command == "activate":
        return CardIssuanceService.validate_card_activation(db, card_id)
    elif command == "verify":
        if not request:
            raise HTTPException(status_code=400, detail="Request body required for verification")
        return CardIssuanceService.finalize_card_activation(db, card_id, request)
    else:
        raise HTTPException(status_code=400, detail="Invalid command. Use 'activate' or 'verify'.")

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