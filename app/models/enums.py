from enum import Enum


# AUTH
class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


# COUNTRY & REGION
class Country(str, Enum):
    INDIA = "India"
    USA = "USA"
    UK = "UK"
    CANADA = "Canada"
    AUSTRALIA = "Australia"
    UAE = "UAE"
    # Restricted / Prohibited
    PAKISTAN = "Pakistan"
    MYANMAR = "Myanmar"
    SYRIA = "Syria"
    YEMEN = "Yemen"
    AFGHANISTAN = "Afghanistan"
    SOMALIA = "Somalia"
    SUDAN = "Sudan"
    SOUTH_SUDAN = "South Sudan"
    LIBYA = "Libya"
    LEBANON = "Lebanon"
    IRAQ = "Iraq"
    ZIMBABWE = "Zimbabwe"
    VENEZUELA = "Venezuela"
    CONGO = "Congo"
    NORTH_KOREA = "North Korea"
    IRAN = "Iran"


class CountryCode(str, Enum):
    INDIA = "+91"
    USA = "+1"
    UK = "+44"
    CANADA = "+1"
    AUSTRALIA = "+61"
    UAE = "+971"


class TimeZone(str, Enum):
    IST = "IST"
    EST = "EST"
    PST = "PST"
    GMT = "GMT"
    AEST = "AEST"


# PERSONAL
class Suffix(str, Enum):
    JR = "JR"
    SR = "SR"
    II = "II"
    III = "III"


class YesNo(str, Enum):
    YES = "YES"
    NO = "NO"


class CitizenshipDocumentType(str, Enum):
    PAN = "PAN"
    AADHAAR = "AADHAAR"
    SSN = "SSN"
    NATIONAL_INSURANCE = "NATIONAL_INSURANCE"
    EMIRATES_ID = "EMIRATES_ID"
    SIN = "SIN"
    TFN = "TFN"

class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"

class MaritalStatus(str, Enum):
    SINGLE = "SINGLE"
    MARRIED = "MARRIED"
    DIVORCED = "DIVORCED"
    WIDOWED = "WIDOWED"


# RESIDENCE
class AddressType(str, Enum):
    CURRENT = "CURRENT"
    PERMANENT = "PERMANENT"
    OFFICE = "OFFICE"
    PREVIOUS = "PREVIOUS"
    ALTERNATIVE = "ALTERNATIVE"

class ResidenceType(str, Enum):
    OWNED = "Owned"
    MORTGAGED = "Mortgaged"
    RENTED = "Rented"
    LIVING_WITH_PARENTS = "Living with parents"


# EMPLOYMENT
class EmploymentType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    CONTRACTOR = "CONTRACTOR"
    STUDENT = "STUDENT"
    RETIRED = "RETIRED"
    UNEMPLOYED = "UNEMPLOYED"


# COMMUNICATION
class PreferredCommunication(str, Enum):
    SMS = "SMS"
    EMAIL = "EMAIL"

class PreferredLanguage(str, Enum):
    ENGLISH = "EN"
    SPANISH = "ES"
    FRENCH = "FR"
    HINDI = "HI"


# APPLICATION
class ApplicationStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    ADMIN_REVIEW_PENDING = "ADMIN_REVIEW_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACCOUNT_CREATED = "ACCOUNT_CREATED"

class RiskBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"

class FraudFlagType(str, Enum):
    RESIDENCY_MISMATCH = "RESIDENCY_MISMATCH"
    INCOME_MISMATCH = "INCOME_MISMATCH"
    HIGH_VELOCITY = "HIGH_VELOCITY"
    SANCTIONS_MATCH = "SANCTIONS_MATCH"

