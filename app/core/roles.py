from enum import Enum


class Role(str, Enum):
    ADMIN   = "ADMIN"       # Full system access (was SUPERADMIN)
    MANAGER = "MANAGER"     # Approvals, evaluations, account ops
    SALES   = "SALES"       # Customer onboarding & registration only
    USER    = "USER"        # Cardholder self-service only
