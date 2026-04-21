from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict, condecimal, model_validator
from decimal import Decimal
from typing import Optional, List
from datetime import date
from fastapi import HTTPException



# COMMON SCHEMAS
def validate_currency_10_3(v: Decimal) -> Decimal:
    if v is None: return v
    if v < 0:
        raise ValueError("Value cannot be negative")
    if v >= Decimal("10000000000"):
        raise ValueError("Value must be less than 10 digits before decimal")
    str_v = str(v)
    if "." in str_v:
        decimals = len(str_v.split(".")[1])
        if decimals > 3:
            raise ValueError("only upto 4 digits after decimal")
    return v

class ContactSchema(BaseModel):
    country_code: str = Field(..., json_schema_extra={"example": "+91"})
    phone_number: str = Field(..., json_schema_extra={"example": "9876543210"})

    @field_validator("country_code", mode="before")
    @classmethod
    def format_country_code(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("country_code")
    def validate_country_code(cls, v):
        if not v.startswith("+") or not v[1:].isdigit() or len(v) > 5:
            raise ValueError("Invalid country code format (e.g., +91)")
        return v

    @field_validator("phone_number")
    def validate_phone_number(cls, v):
        if not v.isdigit() or len(v) < 7 or len(v) > 15:
            raise ValueError("Phone number must be between 7 and 15 digits")
        return v


class NameSchema(BaseModel):
    first_name: str = Field(..., min_length=2)
    last_name: str = Field(..., min_length=2)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name_format(cls, v):
        if v is None:
            return v
        if not v.replace(" ", "").isalpha():
            raise ValueError("Name should only contain letters and spaces")
        return v


class RegisterFullName(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)

    @field_validator("first_name", "last_name")
    @classmethod
    def letters_only(cls, v):
        if not v.isalpha():
            raise ValueError("must contain letters only")
        return v

class RegisterPhone(BaseModel):
    country_code: str
    number: str

    @model_validator(mode='after')
    def validate_phone(self) -> 'RegisterPhone':
        allowed = {
            "+91": ("India", 10),
            "+1": ("USA", 10),
            "+44": ("UK", 10),
            "+61": ("Australia", 9),
            "+971": ("UAE", 9),
            "+7": ("Russia", 10),
        }
        
        if self.country_code not in allowed:
            raise ValueError("Country not supported. Allowed: India, USA, UK, Australia, UAE, Russia.")
            
        country_name, required_len = allowed[self.country_code]
        if not self.number.isdigit():
            raise ValueError(f"Phone number for {self.country_code} ({country_name}) must be digits only.")
            
        if len(self.number) != required_len:
            raise ValueError(f"Phone number for {self.country_code} ({country_name}) must be exactly {required_len} digits. You provided {len(self.number)}.")
            
        return self


class CreateRegistrationRequest(BaseModel):
    full_name: RegisterFullName
    date_of_birth: date = Field(..., description="ISO 8601 date string, e.g. '1998-07-21'", json_schema_extra={"example": "1998-07-21"})
    email: str
    phone: RegisterPhone
    password: str
    confirm_password: str

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob_age(cls, v):
        """Ensure the applicant is at least 18 years old."""
        from dateutil.relativedelta import relativedelta
        today = date.today()
        age = relativedelta(today, v).years
        if age < 18:
            raise ValueError("You must be at least 18 years old to register.")
        return v

    @field_validator("email")
    @classmethod
    def email_rfc(cls, v):
        if any(c.isupper() for c in v):
            raise ValueError("Email must be lowercase only.")
        import re
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("value is not a valid email address: The email address is not valid. It must have exactly one @-sign.")
        return v

    @model_validator(mode='after')
    def passwords_match(self) -> 'CreateRegistrationRequest':
        p = self.password
        if len(p) < 12:
            raise ValueError("Password must be at least 12 characters.")
        if len(p) > 20:
            raise ValueError("Password cannot exceed 20 characters.")
        import re
        if not re.search(r'[A-Z]', p):
            raise ValueError("Password must contain at least 1 uppercase letter.")
        if not re.search(r'[a-z]', p):
            raise ValueError("Password must contain at least 1 lowercase letter.")
        if not re.search(r'[0-9]', p):
            raise ValueError("Password must contain at least 1 digit.")
        if not re.search(r'[!@#\$%\^&\*\(\)_\+\-\=\{\}\[\]\\\|:;"\'<>,.\?/]', p):
            raise ValueError("Password must contain at least 1 special character.")
            
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
            
        return self


class VerifyRegistrationRequest(BaseModel):
    email:EmailStr
    otp: str


# LOGIN
class LoginEmailRequest(BaseModel):
    email: EmailStr
    password: str

# PASSWORD RESET (FORGOT PASSWORD)
class CreatePasswordResetRequest(BaseModel):
    contact: ContactSchema


class VerifyPasswordResetRequest(BaseModel):
    password_reset_token: str
    new_password: str
    confirm_password: str

# GENERIC OTP
from app.models.customer import OTPPurpose
import uuid

class OTPGenerateRequest(BaseModel):
    purpose: OTPPurpose = Field(..., description="The context for which the OTP is needed (e.g., LOGIN, ACTIVATION)")

class OTPVerifyRequest(BaseModel):
    purpose: OTPPurpose = Field(..., description="The context for which the OTP is needed (e.g., LOGIN, ACTIVATION)")
    otp: str = Field(..., min_length=4, max_length=6, description="The OTP code received by the user")


class PasswordResetContact(BaseModel):
    country_code: str
    phone_number: str

class OTPDispatcherRequest(BaseModel):
    """Request body for OTP generate/verify operations."""
    purpose: OTPPurpose = Field(
        ...,
        description="The context for which the OTP is needed. Accepts any case (e.g., 'registration', 'REGISTRATION')."
    )
    otp: Optional[str] = Field(
        None, min_length=4, max_length=6,
        description="The OTP code received by the user. Mandatory for 'verify' command."
    )
    password_reset: Optional[PasswordResetContact] = None
    activation_id: Optional[uuid.UUID] = Field(
        None,
        description="The unique activation ID from Stage 1. Mandatory for purpose=ACTIVATION."
    )

    @field_validator("purpose", mode="before")
    @classmethod
    def normalize_purpose_case(cls, v):
        """Accept any case for purpose and normalise to uppercase."""
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @model_validator(mode='after')
    def validate_activation_integrity(self) -> 'OTPDispatcherRequest':
        """Ensure activation_id is provided if the purpose is ACTIVATION."""
        purpose_str = self.purpose.value if hasattr(self.purpose, 'value') else str(self.purpose)
        if purpose_str == "ACTIVATION" and not self.activation_id:
            raise ValueError("activation_id is mandatory when purpose is 'ACTIVATION'")
        return self


# RESET PASSWORD (AFTER LOGIN)
class ResetPasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str
    
from app.models.enums import UserRole

class AuthResponse(BaseModel):
    access_token: str
    message: str
    is_cif_completed: bool
    is_kyc_completed: bool
    application_status: Optional[str] = None
    login_timestamp: str
    
# CIF PERSONAL DETAILS SCHEMA
from datetime import date
from app.models.enums import (
    Country,
    YesNo,
    Suffix,
    Gender,
    MaritalStatus,
    PreferredLanguage
)

class PersonalDetailsSchema(BaseModel):
    nationality: Country
    dual_citizenship: YesNo = YesNo.NO
    country_of_residence: Country
    date_of_birth: date = Field(..., description="ISO 8601 date string, e.g. '1990-01-15'", json_schema_extra={"example": "1990-01-15"})
    gender: Gender
    marital_status: MaritalStatus
    preferred_language: PreferredLanguage = PreferredLanguage.ENGLISH
    
from app.models.enums import AddressType, ResidenceType
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

class AddressInputItem(BaseModel):
    type: AddressType
    residence_type: Optional[ResidenceType] = None
    years_at_address: Optional[int] = Field(None, ge=0)
    line1: Optional[str] = Field(None, min_length=5)
    line2: Optional[str] = None
    city: Optional[str] = Field(None, min_length=2)
    state: Optional[str] = Field(None, min_length=2)
    country: Optional[str] = Field(None, min_length=2)
    pincode: Optional[str] = Field(None, alias="pincode/Zipcode")
    is_kyc_verified: Optional[bool] = False
    same_as_current: Optional[bool] = False

    @field_validator("city", "state", "country")
    @classmethod
    def validate_address_strings(cls, v):
        if v is None:
            return v
        if not v.replace(" ", "").isalpha():
            raise ValueError(f"Value '{v}' should only contain letters")
        return v

    @model_validator(mode='after')
    def check_residence_type(self) -> 'AddressInputItem':
        if not self.same_as_current and not self.residence_type:
            raise ValueError("residence_type is mandatory")
        return self

class ResidentialDetailsSchema(BaseModel):
    addresses: List[AddressInputItem]

    @model_validator(mode='after')
    def check_previous_address_requirement(self) -> 'ResidentialDetailsSchema':
        # Use string values to avoid any enum instance comparison issues
        address_types = [addr.type.value if hasattr(addr.type, 'value') else str(addr.type) for addr in self.addresses]
        
        has_previous = "PREVIOUS" in address_types
        
        for addr in self.addresses:
            addr_type_val = addr.type.value if hasattr(addr.type, 'value') else str(addr.type)
            
            if addr_type_val == "CURRENT" and addr.years_at_address is not None:
                try:
                    yrs = int(addr.years_at_address)
                except ValueError:
                    continue
                
                if yrs < 3 and not has_previous:
                    raise ValueError("YEARS_AT_RESIDENCE IS LESS THAN 3 PLEASE MENTION THE PREVIOUS ADDRESS")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "addresses": [
                    {
                        "type": "CURRENT",
                        "residence_type": "Owned",
                        "years_at_address": 1,
                        "line1": "*****",
                        "line2":"*****",
                        "city": "BENGALURU",
                        "state": "KARNATAKA",
                        "country": "INDIA",
                        "pincode/Zipcode": "560***"
                    },
                    {
                        "type": "PREVIOUS",
                        "residence_type": "Rented",
                        "years_at_address": 3,
                        "line1": "*****",
                        "line2":"*****",
                        "city": "BENGALURU",
                        "state": "KARNATAKA",
                        "country": "INDIA",
                        "pincode/Zipcode": "560***"
                    }
                ]
            }
        }
    )
