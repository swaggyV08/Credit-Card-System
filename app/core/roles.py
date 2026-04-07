from enum import Enum


class Role(str, Enum):
    SUPERADMIN = "SUPERADMIN"   # Unrestricted System Setup
    ADMIN      = "ADMIN"       # Full system access
    MANAGER    = "MANAGER"     # Approvals, evaluations, account ops
    SALES      = "SALES"       # Customer onboarding & registration only
    USER       = "USER"        # Cardholder self-service only
