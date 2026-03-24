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

from sqlalchemy import create_engine, inspect
from app.core.config import settings

try:
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    if "admins" in inspector.get_table_names():
        print("Table 'admins' exists.")
        columns = [c["name"] for c in inspector.get_columns("admins")]
        print(f"Columns: {columns}")
    else:
        print("Table 'admins' DOES NOT exist.")
except Exception as e:
    print(f"Error: {e}")
