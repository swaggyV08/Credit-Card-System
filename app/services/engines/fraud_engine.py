from typing import List, Dict, Any, Optional
from app.models.enums import FraudFlagType

class FraudRule:
    def __init__(self, code: FraudFlagType, description: str, severity: str):
        self.code = code
        self.description = description
        self.severity = severity

def detect_fraud_anomalies(
    declared_country: str,
    ip_country: Optional[str],
    declared_income: float,
    verified_income: Optional[float],
    application_velocity_count: int
) -> List[FraudRule]:
    """
    Generates system-only, immutable fraud flags based on application anomalies.
    
    Args:
        declared_country (str): Country declared by the applicant.
        ip_country (str, optional): Country detected from the originating IP.
        declared_income (float): Income declared in the application.
        verified_income (float, optional): Income verified during KYC/Financial checks.
        application_velocity_count (int): Number of applications from this user in the last 24h.
        
    Returns:
        List[FraudRule]: List of detected fraud flags with severity levels.
    """
    flags = []
    
    if ip_country and declared_country and declared_country.upper() != ip_country.upper():
        flags.append(FraudRule(
            code=FraudFlagType.RESIDENCY_MISMATCH,
            description=f"Declared residency ({declared_country}) does not match originating IP country ({ip_country})",
            severity="HIGH"
        ))
        
    if verified_income is not None and declared_income > verified_income * 2:
        flags.append(FraudRule(
            code=FraudFlagType.INCOME_MISMATCH,
            description="Declared income is significantly higher than verified income",
            severity="MEDIUM"
        ))
        
    if application_velocity_count > 3:
        flags.append(FraudRule(
            code=FraudFlagType.HIGH_VELOCITY,
            description=f"High application velocity detected: {application_velocity_count} applications in 24 hours",
            severity="CRITICAL"
        ))
        
    return flags