class ActorType(str, Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ADMIN = "ADMIN"

class ActionType(str, Enum):
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    BUREAU_PULLED = "BUREAU_PULLED"
    RISK_ASSESSED = "RISK_ASSESSED"
    FRAUD_CHECK_COMPLETED = "FRAUD_CHECK_COMPLETED"
    APPLICATION_APPROVED = "APPLICATION_APPROVED"
    APPLICATION_REJECTED = "APPLICATION_REJECTED"
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    CARD_ISSUED = "CARD_ISSUED"



class ApplicationStage(str, Enum):
    KYC = "KYC"
    DOCUMENTS = "DOCUMENTS"
    BUREAU = "BUREAU"
    UNDERWRITING = "UNDERWRITING"
    FINAL = "FINAL"


# PRODUCT
class ProductStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class InterestType(str, Enum):
    FIXED = "FIXED"
    FLOATING = "FLOATING"


# ACCOUNT
class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"


# CARD
class CardStatus(str, Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"


class CardType(str, Enum):
    PRIMARY = "PRIMARY"
    ADDON = "ADDON"
    VIRTUAL = "VIRTUAL"


class CardNetwork(str, Enum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    RUPAY = "RUPAY"
    AMEX = "AMEX"
    
# KYC
class KYCState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class PrimaryJurisdiction(str, Enum):
    INDIA = "INDIA"
    US = "US"
    UK = "UK"
    UAE = "UAE"
    AUSTRALIA = "AUSTRALIA"

class DocumentCategory(str, Enum):
    IDENTITY_PROOF = "IDENTITY_PROOF"
    ADDRESS_PROOF = "ADDRESS_PROOF"

class KYCVerificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class ScreeningType(str, Enum):
    AML = "AML"
    SANCTIONS = "SANCTIONS"
    PEP = "PEP"
    ADVERSE_MEDIA = "ADVERSE_MEDIA"

class ScreeningStatus(str, Enum):
    CLEARED = "CLEARED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"

class InternalRiskRating(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class AutoPayType(str, Enum):
    FULL = "FULL"
    MINIMUM = "MINIMUM"

# =====================================================
# CREDIT & CARD PRODUCT
# =====================================================
class ProductCategory(str, Enum):
    CARD = "CARD"
    LOAN = "LOAN"

class InterestCalculationMethod(str, Enum):
    AVERAGE_DAILY_BALANCE = "AVERAGE_DAILY_BALANCE"
    DAILY_BALANCE = "DAILY_BALANCE"
    ADJUSTED_BALANCE = "ADJUSTED_BALANCE"

class InterestBasis(str, Enum):
    ACTUAL_360 = "ACTUAL_360"
    ACTUAL_365 = "ACTUAL_365"

class AMLRiskCategory(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"

class TaxApplicability(str, Enum):
    GST_APPLICABLE = "GST_APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class CardFormFactor(str, Enum):
    PHYSICAL = "PHYSICAL"
    VIRTUAL = "VIRTUAL"
    HYBRID = "HYBRID"

class CardVariant(str, Enum):
    CLASSIC = "CLASSIC"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"
    SIGNATURE = "SIGNATURE"
    INFINITE = "INFINITE"

class BillingCycleType(str, Enum):
    MONTHLY = "MONTHLY"
    BI_MONTHLY = "BI_MONTHLY"
    QUARTERLY = "QUARTERLY"

class StatementGenerationMode(str, Enum):
    ELECTRONIC = "ELECTRONIC"
    PHYSICAL = "PHYSICAL"
    BOTH = "BOTH"

class RewardAccrualType(str, Enum):
    POINTS = "POINTS"
    CASHBACK = "CASHBACK"
    MILES = "MILES"

class RewardExpiryPolicy(str, Enum):
    NO_EXPIRY = "NO_EXPIRY"
    ONE_YEAR = "ONE_YEAR"
    TWO_YEARS = "TWO_YEARS"
    THREE_YEARS = "THREE_YEARS"

class FraudMonitoringProfile(str, Enum):
    STANDARD = "STANDARD"
    STRICT = "STRICT"

class VelocityCheckProfile(str, Enum):
    STANDARD = "STANDARD"
    AGGRESSIVE = "AGGRESSIVE"

# =====================================================
# CREDIT CARD MANAGEMENT SYSTEM (CCM)
# =====================================================
class CCMCardStatus(str, Enum):
    CREATED = "CREATED"     # Initial state upon card generation
    ISSUED = "ISSUED"       # Dispatched but not yet in user's hand
    INACTIVE = "INACTIVE"   # Received but not activated
    ACTIVE = "ACTIVE"       # Fully functional
    BLOCKED_USER = "BLOCKED_USER" # Temporarily blocked by customer
    BLOCKED_FRAUD = "BLOCKED_FRAUD" # Blocked by bank for security
    BLOCKED_TEMP = "BLOCKED_TEMP" # General temporary block
    EXPIRED = "EXPIRED"     # Past expiry date
    TERMINATED = "TERMINATED" # Permanently closed
    REPLACED = "REPLACED"   # Retired due to reissue

class CCMTransactionType(str, Enum):
    PURCHASE = "PURCHASE"
    REFUND = "REFUND"
    PAYMENT = "PAYMENT"
    FEE = "FEE"
    INTEREST = "INTEREST"
    CASH_ADVANCE = "CASH_ADVANCE"
    REVERSAL = "REVERSAL"

class CCMTransactionStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"
    AUTHORIZED = "AUTHORIZED"

class CCMFraudBlockReason(str, Enum):
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    GEO_MISMATCH = "GEO_MISMATCH"
    VELOCITY_CHECK = "VELOCITY_CHECK"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    USER_REQUEST = "USER_REQUEST"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"
    MERCHANT_BLACKLIST = "MERCHANT_BLACKLIST"
    AMOUNT_LIMIT_EXCEEDED = "AMOUNT_LIMIT_EXCEEDED"
    UNUSUAL_TIME = "UNUSUAL_TIME"
    FRAUD = "FRAUD"
    LOST = "LOST"
    STOLEN = "STOLEN"
    TEMPORARY_BLOCK = "TEMPORARY_BLOCK"
    CARD_FOUND = "CARD_FOUND"

class CCMCommand(str, Enum):
    ACTIVATE = "activate"
    GENERATE = "generate"
    VERIFY = "verify"
    BLOCK = "block"
    UNBLOCK_INI = "unblock_ini"
    UNBLOCK = "unblock"
    REPLACE = "replace"
    TERMINATE = "terminate"
    SET_PIN = "set_pin"
    FREEZE = "freeze"
    UNFREEZE = "unfreeze"
    RENEW = "renew"

class CCMReissueReason(str, Enum):
    DAMAGED = "DAMAGED"
    LOST = "LOST"
    UPGRADE = "UPGRADE"
    EXPIRY = "EXPIRY"

class CCMReissueType(str, Enum):
    PHYSICAL = "PHYSICAL"
    VIRTUAL = "VIRTUAL"


# =====================================================
# ADMIN CREDIT ACCOUNT MANAGEMENT
# =====================================================
class CCMAccountStatus(str, Enum):
    """Credit account lifecycle state machine."""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    FROZEN = "FROZEN"
    DELINQUENT = "DELINQUENT"
    CLOSED = "CLOSED"
    CHARGED_OFF = "CHARGED_OFF"

class CCMAccountRiskFlag(str, Enum):
    """Risk classification for credit accounts."""
    NONE = "NONE"
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"

class CCMAdjustmentType(str, Enum):
    """Manual adjustment direction."""
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"

class CCMLedgerEntryType(str, Enum):
    """Ledger entry classification."""
    PURCHASE = "PURCHASE"
    REFUND = "REFUND"
    PAYMENT = "PAYMENT"
    FEE = "FEE"
    INTEREST = "INTEREST"
    ADJUSTMENT = "ADJUSTMENT"
    CASH_ADVANCE = "CASH_ADVANCE"
    REVERSAL = "REVERSAL"
    LIMIT_CHANGE = "LIMIT_CHANGE"

class CCMLimitReasonCode(str, Enum):
    """Reason codes for credit limit changes."""
    INCOME_REVIEW = "INCOME_REVIEW"
    RISK_ADJUSTMENT = "RISK_ADJUSTMENT"
    PROMOTIONAL = "PROMOTIONAL"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"

class CCMStatusReasonCode(str, Enum):
    """Reason codes for account status transitions."""
    KYC_REVIEW = "KYC_REVIEW"
    FRAUD_ALERT = "FRAUD_ALERT"
    DELINQUENCY = "DELINQUENCY"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    COMPLIANCE = "COMPLIANCE"
    ADMIN_ACTION = "ADMIN_ACTION"

class CCMAdjustmentReasonCode(str, Enum):
    """Reason codes for manual adjustments."""
    MERCHANT_DISPUTE = "MERCHANT_DISPUTE"
    GOODWILL_CREDIT = "GOODWILL_CREDIT"
    FEE_WAIVER = "FEE_WAIVER"
    INTEREST_REVERSAL = "INTEREST_REVERSAL"
    MANUAL_CORRECTION = "MANUAL_CORRECTION"

# =====================================================
# BUREAU SCORING SYSTEM
# =====================================================
class BureauRiskBand(str, Enum):
    POOR = "POOR"
    FAIR = "FAIR"
    GOOD = "GOOD"
    VERY_GOOD = "VERY_GOOD"
    EXCELLENT = "EXCELLENT"

class ScoreTrigger(str, Enum):
    TRANSACTION_SETTLED = "TRANSACTION_SETTLED"
    PAYMENT_MADE = "PAYMENT_MADE"
    MANUAL_REQUEST = "MANUAL_REQUEST"
    SCHEDULED = "SCHEDULED"