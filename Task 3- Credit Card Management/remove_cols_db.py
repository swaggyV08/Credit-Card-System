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

from sqlalchemy import create_engine, text
from app.core.config import settings

def remove_columns():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        print("Dropping columns from 'admins'...")
        try:
            conn.execute(text("ALTER TABLE admins DROP COLUMN IF EXISTS middle_name;"))
            conn.execute(text("ALTER TABLE admins DROP COLUMN IF EXISTS passcode_hash;"))
        except Exception as e:
            print(f"Error updating admins: {e}")
            
        print("Dropping columns from 'auth_credentials'...")
        try:
            conn.execute(text("ALTER TABLE auth_credentials DROP COLUMN IF EXISTS passcode_hash;"))
        except Exception as e:
            print(f"Error updating auth_credentials: {e}")
            
        print("Dropping columns from 'pending_registrations'...")
        try:
            conn.execute(text("ALTER TABLE pending_registrations DROP COLUMN IF EXISTS middle_name;"))
            conn.execute(text("ALTER TABLE pending_registrations DROP COLUMN IF EXISTS passcode;"))
        except Exception as e:
            print(f"Error updating pending_registrations: {e}")
            
        conn.commit()
    print("Done!")

if __name__ == "__main__":
    remove_columns()
