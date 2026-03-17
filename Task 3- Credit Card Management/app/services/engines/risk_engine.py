from typing import List, Dict, Any, Tuple
from app.models.enums import RiskBand, FraudFlagType
from app.services.engines.fraud_engine import FraudRule

def calculate_risk_assessment(
    bureau_score: int, 
    fraud_flags: List[FraudRule],
    declared_income: float
) -> Tuple[RiskBand, float, str]:
    """
    Calculates the risk band based on bureau score and fraud flags.
    Returns (RiskBand, confidence_score, explanation)
    """
    
    # 1. Immediate High/Very High Risk overrides
    critical_frauds = [f for f in fraud_flags if f.severity == "CRITICAL"]
    high_frauds = [f for f in fraud_flags if f.severity == "HIGH"]
    
    if critical_frauds:
        return (
            RiskBand.VERY_HIGH, 
            95.0, 
            f"Critical fraud flags detected: {', '.join([f.code.value for f in critical_frauds])}"
        )
        
    if high_frauds:
        return (
            RiskBand.HIGH, 
            85.0, 
            f"High severity fraud flags detected: {', '.join([f.code.value for f in high_frauds])}"
        )
        
    # 2. Score-based Risk Band Assignment
    if bureau_score >= 750:
        base_band = RiskBand.LOW
        confidence = 90.0
        explanation = "Excellent bureau score, no significant fraud flags."
    elif 650 <= bureau_score < 750:
        base_band = RiskBand.MEDIUM
        confidence = 80.0
        explanation = "Good bureau score, acceptable risk profile."
    elif 550 <= bureau_score < 650:
        base_band = RiskBand.HIGH
        confidence = 75.0
        explanation = "Subprime bureau score, requires manual underwriting or high caution."
    else:
        base_band = RiskBand.VERY_HIGH
        confidence = 90.0
        explanation = "Poor bureau score. Auto-reject recommended."
        
    # 3. Income modifiers
    if base_band in [RiskBand.MEDIUM, RiskBand.LOW] and declared_income < 20000:
        base_band = RiskBand.MEDIUM if base_band == RiskBand.LOW else RiskBand.HIGH
        explanation += " Risk elevated due to low declared income."
        confidence -= 10.0
        
    # 4. Medium fraud flags modifier
    medium_frauds = [f for f in fraud_flags if f.severity == "MEDIUM"]
    if medium_frauds:
        if base_band == RiskBand.LOW:
            base_band = RiskBand.MEDIUM
            explanation += f" Adjusted down due to medium fraud flags: {', '.join([f.code.value for f in medium_frauds])}."
        elif base_band == RiskBand.MEDIUM:
            base_band = RiskBand.HIGH
            explanation += f" Adjusted down due to medium fraud flags: {', '.join([f.code.value for f in medium_frauds])}."

    return base_band, max(0.0, min(100.0, confidence)), explanation