from app.models.enums import EmploymentType

class EmploymentDetailsSchema(BaseModel):
    employment_type: EmploymentType
    organisation_name: Optional[str] = None
    designation: Optional[str] = None
    annual_income: Optional[condecimal(max_digits=13, decimal_places=3)] = Field(None, json_schema_extra={"example": "0000000000.000"})

    @field_validator("annual_income")
    @classmethod
    def validate_inc(cls, v):
        return validate_currency_10_3(v)
    
    model_config = ConfigDict(from_attributes=True)
    
class FinancialDetailsSchema(BaseModel):
    net_annual_income: condecimal(max_digits=13, decimal_places=3) = Field(..., json_schema_extra={"example": "0000000000.000"})
    monthly_income: condecimal(max_digits=13, decimal_places=3) = Field(..., json_schema_extra={"example": "0000000000.000"})
    other_income: Optional[condecimal(max_digits=13, decimal_places=3)] = Field(Decimal("0.0"), json_schema_extra={"example": "0000000000.000"})
    housing_payment: Optional[condecimal(max_digits=13, decimal_places=3)] = Field(Decimal("0.0"), json_schema_extra={"example": "0000000000.000"})
    other_obligations: Optional[condecimal(max_digits=13, decimal_places=3)] = Field(Decimal("0.0"), json_schema_extra={"example": "0000000000.000"})

    @field_validator("net_annual_income", "monthly_income", "other_income", "housing_payment", "other_obligations")
    @classmethod
    def validate_fin_nums(cls, v):
        return validate_currency_10_3(v)
    
    model_config = ConfigDict(from_attributes=True)
    
