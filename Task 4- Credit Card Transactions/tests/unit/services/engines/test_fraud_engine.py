import pytest
from app.models.enums import FraudFlagType
from app.services.engines.fraud_engine import detect_fraud_anomalies

def test_detect_residency_mismatch():
    flags = detect_fraud_anomalies(
        declared_country="India",
        ip_country="USA",
        declared_income=50000,
        verified_income=50000,
        application_velocity_count=1
    )
    assert len(flags) == 1
    assert flags[0].code == FraudFlagType.RESIDENCY_MISMATCH
    assert flags[0].severity == "HIGH"

def test_detect_income_mismatch():
    flags = detect_fraud_anomalies(
        declared_country="India",
        ip_country="India",
        declared_income=150000,
        verified_income=50000, # declared > verified * 2
        application_velocity_count=1
    )
    assert len(flags) == 1
    assert flags[0].code == FraudFlagType.INCOME_MISMATCH
    assert flags[0].severity == "MEDIUM"

def test_high_velocity():
    flags = detect_fraud_anomalies(
        declared_country="India",
        ip_country="India",
        declared_income=50000,
        verified_income=50000,
        application_velocity_count=5 # > 3
    )
    assert len(flags) == 1
    assert flags[0].code == FraudFlagType.HIGH_VELOCITY
    assert flags[0].severity == "CRITICAL"

def test_no_fraud():
    flags = detect_fraud_anomalies(
        declared_country="India",
        ip_country="India",
        declared_income=50000,
        verified_income=50000,
        application_velocity_count=1
    )
    assert len(flags) == 0
