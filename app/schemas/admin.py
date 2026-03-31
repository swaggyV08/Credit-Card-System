from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

from app.core.roles import Role


class AdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, description="Minimum 12 characters")
    full_name: str = Field(..., min_length=2)
    role: Role = Role.MANAGER
    department: Optional[str] = None
    employee_id: Optional[str] = None


class AdminEmailLogin(BaseModel):
    email: EmailStr
    password: str


class AdminResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: Role
    department: Optional[str] = None
    employee_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    message: str
    login_timestamp: str


class AdminCreationResponse(BaseModel):
    admin: str
    created_at: datetime
    created_by: str
