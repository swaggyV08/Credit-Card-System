import traceback
try:
    from tests.unit.services.engines.test_bureau_engine import test_simulate_bureau_score_high_income, test_simulate_bureau_score_low_income_unemployed, test_score_clamping
    from tests.unit.services.engines.test_fraud_engine import test_detect_residency_mismatch, test_detect_income_mismatch, test_high_velocity, test_no_fraud
    from tests.unit.services.engines.test_risk_engine import test_critical_fraud, test_high_fraud, test_excellent_score_no_fraud, test_good_score_no_fraud, test_poor_score_no_fraud, test_low_income_modifier, test_medium_fraud_modifier

    test_simulate_bureau_score_high_income()
    test_simulate_bureau_score_low_income_unemployed()
    test_score_clamping()
    print("Bureau Engine Tests Passed")

    test_detect_residency_mismatch()
    test_detect_income_mismatch()
    test_high_velocity()
    test_no_fraud()
    print("Fraud Engine Tests Passed")

    test_critical_fraud()
    test_high_fraud()
    test_excellent_score_no_fraud()
    test_good_score_no_fraud()
    test_poor_score_no_fraud()
    test_low_income_modifier()
    test_medium_fraud_modifier()
    print("Risk Engine Tests Passed")

    print("\nALL TESTS PASSED SUCCESSFULLY.")
except Exception as e:
    print(f"TEST FAILED: {e}")
    traceback.print_exc()
