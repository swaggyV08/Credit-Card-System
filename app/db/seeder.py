from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.admin import Admin
from app.core.security import hash_value
from app.core.roles import Role

def seed_super_admin(db: Session):
    """Seed the initial SUPER_ADMIN user if not exists."""
    email = "vishnup@email.com"
    existing_admin = db.execute(select(Admin).where(Admin.email == email)).scalar_one_or_none()
    
    if not existing_admin:
        # Check by employee_id as well to avoid unique constraint violations if email changed
        existing_emp = db.execute(select(Admin).where(Admin.employee_id == "01")).scalar_one_or_none()
        if existing_emp:
            return  # If employee 01 exists, assume already seeded
            
        super_admin = Admin(
            email=email,
            password_hash=hash_value("Rasenshuriken@1"),
            full_name="Vishnu P",
            role=Role.SUPERADMIN,
            country_code="+91",
            phone_number="7019666370",
            department="Bank",
            employee_id="01"
        )
        db.add(super_admin)
        db.commit()
        db.refresh(super_admin)
        print("Successfully seeded SUPERADMIN.")
    else:
        # If it exists, ensure the role is SUPERADMIN
        if existing_admin.role != Role.SUPERADMIN:
            existing_admin.role = Role.SUPERADMIN
            db.commit()
            print("Upgraded existing admin to SUPERADMIN.")
