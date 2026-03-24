from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

from app.schemas.auth import ContactSchema
from app.models.enums import Suffix

class AdminBase(BaseModel):
    email: EmailStr
    position: Optional[str] = None
    first_name: str = Field(..., alias="first name")
    last_name: str = Field(..., alias="last name")
    suffix: Optional[Suffix] = None

    @field_validator("suffix", mode="before")
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class AdminCreate(AdminBase):
    contact: ContactSchema
    password: str
    confirm_password: str = Field(..., alias="confirm password")

class AdminEmailLogin(BaseModel):
    email: EmailStr
    password: str


class AdminResponse(AdminBase):
    id: UUID
    contact_info: Optional[ContactSchema] = None
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
