import sqlalchemy
print(f"SQLAlchemy version: {sqlalchemy.__version__}")
from sqlalchemy.orm import declarative_base
print("Importing declarative_base...")
Base = declarative_base()
print("Base created successfully!")
