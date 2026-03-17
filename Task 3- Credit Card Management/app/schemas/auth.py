from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional
from datetime import date
from fastapi import HTTPException



# COMMON SCHEMAS
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


from app.models.enums import Suffix

class NameSchema(BaseModel):
    first_name: str = Field(..., min_length=2)
    last_name: str = Field(..., min_length=2)
    suffix: Optional[Suffix] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name_format(cls, v):
        if v is None:
            return v
        if not v.replace(" ", "").isalpha():
            raise ValueError("Name should only contain letters and spaces")
        return v


# REGISTRATION (REST CORRECT)
class CreateRegistrationRequest(BaseModel):
    name: NameSchema
    contact: ContactSchema
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str


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
    otp: str
    new_password: str
    confirm_password: str

# GENERIC OTP
from app.models.customer import OTPPurpose
import uuid

class OTPActionRequest(BaseModel):
    purpose: OTPPurpose = Field(..., description="The context for which the OTP is needed (e.g., LOGIN, ACTIVATION)")
    otp: Optional[str] = Field(None, description="Not accepted for generate command. Mandatory for verify command.")


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

class DateOfBirthSchema(BaseModel):
    year: int
    month: int
    day: int

    @field_validator("year")
    def validate_year(cls, v):
        current_year = date.today().year
        if v < 1900 or v > current_year:
            raise ValueError("Invalid year")
        return v

    @field_validator("month")
    def validate_month(cls, v):
        if v < 1 or v > 12:
            raise ValueError("Month must be between 1 and 12")
        return v

    @field_validator("day")
    def validate_day(cls, v):
        if v < 1 or v > 31:
            raise ValueError("Day must be between 1 and 31")
        return v

    def to_date(self):
        try:
            return date(self.year, self.month, self.day)
        except ValueError:
            raise ValueError("Invalid calendar date")
        

class PersonalDetailsSchema(BaseModel):
    nationality: Country
    dual_citizenship: YesNo = YesNo.NO
    country_of_residence: Country
    date_of_birth: DateOfBirthSchema
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
    annual_income: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)
    
class FinancialDetailsSchema(BaseModel):
    net_annual_income: float
    monthly_income: float
    other_income: Optional[float] = 0
    housing_payment: Optional[float] = 0
    other_obligations: Optional[float] = 0
    
    model_config = ConfigDict(from_attributes=True)
    
class FATCADetailsSchema(BaseModel):
    us_citizen: bool = False
    us_tax_resident: bool = False
    us_tin: Optional[str] = None
    
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
    cif_id: Optional[str] = None
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
    cif_number: Optional[str] = None
    kyc_state: str
