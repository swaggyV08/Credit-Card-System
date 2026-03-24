from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.api.deps import get_db, get_current_admin_user
from app.models.admin import Admin
from app.schemas.admin import AdminCreate, AdminEmailLogin, AdminResponse, TokenResponse, AdminCreationResponse
from app.core.security import hash_value, verify_value, validate_password_rules
from app.core.jwt import create_access_token

router = APIRouter(prefix="/auth", tags=["Admin: Authentication"])

@router.post("/login/email", response_model=TokenResponse)
def login_admin_email(data: AdminEmailLogin, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.email == data.email).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_value(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    full_name = f"{admin.first_name} {admin.last_name}"
    access_token = create_access_token({"sub": str(admin.id)})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "message": f"Welcome Admin: {full_name}",
        "login_timestamp": datetime.now(timezone.utc).isoformat()
    }



@router.post("/login/swagger", response_model=TokenResponse, include_in_schema=False)
def login_admin_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    This endpoint is used specifically for the Swagger UI 'Authorize' button which sends form data.
    """
    admin = db.query(Admin).filter(Admin.email == form_data.username).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_value(form_data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    full_name = f"{admin.first_name} {admin.last_name}"
    access_token = create_access_token({"sub": str(admin.id)})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "message": f"Welcome Admin: {full_name}",
        "login_timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.post("/admins", response_model=AdminCreationResponse, status_code=status.HTTP_201_CREATED)
def add_admin(
    data: AdminCreate,
    current_admin: Admin = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Only existing admins can add another admin.
    """
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Password mismatch")

    try:
        validate_password_rules(data.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing_admin = db.query(Admin).filter(Admin.email == data.email).first()
    if existing_admin:
        raise HTTPException(status_code=400, detail="Admin with this email already exists")
    
    hashed_password = hash_value(data.password)
    
    new_admin = Admin(
        first_name=data.first_name,
        last_name=data.last_name,
        suffix=data.suffix,
        email=data.email,
        country_code=data.contact.country_code if data.contact else None,
        phone_number=data.contact.phone_number if data.contact else None,
        position=data.position,
        password_hash=hashed_password
    )
    
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    new_admin_name = f"{new_admin.first_name} {new_admin.last_name}"
    current_admin_name = f"{current_admin.first_name} {current_admin.last_name}"
    
    return {
        "admin": f"{new_admin_name} added successfully",
        "created_at": new_admin.created_at or datetime.now(timezone.utc),
        "created_by": current_admin_name
    }
