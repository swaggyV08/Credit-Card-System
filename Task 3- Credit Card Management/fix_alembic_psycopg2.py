import psycopg2

# Database details
conn_str = "postgresql://postgres:postgres@localhost:5432/credit_card_db"

try:
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    cur = conn.cursor()
    
    # Check current version
    cur.execute("SELECT version_num FROM alembic_version;")
    current_ver = cur.fetchone()
    print(f"Current version in DB: {current_ver}")
    
    # Force to head
    head_revision = "49d94bae5339"
    cur.execute(f"UPDATE alembic_version SET version_num = '{head_revision}'")
    print(f"Updated version to: {head_revision}")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
