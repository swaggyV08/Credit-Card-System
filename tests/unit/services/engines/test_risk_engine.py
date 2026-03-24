import pytest
from app.models.enums import RiskBand, FraudFlagType
from app.services.engines.risk_engine import calculate_risk_assessment
from app.services.engines.fraud_engine import FraudRule

def test_critical_fraud():
    frauds = [FraudRule(code=FraudFlagType.HIGH_VELOCITY, description="high velocity", severity="CRITICAL")]
    band, conf, expl = calculate_risk_assessment(800, frauds, 50000.0)
    assert band == RiskBand.VERY_HIGH
    assert conf == 95.0
    assert "Critical fraud flags detected" in expl

def test_high_fraud():
    frauds = [FraudRule(code=FraudFlagType.RESIDENCY_MISMATCH, description="mismatch", severity="HIGH")]
    band, conf, expl = calculate_risk_assessment(800, frauds, 50000.0)
    assert band == RiskBand.HIGH
    assert conf == 85.0
    assert "High severity fraud flags detected" in expl

def test_excellent_score_no_fraud():
    band, conf, expl = calculate_risk_assessment(780, [], 50000.0)
    assert band == RiskBand.LOW
    assert conf == 90.0

def test_good_score_no_fraud():
    band, conf, expl = calculate_risk_assessment(700, [], 50000.0)
    assert band == RiskBand.MEDIUM
    assert conf == 80.0

def test_poor_score_no_fraud():
    band, conf, expl = calculate_risk_assessment(500, [], 50000.0)
    assert band == RiskBand.VERY_HIGH
    assert conf == 90.0

def test_low_income_modifier():
    band, conf, expl = calculate_risk_assessment(780, [], 10000.0) # Income < 20000
    assert band == RiskBand.MEDIUM
    assert conf == 80.0 # 90 - 10
    assert "elevated due to low declared income" in expl

def test_medium_fraud_modifier():
    frauds = [FraudRule(code=FraudFlagType.INCOME_MISMATCH, description="mismatch", severity="MEDIUM")]
    band, conf, expl = calculate_risk_assessment(760, frauds, 50000.0) # Base LOW, becomes MEDIUM
    assert band == RiskBand.MEDIUM
    assert "Adjusted down due to medium fraud flags" in expl
