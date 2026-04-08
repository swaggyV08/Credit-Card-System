"""
Global validation utilities for the ZBANQUe API.

Provides:
- Case-insensitive enum normalisation for all enum inputs across the API.
- Sequential ID generators for user and admin identifiers.
"""
from enum import Enum
from typing import Type, TypeVar
from fastapi import HTTPException
from sqlalchemy.orm import Session

T = TypeVar("T", bound=Enum)


def normalize_enum_input(value: str, enum_class: Type[T], field_name: str) -> T:
    """
    Accept any case (upper, lower, mixed) for an enum input,
    normalise to uppercase internally, and return the matching enum member.

    Raises a human-readable HTTPException if no match is found.
    """
    if not isinstance(value, str):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"{field_name} must be a string value"
            }
        )

    normalised = value.strip().upper()
    valid_values = [m.value for m in enum_class]

    try:
        return enum_class(normalised)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_VALUE",
                "message": (
                    f"Invalid {field_name}: '{value}'. "
                    f"Valid values are: {', '.join(valid_values)}"
                )
            }
        )


def validate_enum_case_strict(value: str, field_name: str) -> str:
    """
    Validate that an enum string input is either fully uppercase or fully lowercase.
    Mixed case (e.g. 'Manager') is rejected with a human-readable error.

    Returns the value normalised to uppercase.
    """
    stripped = value.strip()
    if stripped != stripped.upper() and stripped != stripped.lower():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CASE",
                "message": f"{field_name} must be entered in all uppercase or all lowercase"
            }
        )
    return stripped.upper()


def generate_znbnq_id(db: Session) -> str:
    """
    Generate a sequential human-readable user ID in format ZNBNQ000001.

    Queries the users table for the highest existing ZNBNQ-prefixed ID
    and returns the next sequential number, zero-padded to 6 digits.
    """
    from app.models.auth import User

    last_user = (
        db.query(User)
        .filter(User.id.like("ZNBNQ%"))
        .order_by(User.id.desc())
        .first()
    )

    if not last_user:
        return "ZNBNQ000001"

    last_number = int(last_user.id.replace("ZNBNQ", ""))
    new_number = last_number + 1
    return f"ZNBNQ{new_number:06d}"


def generate_znbad_id(db: Session) -> str:
    """
    Generate a sequential employee ID for admins in format ZNBAD000001.

    Queries the admins table for the highest existing ZNBAD-prefixed ID
    and returns the next sequential number, zero-padded to 6 digits.
    """
    from app.models.admin import Admin

    last_admin = (
        db.query(Admin)
        .filter(Admin.employee_id.like("ZNBAD%"))
        .order_by(Admin.employee_id.desc())
        .first()
    )

    if not last_admin:
        return "ZNBAD000001"

    last_number = int(last_admin.employee_id.replace("ZNBAD", ""))
    new_number = last_number + 1
    return f"ZNBAD{new_number:06d}"
