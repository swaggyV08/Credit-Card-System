from sqlalchemy import create_engine, inspect
from app.core.config import settings

def verify_schema():
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    columns = inspector.get_columns('credit_account')
    column_names = [col['name'] for col in columns]
    
    print(f"Columns in 'credit_account': {column_names}")
    
    required = ['created_by', 'approved_by']
    missing = [col for col in required if col not in column_names]
    
    if not missing:
        print("SUCCESS: All required columns exist.")
    else:
        print(f"FAILURE: Missing columns: {missing}")

if __name__ == "__main__":
    verify_schema()
