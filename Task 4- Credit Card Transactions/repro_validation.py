import sys
import os
from pydantic import ValidationError

# Ensure the app directory is in the path
sys.path.append(os.getcwd())

from app.schemas.auth import ResidentialDetailsSchema, AddressInputItem
from app.models.enums import AddressType, ResidenceType

def test_validation():
    print("Testing ResidentialDetailsSchema validation...")
    
    # Payload with 1 year at current address and NO previous address
    payload = {
        "addresses": [
            {
                "type": "CURRENT",
                "residence_type": "Owned",
                "years_at_address": 1,
                "line1": "123 Main St",
                "city": "BENGALURU",
                "state": "KARNATAKA",
                "country": "INDIA",
                "pincode/Zipcode": "560085"
            }
        ]
    }
    
    try:
        schema = ResidentialDetailsSchema(**payload)
        print("FAIL: Validation should have failed but it PASSED!")
    except ValidationError as e:
        print("SUCCESS: Validation failed as expected.")
        print(f"Error: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected exception: {e}")

if __name__ == "__main__":
    test_validation()
