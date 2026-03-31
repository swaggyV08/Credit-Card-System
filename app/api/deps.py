"""
Shared FastAPI dependencies.

The canonical auth dependency is now `require(permission)` from `app.core.rbac`.
These legacy wrappers are kept temporarily for modules not yet migrated.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from app.core.jwt import decode_access_token
from app.models.admin import Admin
from app.models.auth import User

security = HTTPBearer()
admin_security = OAuth2PasswordBearer(
    tokenUrl="/admin/auth/login/swagger",
    scheme_name="AdminLogin",
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Legacy wrappers — kept for backward compat until all modules migrated ──

def get_current_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Legacy: prefer ``require()`` from ``app.core.rbac``."""
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


def get_current_admin_user(
    token: str = Depends(admin_security),
    db: Session = Depends(get_db),
):
    """Legacy: prefer ``require()`` from ``app.core.rbac``."""
    payload = decode_access_token(token)
    admin_id = payload.get("sub")

    if not admin_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    admin = db.query(Admin).filter(Admin.id == admin_id).first()

    if not admin:
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")

    return admin
