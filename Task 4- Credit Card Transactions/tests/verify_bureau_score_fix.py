from app.models.enums import EmploymentType, Country
from app.services.engines.bureau_engine import simulate_bureau_score
from datetime import date

def verify_score():
    # User's DOB: 2004-09-26
    # Today: 2026-03-18
    # Age calculation from issuance_svc.py
    dob = date(2004, 9, 26)
    today = date(2026, 3, 18)
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    
    # After my fix, 'full_time' (normalized) becomes 'FULL_TIME' (uppercase)
    # and then matches the enum.
    employment_status = "full_time"
    employment_type_str = employment_status.upper()
    employment_type = EmploymentType(employment_type_str) if employment_type_str in [e.value for e in EmploymentType] else EmploymentType.UNEMPLOYED
    
    print(f"Age: {age}")
    print(f"Employment Type: {employment_type}")
    
    bureau_data = simulate_bureau_score(
        age=age,
        annual_income=480000.0,
        employment_type=employment_type,
        country=Country.INDIA,
        is_kyc_completed=True
    )
    
    print(f"Bureau Score: {bureau_data['bureau_score']}")
    assert bureau_data['bureau_score'] >= 700, "Bureau score should be above 700 now"
    print("Verification passed!")

if __name__ == "__main__":
    verify_score()
