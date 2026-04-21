"""
Shared FastAPI dependencies.

The canonical auth dependency is now `require(permission)` from `app.core.rbac`.
These legacy wrappers are kept temporarily for modules not yet migrated.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Re-export async DB dependency for routers
from app.db.session import get_async_db  # noqa: F401

# --- LEGACY SHIMS FOR TEST COMPATIBILITY ---
def get_current_admin_user():
    """Shim for legacy tests."""
    pass

def get_current_user():
    """Shim for legacy tests."""
    pass

def get_current_authenticated_user():
    """Shim for legacy tests."""
    pass
