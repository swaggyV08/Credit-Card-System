import os
import platform
import collections

# Fix for platform.uname() hang on some Windows environments
if os.name == 'nt':
    try:
        UnameResult = collections.namedtuple('uname_result', ['system', 'node', 'release', 'version', 'machine', 'processor'])
        platform.uname = lambda: UnameResult('Windows', 'local-node', '10', '10.0.19041', 'AMD64', 'Intel64 Family 6 Model 158 Stepping 10')
    except Exception:
        pass

import sys
import os
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.admin import Admin
from app.core.security import hash_value
from app.core.config import settings

def seed_admin():
    db: Session = SessionLocal()
    try:
        # Check if admin already exists by email
        admin_email = "vishnup@email.com"
        admin = db.query(Admin).filter(Admin.email == admin_email).first()
        
        if admin:
            print(f"Admin with email {admin_email} already exists. Updating password...")
            admin.password_hash = hash_value("Rasenshuriken@1")
            admin.first_name = "Vishnu"
            admin.last_name = "P"
            admin.phone_number = "+917019666370"
            admin.country_code = "+91"
        else:
            print(f"Creating new superadmin: {admin_email}")
            admin = Admin(
                first_name="Vishnu",
                last_name="P",
                email=admin_email,
                password_hash=hash_value("Rasenshuriken@1"),
                country_code="+91",
                phone_number="+917019666370",
                position="Super Admin"
            )
            db.add(admin)
        
        db.commit()
        print("Superadmin seeded successfully!")
    except Exception as e:
        import traceback
        print(f"Error seeding admin: {e}")
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Ensure app directory is in path
    sys.path.append(os.getcwd())
    seed_admin()
