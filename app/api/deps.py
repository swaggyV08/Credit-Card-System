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
