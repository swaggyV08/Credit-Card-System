import pytest
from app.models.enums import Country, EmploymentType
from app.services.engines.bureau_engine import simulate_bureau_score

def test_simulate_bureau_score_high_income():
    result = simulate_bureau_score(
        age=40,
        annual_income=150000.0,
        employment_type=EmploymentType.FULL_TIME,
        country=Country.USA,
        is_kyc_completed=True
    )
    score = result["bureau_score"]
    assert 300 <= score <= 900
    assert result["snapshot"]["factors"]["kyc_contribution"] == int(50 * 1.2)
    assert result["snapshot"]["factors"]["employment_contribution"] == 50
    assert score > 750 # Expect a high score

def test_simulate_bureau_score_low_income_unemployed():
    result = simulate_bureau_score(
        age=20, # < 25
        annual_income=0.0,
        employment_type=EmploymentType.UNEMPLOYED,
        country=Country.INDIA,
        is_kyc_completed=False
    )
    score = result["bureau_score"]
    assert 300 <= score <= 900
    assert result["snapshot"]["factors"]["age_contribution"] == -30
    assert result["snapshot"]["factors"]["employment_contribution"] == -50
    assert result["snapshot"]["factors"]["kyc_contribution"] == -50
    assert score < 600 # Expect a lower score

def test_score_clamping():
    # Force extreme values to test clamping
    result = simulate_bureau_score(
        age=60,
        annual_income=10000000.0,
        employment_type=EmploymentType.FULL_TIME,
        country=Country.USA,
        is_kyc_completed=True
    )
    score = result["bureau_score"]
    assert score <= 900

    result2 = simulate_bureau_score(
        age=18,
        annual_income=0.0,
        employment_type=EmploymentType.UNEMPLOYED,
        country=Country.INDIA,
        is_kyc_completed=False
    )
    score2 = result2["bureau_score"]
    assert score2 >= 300
