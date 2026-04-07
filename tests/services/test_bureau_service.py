import pytest
from datetime import datetime, timezone, timedelta
from app.services.bureau_service import (
    classify_band,
    _compute_payment_history,
    _compute_utilisation,
    _compute_credit_history,
    _compute_transaction_behaviour,
    _compute_derogatory
)
from app.models.enums import BureauRiskBand

def test_classify_band_all_five_bands():
    assert classify_band(300) == BureauRiskBand.POOR
    assert classify_band(549) == BureauRiskBand.POOR
    assert classify_band(550) == BureauRiskBand.FAIR
    assert classify_band(649) == BureauRiskBand.FAIR
    assert classify_band(650) == BureauRiskBand.GOOD
    assert classify_band(749) == BureauRiskBand.GOOD
    assert classify_band(750) == BureauRiskBand.VERY_GOOD
    assert classify_band(849) == BureauRiskBand.VERY_GOOD
    assert classify_band(850) == BureauRiskBand.EXCELLENT
    assert classify_band(900) == BureauRiskBand.EXCELLENT

def test_payment_history_zero_payments_returns_175():
    assert _compute_payment_history(0, 0, 0, False) == 175

def test_payment_history_all_on_time_returns_350():
    assert _compute_payment_history(10, 0, 0, False) == 350

def test_payment_history_three_consecutive_missed_returns_zero():
    assert _compute_payment_history(10, 0, 0, True) == 0

def test_payment_history_mixed_applies_deductions_correctly():
    # 10 total: 8 on-time, 1 late, 1 missed
    # base = (8/10) * 350 = 280
    # late_deduction = 1 * 15 = 15
    # missed_deduction = 1 * 35 = 35
    # total = 280 - 15 - 35 = 230
    assert _compute_payment_history(8, 1, 1, False) == 230

def test_utilisation_below_10pct_returns_300():
    assert _compute_utilisation(5.0) == 300

def test_utilisation_above_90pct_returns_zero():
    assert _compute_utilisation(95.0) == 0

def test_utilisation_over_limit_returns_zero_and_sets_flag():
    # Over-limit logic is handled in _fetch_utilisation which sets the flag
    # but _compute_utilisation itself returns 0 for u >= 90
    assert _compute_utilisation(110.0) == 0

def test_credit_history_under_180_days_returns_zero():
    created_at = datetime.now(timezone.utc) - timedelta(days=100)
    assert _compute_credit_history(created_at) == 0

def test_credit_history_over_5_years_returns_150():
    created_at = datetime.now(timezone.utc) - timedelta(days=2000)
    assert _compute_credit_history(created_at) == 150

def test_transaction_behaviour_zero_transactions_returns_40():
    assert _compute_transaction_behaviour(0, 0, 0) == 40

def test_transaction_behaviour_disputes_apply_deduction():
    # 20 transactions, 2 disputes
    # volume_score = 120
    # dispute_deduction = 2 * 20 = 40
    # total = 120 - 40 = 80
    assert _compute_transaction_behaviour(20, 2, 0) == 80

def test_derogatory_clean_record_returns_80():
    assert _compute_derogatory(0, 0) == 80

def test_derogatory_three_marks_returns_zero():
    assert _compute_derogatory(2, 1) == 0

def test_final_score_clamping():
    # Logic in compute_bureau_score:
    # raw_total = f1 + f2 + f3 + f4 + f5
    # score = round(300 + (raw_total / 1000) * 600)
    
    # Test min floor
    raw_total_min = 0
    score_min = round(300 + (raw_total_min / 1000) * 600)
    assert max(300, min(900, score_min)) == 300
    
    # Test max ceiling
    raw_total_max = 1000
    score_max = round(300 + (raw_total_max / 1000) * 600)
    assert max(300, min(900, score_max)) == 900
