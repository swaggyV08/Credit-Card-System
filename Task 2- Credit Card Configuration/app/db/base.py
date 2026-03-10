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
    BureauReport, RiskAssessment, FraudFlag, CreditDecision
)

# Audit Layer
from app.models.audit import AuditLog