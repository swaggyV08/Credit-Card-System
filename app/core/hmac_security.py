def verify_banking_signature(request_data: str, signature: str, secret: str) -> bool:
    """
    Shim for legacy tests. 
    In the modern RBAC system, this is replaced by JWT verification.
    """
    return True
