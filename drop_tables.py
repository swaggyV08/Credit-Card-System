import sys
import os

# Add the current directory to sys.path to import app
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, MetaData, text
from app.core.config import settings
from app.db.base import Base 

def drop_all_tables_and_types():
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # Drop all tables
        print("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        
        # Drop alembic_version specifically
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        
        # Drop all types (Enums) in the public schema
        print("Dropping all custom types (enums)...")
        # This query finds all types in the public schema that are not system types
        result = conn.execute(text("""
            SELECT n.nspname as schema, t.typname as type 
            FROM pg_type t 
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace 
            WHERE (t.typrelid = 0 OR (SELECT c.relkind = 'c' FROM pg_catalog.pg_class c WHERE c.oid = t.typrelid)) 
            AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_type el WHERE el.oid = t.typelem AND el.typarray = t.oid)
            AND n.nspname = 'public'
        """))
        
        types = result.fetchall()
        for schema, type_name in types:
            try:
                print(f"Dropping type {schema}.{type_name}...")
                conn.execute(text(f"DROP TYPE IF EXISTS {schema}.\"{type_name}\" CASCADE"))
            except Exception as e:
                print(f"Could not drop type {type_name}: {e}")
        
        conn.commit()
    print("Cleanup complete.")

if __name__ == "__main__":
    drop_all_tables_and_types()
