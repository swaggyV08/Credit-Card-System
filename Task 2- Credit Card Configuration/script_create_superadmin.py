from app.db.session import SessionLocal
from app.models.admin import Admin
from app.core.security import hash_value

import traceback

def create_superadmin():
    db = SessionLocal()
    try:
        email = "vishnup@email.com"
        existing = db.query(Admin).filter(Admin.email == email).first()
        if existing:
            existing.first_name = "Vishnu"
            existing.last_name = "P"
            existing.country_code = "+91"
            existing.phone_number = "7019666370"
            db.commit()
            print(f"Superadmin already exists. Updated details for {email}")
            return
        
        passcode = "260304"
        password = "Rasenshuriken@1"
        
        hashed_passcode = hash_value(passcode)
        hashed_password = hash_value(password)
        
        superadmin = Admin(
            first_name="Vishnu",
            last_name="P",
            email=email,
            country_code="+91",
            phone_number="7019666370",
            position="Super Admin",
            passcode_hash=hashed_passcode,
            password_hash=hashed_password
        )
        
        db.add(superadmin)
        db.commit()
        db.refresh(superadmin)
        print(f"Superadmin successfully created! Name: Vishnu P, Email: {email}")
    except Exception as e:
        print(f"Failed to create superadmin: {e}")
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Initiating Superadmin Creation...")
    create_superadmin()
