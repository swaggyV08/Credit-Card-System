import hmac
import hashlib
import time
import json

# Simulated settings
BANKING_API_SECRET = "banking_grade_secret_key_2024"

def generate_banking_headers(body_dict):
    timestamp = str(int(time.time()))
    request_id = "REQ-TEST-001"
    body_str = json.dumps(body_dict, separators=(',', ':'))
    
    payload = f"{timestamp}{body_str}".encode()
    signature = hmac.new(
        BANKING_API_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return {
        "X-Request-ID": request_id,
        "X-Timestamp": timestamp,
        "X-Signature": signature
    }

def verify_signature(body_str, signature, timestamp):
    payload = f"{timestamp}{body_str}".encode()
    expected = hmac.new(
        BANKING_API_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

# Test run
test_body = {"card_id": "123", "command": "activate"}
headers = generate_banking_headers(test_body)
body_json = json.dumps(test_body, separators=(',', ':'))

is_valid = verify_signature(body_json, headers["X-Signature"], headers["X-Timestamp"])
print(f"Signature Verification Success: {is_valid}")
print(f"Headers: {headers}")