class FATCADetailsSchema(BaseModel):
    us_citizen: bool = False
    us_tax_resident: bool = False
    us_tin: Optional[str] = None

class UnifiedCIFRequest(BaseModel):
    Personal_details: Optional[PersonalDetailsSchema] = None
    Residential_details: Optional[ResidentialDetailsSchema] = None
    Employment_details: Optional[EmploymentDetailsSchema] = None
    Financial_details: Optional[FinancialDetailsSchema] = None
    Fatca_details: Optional[FATCADetailsSchema] = None

# SUMMARY ENDPOINT SCHEMAS
class CifSummaryBasicProfile(BaseModel):
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None

class CifSummaryContactSummary(BaseModel):
    mobile: Optional[str] = None
    email: Optional[str] = None

class CifSummaryAddressSummary(BaseModel):
    current_city: Optional[str] = None
    country: Optional[str] = None
    kyc_verified: Optional[bool] = None

class CifSummaryRegulatory(BaseModel):
    fatca_status: str
    us_citizen: Optional[bool] = None
    us_tax_resident: Optional[bool] = None
    us_tin: Optional[str] = None

class CIFSummaryResponse(BaseModel):
    user_id: Optional[str] = None
    customer_type: str = "INDIVIDUAL"
    customer_status: str
    kyc_status: str
    risk_category: str
    basic_profile: CifSummaryBasicProfile
    contact_summary: CifSummaryContactSummary
    address_summary: Optional[CifSummaryAddressSummary] = None
    employment_details: Optional[EmploymentDetailsSchema] = None
    financial_information: Optional[FinancialDetailsSchema] = None
    regulatory_flags: CifSummaryRegulatory

class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    phone_number: str
    is_cif_completed: bool
    is_kyc_completed: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    kyc_state: str
