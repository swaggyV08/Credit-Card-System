import platform
# Monkey-patch platform.uname before it hangs
def mock_uname():
    return platform.uname_result('Windows', 'local-machine', '10', '10.0.19041', 'AMD64', 'Intel64 Family 6 Model 158 Stepping 10, GenuineIntel')

platform.uname = mock_uname
print("Monkey-patch applied!")

try:
    print("Importing SQLAlchemy...")
    import sqlalchemy
    print(f"SQLAlchemy version: {sqlalchemy.__version__}")
    
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()
    print("Base created successfully!")
    
except Exception as e:
    print(f"Error: {e}")

print("Done!")
