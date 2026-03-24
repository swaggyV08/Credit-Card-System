import hmac
import hashlib
import time
from fastapi import Request, HTTPException, Header
from app.core.config import settings

async def verify_banking_signature(
    request: Request,
    x_signature: str = Header(..., alias="X-Signature"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_request_id: str = Header(..., alias="X-Request-ID")
):
    """
    Validates the digital signature for banking-grade API security.
    Signature = HMAC_SHA256(secret, timestamp + body)
    """
    # 1. Prevent Replay Attack (5-minute window)
    try:
        request_time = int(x_timestamp)
        current_time = int(time.time())
        if abs(current_time - request_time) > 300: # 5 minutes
            raise HTTPException(status_code=403, detail="Request timestamp expired. Possible replay attack.")
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid X-Timestamp format")

    # 2. Reconstruct Payload
    # Get raw body for HMAC verification
    body = await request.body()
    request_body_str = body.decode()
    payload = f"{x_timestamp}{request_body_str}".encode()
    
    # 3. Compute Expected Signature
    expected_signature = hmac.new(
        settings.BANKING_API_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    # 4. Compare using constant-time comparison
    if not hmac.compare_digest(expected_signature, x_signature):
        raise HTTPException(status_code=403, detail="Invalid digital signature (X-Signature mismatch)")
    
    return x_request_id
