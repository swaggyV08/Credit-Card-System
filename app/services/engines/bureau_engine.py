import random
from typing import Dict, Any
from app.models.enums import Country, EmploymentType

EMPLOYMENT_SCORE_MAP = {
    EmploymentType.FULL_TIME: +50,
    EmploymentType.PART_TIME: +10,
    EmploymentType.SELF_EMPLOYED: +20,
    EmploymentType.CONTRACTOR: +15,
    EmploymentType.STUDENT: -10,
    EmploymentType.RETIRED: +30,
    EmploymentType.UNEMPLOYED: -50,
}

COUNTRY_CREDIT_MULTIPLIER = {
    Country.INDIA: 1.0,
    Country.USA: 1.2,
    Country.UK: 1.1,
    Country.CANADA: 1.1,
    Country.AUSTRALIA: 1.1,
    Country.UAE: 1.0,
}

def simulate_bureau_score(
    age: int, 
    annual_income: float, 
    employment_type: EmploymentType, 
    country: Country, 
    is_kyc_completed: bool
) -> Dict[str, Any]:
    """
    Simulates a deterministic bureau score based on customer profile characteristics.
    Formula: clamp(base_score + income_factor + employment_factor + age_factor + kyc_factor * country_factor, 300, 900)
    """
    
    base_score = 600
    
    # 1. Age Factor
    age_factor = 0
    if age < 25:
        age_factor = -30
    elif 25 <= age <= 35:
        age_factor = +10
    elif 35 < age <= 50:
        age_factor = +30
    elif age > 50:
        age_factor = +40

    # 2. Income Factor
    income_factor = 0
    # Assuming income is in USD equivalent for simplicity, or we can just scale it.
    # Let's use a generic scale where 50,000 gives +25
    income_factor = min(int((annual_income / 50000) * 25), 100) # Max +100
    
    # 3. Employment Factor
    employment_factor = EMPLOYMENT_SCORE_MAP.get(employment_type, 0)
    
    # 4. KYC Factor
    kyc_factor = 50 if is_kyc_completed else -50
    
    # 5. Country Multiplier
    country_multiplier = COUNTRY_CREDIT_MULTIPLIER.get(country, 1.0)
    
    calculated_score = int(
        base_score + 
        income_factor + 
        employment_factor + 
        age_factor + 
        (kyc_factor * country_multiplier)
    )
    
    # Add a tiny deterministic random-like variation based on age and income to avoid identical scores
    variation = int(((age * 13) + int(annual_income) % 17) % 20) - 10
    calculated_score += variation
    
    # Clamp between 300 and 900
    final_score = max(300, min(900, calculated_score))
    
    return {
        "bureau_score": final_score,
        "report_reference_id": f"bur-{random.randint(100000, 999999)}",
        "snapshot": {
            "factors": {
                "base": base_score,
                "age_contribution": age_factor,
                "income_contribution": income_factor,
                "employment_contribution": employment_factor,
                "kyc_contribution": int(kyc_factor * country_multiplier),
                "variation": variation
            },
            "age_used": age,
            "income_used": annual_income,
            "employment_used": employment_type.value,
            "country_used": country.value
        }
    }
