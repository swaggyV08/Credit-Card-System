from app.db.base_class import Base

# Authentication Layer
from app.models.auth import User, AuthCredential
from app.models.pending_registration import PendingRegistration
from app.models.admin import Admin

# Customer Layer
from app.models.customer import (
    CustomerProfile,
    CustomerAddress,
    EmploymentDetail,
    FinancialInformation,
    KYCDocumentSubmission,
    KYCOTPVerification,
    RiskComplianceLog,
    OTPCode,
    FATCADeclaration
)

# Credit Products Layer
from app.admin.models.credit_product import (
    CreditProductFees, CreditProductEligibilityRules,
    CreditProductComplianceMetadata, CreditProductAccountingMapping, CreditProductGovernance
)

# Card Products Layer
from app.admin.models.card_product import (
    CardProductCore, CardBillingConfiguration, CardTransactionControls,
    CardUsageLimits, CardRewardsConfiguration, CardAuthorizationRules,
    CardLifecycleRules, CardFraudRiskProfile, CardProductGovernance,
    CardFxConfiguration
)

# Issuance Layer
from app.admin.models.card_issuance import (
    CreditCardApplication, CreditAccount, Card
)

# Credit Base Models Layer
from app.models.credit import (
    BureauReport, RiskAssessment,
    FraudFlag as ApplicationFraudFlag,   # application-level fraud flags
    CreditDecision,
)

# Credit Card Management Layer (CCM)
from app.models.card_management import (
    CCMCreditAccount, CCMCreditCard, CCMCardTransaction,
    CCMCreditAccountAdjustment, CCMCreditAccountLedger
)

# Audit Layer
from app.models.audit import AuditLog

# Billing Layer (Week 5)
from app.models.billing import (
    Statement, StatementLineItem, Payment,
    FraudFlag as TransactionFraudFlag,   # transaction-level fraud flags
    IdempotencyKey,
)

# Bureau Scoring Layer
from app.models.bureau import BureauScore