import os
import sys
from sqlalchemy import create_engine, inspect

# Use the URL from alembic.ini or .env
DB_URL = "postgresql://postgres:Rasenshuriken%401@localhost:5432/credit_card_db"

def check_columns():
    engine = create_engine(DB_URL)
    inspector = inspect(engine)
    
    tables = ['credit_card_application', 'credit_account', 'card']
    for table in tables:
        columns = [c['name'] for c in inspector.get_columns(table)]
        print(f"Table: {table}")
        print(f"Columns: {columns}")
        if 'readable_id' in columns:
            print(f"SUCCESS: 'readable_id' found in {table}")
        else:
            print(f"FAILURE: 'readable_id' NOT found in {table}")
        print("-" * 20)

if __name__ == "__main__":
    check_columns()
