import platform
import collections

# Simpler mock for platform.uname
UnameResult = collections.namedtuple('uname_result', ['system', 'node', 'release', 'version', 'machine', 'processor'])
platform.uname = lambda: UnameResult('Windows', 'node', '10', '10.0.19041', 'AMD64', 'Intel64 Family 6 Model 158 Stepping 10')

print("Monkey-patch applied!")

try:
    print("Importing SQLAlchemy...")
    import sqlalchemy
    print(f"SQLAlchemy version: {sqlalchemy.__version__}")
    
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()
    print("Base created successfully!")
    
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

print("Done!")
