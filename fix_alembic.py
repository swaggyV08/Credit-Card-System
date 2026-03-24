from sqlalchemy import create_engine, text

# Database URL from research
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/credit_card_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
head_revision = "49d94bae5339"

with engine.connect() as connection:
    trans = connection.begin()
    try:
        connection.execute(text(f"UPDATE alembic_version SET version_num = '{head_revision}'"))
        trans.commit()
        print(f"Successfully updated alembic_version to {head_revision}")
    except Exception as e:
        trans.rollback()
        print(f"Error: {e}")
